# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Managed company PATs: API queues intent; only the isolated worker issues tokens."""

import hashlib
import time
import uuid
from datetime import datetime, time as midnight, timedelta, timezone as utc
from contextlib import contextmanager

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from plane.db.models import (
    CompanyAccount,
    ManagedRepositoryConnection,
    RepositoryConnectionOptOut,
    RepositoryCredential,
    RepositorySelection,
    RepositoryAccessAudit,
    User,
)
from .company import CompanyError, identity_matches
from .repository_transport import RepositoryError
from .vault import VaultError, seal, require_owner


def managed_instance(instance):
    return (
        settings.SINGULARITY_MANAGED_REPOSITORY_TOKENS
        and settings.SINGULARITY_COMPANY_ENABLED
        and instance.enabled
        and instance.company_primary
        and instance.provider == "gitlab"
        and instance.api_url.rstrip("/") == settings.SINGULARITY_COMPANY_URL.rstrip("/") + "/api/v4"
    )


def account_for(owner, instance):
    if not managed_instance(instance) or not owner.is_active or owner.is_bot:
        return None
    return CompanyAccount.objects.filter(
        user=owner,
        status="linked",
        instance_url=settings.SINGULARITY_COMPANY_URL.rstrip("/"),
        external_id__isnull=False,
    ).first()


def managed_credential(owner, repository, selection, wait_seconds=12):
    """No admin token or GitLab mutation runs in the HTTP/MCP process."""
    if not managed_instance(repository.instance):
        return None
    if RepositoryConnectionOptOut.objects.filter(owner=owner, repository=repository).exists():
        raise RepositoryError("repository_connection_disabled", 403)
    # Preserve explicit anonymous access and user-supplied tokens.
    if selection and (selection.anonymous or selection.credential.kind not in ("oauth", "managed_pat")):
        return None
    account = account_for(owner, repository.instance)
    if not account:
        raise RepositoryError("repository_company_identity_required", 409)
    if selection and (
        selection.credential.owner_id != owner.pk or selection.credential.instance_id != repository.instance_id
    ):
        raise VaultError("credential_unavailable")
    row, _ = ManagedRepositoryConnection.objects.get_or_create(
        owner=owner,
        instance=repository.instance,
        defaults={"external_actor_id": str(account.external_id)},
    )
    deadline = time.monotonic() + wait_seconds
    while True:
        row.refresh_from_db()
        if row.external_actor_id != str(account.external_id):
            raise RepositoryError("repository_company_identity_changed", 409)
        if row.status in ("revoked", "disabled"):
            raise RepositoryError("repository_connection_disabled", 403)
        credential = row.credential
        if credential and credential.revoked_at:
            raise RepositoryError("repository_connection_disabled", 403)
        if credential and credential.expires_at and credential.expires_at > timezone.now():
            require_owner(credential, owner)
            if credential.owner_id != owner.pk or credential.instance_id != repository.instance_id:
                raise VaultError("credential_unavailable")
            # Opt-out is checked again to avoid undoing a concurrent disconnect.
            with transaction.atomic():
                locked = ManagedRepositoryConnection.objects.select_for_update().get(pk=row.pk)
                if (
                    locked.status in ("revoked", "disabled")
                    or RepositoryConnectionOptOut.objects.filter(owner=owner, repository=repository).exists()
                ):
                    raise RepositoryError("repository_connection_disabled", 403)
                RepositorySelection.objects.update_or_create(
                    owner=owner, repository=repository, defaults={"credential": credential, "anonymous": False}
                )
            return credential
        ManagedRepositoryConnection.objects.filter(pk=row.pk, status="ready").update(next_attempt_at=timezone.now())
        if time.monotonic() >= deadline or row.status == "error":
            raise RepositoryError(row.error_code or "repository_connection_pending", 503)
        time.sleep(0.25)


@contextmanager
def issuance_lock(pk):
    key = int.from_bytes(hashlib.sha256(f"managed-pat:{pk}".encode()).digest()[:8], "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [key])
        acquired = cursor.fetchone()[0]
    try:
        yield acquired
    finally:
        if acquired:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [key])


