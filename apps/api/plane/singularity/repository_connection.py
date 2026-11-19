# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Owner-scoped OAuth connection reuse and serialized rotating refresh tokens."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from plane.db.models import RepositoryCredential, RepositorySelection, User
from .vault import VaultError, oauth_material, seal_oauth, require_owner
from .repository_transport import RepositoryError


@transaction.atomic
def usable_connection(user, credential):
    # Same lock as save_oauth: callbacks and reads cannot rotate the same grant
    # concurrently, even when old selections still reference duplicate rows.
    owner = User.objects.select_for_update().get(pk=user.pk)
    credential = RepositoryCredential.objects.select_related("instance").get(pk=credential.pk)
    if not owner.is_active or owner.is_bot or credential.owner_id != owner.pk or credential.revoked_at:
        raise VaultError("credential_unavailable")
    if not credential.instance.enabled:
        raise VaultError("instance_disabled")
    if credential.kind != "oauth" or not credential.external_actor_id:
        require_owner(credential, owner)
        return credential
    rows = RepositoryCredential.objects.filter(
        owner=owner,
        instance=credential.instance,
        kind="oauth",
        external_actor_id=credential.external_actor_id,
        revoked_at__isnull=True,
    )
    current = rows.order_by("-validated_at", "-created_at", "id").first()
    material = oauth_material(current)
    if current.expires_at and current.expires_at <= timezone.now() + timedelta(seconds=60):
        refresh = material.get("refresh_token")
        if refresh and current.instance.provider == "gitlab":
            from .repository_oauth import oauth_config, token_request

            token = token_request(
                current.instance,
                oauth_config(current.instance),
                {
                    "grant_type": "refresh_token",
                    "refresh_token": refresh,
                },
            )
            try:
                expires = int(token["expires_in"])
                if not 0 < expires <= 315360000 or not token.get("access_token") or not token.get("refresh_token"):
                    raise ValueError
                seal_oauth(current, token["access_token"], token["refresh_token"])
            except (KeyError, ValueError, TypeError):
                raise RepositoryError("invalid_upstream_response", 502) from None
            current.expires_at = timezone.now() + timedelta(seconds=expires)
            current.validated_at = timezone.now()
            current.save(
                update_fields=["key_version", "encrypted_material", "expires_at", "validated_at", "updated_at"]
            )
    require_owner(current, owner)
    # Repair only this owner's explicit selections for the exact same account.
    RepositorySelection.objects.filter(owner=owner, credential__in=rows.exclude(pk=current.pk)).update(
        credential=current
    )
    return current
