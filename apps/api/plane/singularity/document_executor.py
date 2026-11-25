# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Per-repository document executors, provisioned only by the company worker."""

import base64
import secrets
import uuid
from datetime import date, timedelta

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.utils import timezone

from plane.db.models import DocumentRepositoryExecutor, ProjectRepository, ProjectRepositoryBinding, RequirementAdoption
from .company import CompanyError
from .repository_managed import issuance_lock
from .repository_provider import component
from .repository_transport import RepositoryError, RepositoryTransport
from .vault import VaultError, keyring


def eligible(repository):
    return (
        repository.enabled
        and repository.purpose == "documentation"
        and settings.SINGULARITY_COMPANY_ENABLED
        and repository.instance.enabled
        and repository.instance.company_primary
        and repository.instance.provider == "gitlab"
        and repository.instance.api_url.rstrip("/") == settings.SINGULARITY_COMPANY_URL.rstrip("/") + "/api/v4"
        and ProjectRepositoryBinding.objects.filter(documentation_repository=repository).exists()
    )


def associated_data(row):
    repo = row.repository
    return f"document-executor-v1:{repo.pk}:{repo.instance_id}:{repo.external_id}".encode()


def seal(row, token):
    version, keys = keyring()
    nonce = secrets.token_bytes(12)
    row.encrypted_material = base64.b64encode(
        nonce + AESGCM(keys[version]).encrypt(nonce, token.encode(), associated_data(row))
    ).decode()
    row.key_version = version


def unseal(row):
    _, keys = keyring()
    try:
        raw = base64.b64decode(row.encrypted_material, validate=True)
        return AESGCM(keys[row.key_version]).decrypt(raw[:12], raw[12:], associated_data(row)).decode()
    except (KeyError, ValueError, InvalidTag, UnicodeError):
        raise VaultError("document_executor_unreadable") from None


def transport(repository):
    if not eligible(repository):
        raise RepositoryError("document_executor_instance_not_managed", 409)
    row, _ = DocumentRepositoryExecutor.objects.get_or_create(repository=repository)
    if (
        row.status != "ready"
        or not row.encrypted_material
        or not row.expires_at
        or row.expires_at <= timezone.now().date()
    ):
        raise RepositoryError(row.error_code or "document_executor_pending", 503)
    return RepositoryTransport(repository.instance, unseal(row))


def actor_matches(repository_id, actor):
    return DocumentRepositoryExecutor.objects.filter(
        repository_id=repository_id, actor_id=actor, expires_at__gt=timezone.now().date()
    ).exists()


def revoke(client, root, token_id):
    try:
        client.call("DELETE", f"{root}/{token_id}")
    except CompanyError as error:
        if str(error) != "company_http_404":
            raise


def cleanup(row, client, root):
    # Persisted issuance names recover a lost response or a crash before saving a secret.
    if row.issuance_name:
        page = 1
        while True:
            tokens = client.call("GET", root, params={"per_page": 100, "page": page})
            for token in tokens:
                if token["name"] == row.issuance_name and token["id"] != row.token_id and not token.get("revoked"):
                    revoke(client, root, token["id"])
            if len(tokens) < 100:
                break
            page += 1
        row.issuance_name = ""
        row.save(update_fields=["issuance_name", "updated_at"])
    for token_id in list(row.retired_tokens):
        revoke(client, root, token_id)
        row.retired_tokens.remove(token_id)
        row.save(update_fields=["retired_tokens", "updated_at"])


def reconcile(repository, client):
    """One repository's error must not stop provisioning the others."""
    with issuance_lock("document-executor:" + str(repository.pk)) as acquired:
        if not acquired or not eligible(repository):
            return
        row, _ = DocumentRepositoryExecutor.objects.get_or_create(repository=repository)
        if row.next_check_at > timezone.now():
            return
        root = f"projects/{component(repository.external_id)}/access_tokens"
        try:
            cleanup(row, client, root)
            remote = None
            if row.token_id:
                try:
                    remote = client.call("GET", f"{root}/{row.token_id}")
                except CompanyError as error:
                    if str(error) != "company_http_404":
                        raise
            healthy = bool(remote and remote.get("active") and not remote.get("revoked"))
            policy = client.call("GET", "application/settings")
            lifetime = max(1, min(90, int(policy.get("max_personal_access_token_lifetime") or 90)))
            renew_days = min(14, max(1, lifetime // 3))
            due = not healthy or date.fromisoformat(remote["expires_at"]) <= timezone.now().date() + timedelta(
                days=renew_days
            )
            if due:
                # Do not replace an actor while its already-authorized merge is in flight.
                if (
                    healthy
                    and RequirementAdoption.objects.filter(
                        config__repository=repository, status__in=["pending", "running"]
                    ).exists()
                ):
                    row.next_check_at = timezone.now() + timedelta(minutes=5)
                    row.save(update_fields=["next_check_at", "updated_at"])
                    return
                row.issuance_name = "Plane document executor " + uuid.uuid4().hex
                row.save(update_fields=["issuance_name", "updated_at"])
                remote = client.call(
                    "POST",
                    root,
                    json={
                        "name": row.issuance_name,
                        "scopes": ["api", "write_repository"],
                        "access_level": 40,
                        "expires_at": (timezone.now().date() + timedelta(days=lifetime)).isoformat(),
                    },
                )
                # Validate the project credential before making it available to the executor.
                http = RepositoryTransport(repository.instance, remote["token"])
                identity = http.get("/user")
                project = http.get("/projects/" + component(repository.external_id))
                if str(project["id"]) != repository.external_id or identity["id"] != remote["user_id"]:
                    raise RepositoryError("document_executor_identity_mismatch", 409)
                seal(row, remote["token"])
                if row.token_id:
                    row.retired_tokens = [*row.retired_tokens, row.token_id]
                row.token_id, row.actor_id = remote["id"], "user-" + str(remote["user_id"])
                row.issuance_name = ""
            row.expires_at = date.fromisoformat(remote["expires_at"])
            row.status, row.error_code = "ready", ""
            row.next_check_at = timezone.now() + timedelta(hours=1)
            row.save()  # Durable new credential BEFORE revoking the old one.
            cleanup(row, client, root)
        except (CompanyError, RepositoryError, VaultError, ValueError, KeyError, TypeError):
            # Upstream bodies and token values never enter logs or API diagnostics.
            DocumentRepositoryExecutor.objects.filter(pk=row.pk).update(
                status="error",
                error_code="document_executor_provisioning_failed",
                next_check_at=timezone.now() + timedelta(minutes=1),
            )


def maintain_executors(client):
    ids = ProjectRepositoryBinding.objects.exclude(documentation_repository=None).values_list(
        "documentation_repository_id", flat=True
    )
    for repository in ProjectRepository.objects.filter(pk__in=ids, enabled=True).select_related("instance"):
        if eligible(repository):
            reconcile(repository, client)