def recover_managed_read(owner, credential, wait_seconds=12):
    """An upstream 401 can reflect earlier expiry or a concurrently retired PAT."""
    row = ManagedRepositoryConnection.objects.get(owner=owner, credential=credential)
    previous = credential.encrypted_material
    ManagedRepositoryConnection.objects.filter(pk=row.pk).update(next_attempt_at=timezone.now())
    deadline = time.monotonic() + wait_seconds
    while True:
        row.refresh_from_db()
        if row.status in ("disabled", "revoked"):
            raise RepositoryError("repository_connection_disabled", 403)
        latest = row.credential
        if latest.encrypted_material != previous:
            require_owner(latest, owner)
            return latest
        if row.status == "error" or time.monotonic() >= deadline:
            raise RepositoryError(row.error_code or "repository_connection_pending", 503)
        time.sleep(0.25)


def remote_token(client, token_id):
    try:
        return client.call("GET", f"personal_access_tokens/{token_id}")
    except CompanyError as error:
        if str(error) == "company_http_404":
            return None
        raise


def revoke(client, token_id):
    try:
        client.call("DELETE", f"personal_access_tokens/{token_id}")
    except CompanyError as error:
        if str(error) != "company_http_404":
            raise


def cleanup(row, client):
    for token_id in list(row.retired_token_ids):
        revoke(client, token_id)
        row.retired_token_ids.remove(token_id)
        row.save(update_fields=["retired_token_ids", "updated_at"])


def cleanup_pending(row, client):
    if not row.pending_name:
        return
    page = 1
    while True:
        found = client.call(
            "GET",
            "personal_access_tokens",
            params={
                "user_id": int(row.external_actor_id),
                "search": row.pending_name,
                "revoked": False,
                "per_page": 100,
                "page": page,
            },
        )
        matches = [
            token
            for token in found
            if token.get("name") == row.pending_name and str(token.get("user_id")) == row.external_actor_id
        ]
        for token in matches:
            revoke(client, token["id"])
        if len(found) < 100:
            break
        # Deletions shrink the result set, so rescan the same page.
        if not matches:
            page += 1
    row.pending_name = ""
    row.save(update_fields=["pending_name", "updated_at"])


def disable(row, client, status="disabled"):
    with transaction.atomic():
        row = ManagedRepositoryConnection.objects.select_for_update().get(pk=row.pk)
        row.status, row.error_code = status, ""
        if row.remote_token_id and row.remote_token_id not in row.retired_token_ids:
            row.retired_token_ids.append(row.remote_token_id)
        row.remote_token_id = None
        if row.credential_id:
            RepositoryCredential.objects.filter(pk=row.credential_id).update(
                revoked_at=timezone.now(), validation_status="revoked", encrypted_material=""
            )
        row.save()
    cleanup(row, client)


