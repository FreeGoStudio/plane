# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Resolve registered repository URLs and add only after verified access."""

from urllib.parse import urlsplit, unquote
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from plane.db.models import RepositoryInstance, RepositoryCredential, RepositorySelection, ProjectRepository, User
from .repository_api import RepositoryAPI, StrictSerializer, validated
from .repository_provider import RepositoryProvider, safe_path
from .repository_transport import RepositoryError
from .vault import unseal, seal


def resolve_address(address):
    """Match a full URL to an enabled registered host without contacting arbitrary hosts."""
    try:
        url = urlsplit(address.strip())
        if (
            url.scheme not in ("https", "http")
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError
        matches = []
        for host in RepositoryInstance.objects.filter(enabled=True):
            base = urlsplit(host.web_url.rstrip("/"))
            prefix = base.path.rstrip("/") + "/"
            if (url.scheme, url.hostname, url.port) == (base.scheme, base.hostname, base.port) and url.path.startswith(
                prefix
            ):
                matches.append((len(prefix), host, unquote(url.path[len(prefix) :]).rstrip("/").removesuffix(".git")))
        if not matches:
            raise RepositoryError("repository_host_not_configured", 400)
        _, host, path = max(matches, key=lambda item: item[0])
        safe_path(path, False)
        if len(path.split("/")) < 2 or (host.provider == "github" and len(path.split("/")) != 2):
            raise ValueError
        return host, path
    except ValueError:
        raise RepositoryError("invalid_repository_url", 400) from None


def available_credentials(owner, instance=None):
    """Return usable choices, grouping OAuth sessions for the same host/account only."""
    rows = (
        RepositoryCredential.objects.filter(owner=owner, revoked_at__isnull=True)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
        .order_by("-validated_at", "-created_at", "id")
    )
    if instance is not None:
        rows = rows.filter(instance=instance)
    seen, result = set(), []
    for row in rows:
        key = (row.instance_id, row.external_actor_id) if row.kind == "oauth" and row.external_actor_id else row.pk
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


@transaction.atomic
def save_oauth(owner, instance, raw, actor_id, actor_label, expires):
    """Refresh one account connection and repoint old OAuth selections without deleting history."""
    User.objects.select_for_update().get(pk=owner.pk)
    rows = RepositoryCredential.objects.filter(
        owner=owner, instance=instance, kind="oauth", external_actor_id=actor_id, revoked_at__isnull=True
    )
    row = rows.order_by("-validated_at", "-created_at").first() or RepositoryCredential(
        owner=owner, instance=instance, kind="oauth"
    )
    row.label = f"{instance.name} · {actor_label}"[:160]
    row.external_actor_id, row.external_actor_label = actor_id, actor_label
    row.validated_at, row.validation_status, row.expires_at = timezone.now(), "identity_verified", expires
    seal(row, raw)
    row.save()
    RepositorySelection.objects.filter(owner=owner, credential__in=rows.exclude(pk=row.pk)).update(credential=row)
    rows.exclude(pk=row.pk).update(revoked_at=timezone.now())
    return row


@transaction.atomic
def finish_add(project, owner, instance, metadata, purpose, credential=None):
    """Register a verified repository idempotently; preserve existing bindings and purpose."""
    row, created = ProjectRepository.objects.get_or_create(
        project=project,
        instance=instance,
        external_id=metadata["external_id"],
        defaults={"path": metadata["path"], "default_branch": metadata["default_branch"], "purpose": purpose},
    )
    if not row.enabled:
        raise RepositoryError("configuration_conflict", 409)
    RepositorySelection.objects.update_or_create(
        owner=owner, repository=row, defaults={"credential": credential, "anonymous": credential is None}
    )
    return row


class AddInput(StrictSerializer):
    url = serializers.CharField(max_length=2048)
    purpose = serializers.ChoiceField(choices=["development", "reference", "documentation", "prototype"])
    method = serializers.ChoiceField(choices=["inspect", "oauth", "existing", "anonymous", "token"])
    credential_id = serializers.UUIDField(required=False)
    token = serializers.CharField(max_length=8192, required=False, trim_whitespace=False, write_only=True)


class AddRepository(RepositoryAPI):
    def post(self, request, slug, project_id):
        """Inspect a URL, start consent, or verify access before saving the new repository."""
        from .repository_oauth import oauth_config, start_add

        project = self.project(request, slug, project_id, admin=True)
        data = validated(AddInput, request.data)
        host, path = resolve_address(data["url"])
        choices = available_credentials(request.user, host)
        if data["method"] == "inspect":
            try:
                oauth_config(host)
                oauth = True
            except RepositoryError:
                oauth = False
            return Response(
                {
                    "instance_id": str(host.pk),
                    "name": host.name,
                    "provider": host.provider,
                    "path": path,
                    "oauth_available": oauth,
                    "credentials": [
                        {
                            "id": str(c.pk),
                            "label": (c.external_actor_label or c.label)
                            + (f" · Token {str(c.pk)[:8]}" if c.kind != "oauth" else ""),
                        }
                        for c in choices
                    ],
                }
            )
        if data["method"] == "oauth":
            return Response(start_add(request, project, host, path, data["purpose"]))
        credential, token = None, None
        if data["method"] == "existing":
            credential = next((c for c in choices if str(c.pk) == str(data.get("credential_id"))), None)
            if credential is None:
                raise RepositoryError("repository_authorization_required", 403)
            token = unseal(credential)
        elif data["method"] == "token":
            token = data.get("token")
            if not token:
                raise RepositoryError("repository_authorization_required", 403)
        provider = RepositoryProvider(host, token)
        metadata = provider.metadata(path, by_id=False)
        with transaction.atomic():
            if data["method"] == "token":
                actor_id, actor_label = provider.actor()
                credential = RepositoryCredential(
                    owner=request.user,
                    instance=host,
                    label=f"{host.name} · {actor_label}"[:160],
                    external_actor_id=actor_id,
                    external_actor_label=actor_label,
                    validated_at=timezone.now(),
                    validation_status="identity_verified",
                )
                seal(credential, token)
                credential.save()
            row = finish_add(project, request.user, host, metadata, data["purpose"], credential)
        self.repository, self.credential = row, credential
        return Response({"id": str(row.pk), "purpose": row.purpose}, status=201)