def process_connection(pk, client):
    """Reconcile response loss, verify identity, replace before retiring old PAT."""
    with issuance_lock(pk) as acquired:
        if not acquired:
            return
        row = ManagedRepositoryConnection.objects.select_related("owner", "instance", "credential").get(pk=pk)
        try:
            if not managed_instance(row.instance) or row.instance.api_url.rstrip("/") != client.base + "/api/v4":
                raise CompanyError("managed_instance_mismatch")
            cleanup(row, client)
            cleanup_pending(row, client)
            if row.status in ("disabled", "revoked"):
                if row.remote_token_id and row.remote_token_id not in row.retired_token_ids:
                    disable(row, client, row.status)
                return
            account = account_for(row.owner, row.instance)
            if not account or str(account.external_id) != row.external_actor_id:
                disable(row, client)
                return
            remote = client.call("GET", f"users/{account.external_id}")
            if not identity_matches(remote, row.owner_id) or remote.get("state") != "active":
                disable(row, client)
                return
            if row.credential_id and row.credential.revoked_at:
                disable(row, client, "revoked")
                return
            config = client.call("GET", "application/settings")
            days = min(
                max(1, settings.SINGULARITY_MANAGED_TOKEN_LIFETIME_DAYS),
                int(config.get("max_personal_access_token_lifetime") or 365),
            )
            if row.remote_token_id:
                current = remote_token(client, row.remote_token_id)
                if not current or current.get("revoked"):
                    disable(row, client, "revoked")
                    return
                if str(current.get("user_id")) != row.external_actor_id or set(current.get("scopes", [])) != {
                    "read_api"
                }:
                    raise CompanyError("managed_token_identity_mismatch")
                renewal_window = min(timedelta(days=7), timedelta(days=days) / 4)
                if row.credential.expires_at > timezone.now() + renewal_window and not current.get("expired"):
                    row.status, row.error_code = "ready", ""
                    row.next_attempt_at = timezone.now() + timedelta(minutes=5)
                    row.save()
                    return
            # Durable name before POST: after response loss, revoke the orphan
            # whose plaintext cannot be recovered, then issue a replacement.
            row.pending_name = f"plane-repository-{row.pk}-{uuid.uuid4().hex[:12]}"
            row.status, row.error_code = "issuing", ""
            row.save()
            expiry = timezone.now().date() + timedelta(days=days)
            token = client.call(
                "POST",
                f"users/{account.external_id}/personal_access_tokens",
                json={"name": row.pending_name, "scopes": ["read_api"], "expires_at": expiry.isoformat()},
            )
            if (
                not token.get("token")
                or str(token.get("user_id")) != row.external_actor_id
                or set(token.get("scopes", [])) != {"read_api"}
            ):
                raise CompanyError("invalid_managed_token_response")
            expires_at = datetime.combine(
                datetime.strptime(token["expires_at"], "%Y-%m-%d").date(), midnight(), utc.utc
            )
            if expires_at <= timezone.now():
                raise CompanyError("invalid_managed_token_expiry")
            with transaction.atomic():
                locked = ManagedRepositoryConnection.objects.select_for_update().get(pk=row.pk)
                current_owner = User.objects.get(pk=row.owner_id)
                current_account = account_for(current_owner, row.instance)
                if (
                    locked.status in ("disabled", "revoked")
                    or not current_account
                    or str(current_account.external_id) != row.external_actor_id
                ):
                    revoke(client, token["id"])
                    return
                credential = row.credential or RepositoryCredential(
                    owner=row.owner, instance=row.instance, kind="managed_pat"
                )
                credential.label = "Plane managed GitLab read access"
                credential.external_actor_id = row.external_actor_id
                credential.external_actor_label = remote.get("username", "")
                credential.expires_at, credential.validated_at = expires_at, timezone.now()
                credential.validation_status = "identity_verified"
                seal(credential, token["token"])
                credential.save()
                if row.remote_token_id:
                    row.retired_token_ids.append(row.remote_token_id)
                row.credential, row.remote_token_id = credential, token["id"]
                row.status, row.error_code, row.pending_name = "ready", "", ""
                row.next_attempt_at = timezone.now() + timedelta(minutes=5)
                row.save()
                blocked = RepositoryConnectionOptOut.objects.filter(owner=row.owner).values("repository_id")
                RepositorySelection.objects.filter(
                    owner=row.owner,
                    repository__instance=row.instance,
                    credential__owner=row.owner,
                    credential__kind="oauth",
                    credential__external_actor_id=row.external_actor_id,
                ).exclude(repository_id__in=blocked).update(credential=credential)
                RepositoryAccessAudit.objects.create(
                    owner=row.owner,
                    credential=credential,
                    external_actor_id=row.external_actor_id,
                    operation="managed_pat_issue",
                    result="ready",
                )
            cleanup(row, client)
        except (CompanyError, VaultError, ValueError, KeyError, TypeError) as error:
            code = str(error) if isinstance(error, (CompanyError, VaultError)) else "invalid_managed_token_response"
            ManagedRepositoryConnection.objects.filter(pk=pk).exclude(status__in=["disabled", "revoked"]).update(
                status="error", error_code=code, next_attempt_at=timezone.now() + timedelta(seconds=30)
            )


def maintain_connections(client):
    if not settings.SINGULARITY_MANAGED_REPOSITORY_TOKENS:
        return
    rows = ManagedRepositoryConnection.objects.filter(
        Q(next_attempt_at__lte=timezone.now()) | Q(owner__is_active=False)
    ).exclude(status__in=["disabled", "revoked"], remote_token_id__isnull=True, retired_token_ids=[], pending_name="")
    for pk in list(rows.order_by("next_attempt_at").values_list("pk", flat=True)[:100]):
        process_connection(pk, client)
