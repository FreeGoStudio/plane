# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Versioned AES-GCM storage bound to the credential owner and hosting instance."""

import base64
import json
import secrets
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from plane.db.models import RepositoryCredential, RepositorySelection, ProjectMember


class VaultError(Exception):
    """Safe codes only; never include key material, tokens or cipher text."""


def keyring():
    """Load independently mounted material on each operation to support rotation."""
    try:
        data = json.loads(Path(settings.SINGULARITY_REPOSITORY_KEY_FILE).read_text())
        keys = {version: base64.b64decode(value, validate=True) for version, value in data["keys"].items()}
        if (
            not keys
            or data["current"] not in keys
            or any(
                not isinstance(version, str) or not 1 <= len(version) <= 32 or len(key) != 32
                for version, key in keys.items()
            )
        ):
            raise ValueError
        return data["current"], keys
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise VaultError("vault_unavailable") from None


def aad(credential):
    return f"repository:{credential.pk}:{credential.owner_id}:{credential.instance_id}:{credential.kind}".encode()


def seal(credential, raw):
    if not isinstance(raw, str) or not 1 <= len(raw) <= 8192 or any(c in raw for c in "\r\n\x00"):
        raise VaultError("invalid_credential")
    version, keys = keyring()
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(keys[version]).encrypt(nonce, raw.encode(), aad(credential))
    credential.key_version = version
    credential.encrypted_material = base64.b64encode(nonce + encrypted).decode()


def unseal(credential):
    """Ciphertext copied between users or instances cannot be decrypted."""
    _, keys = keyring()
    try:
        value = base64.b64decode(credential.encrypted_material, validate=True)
        return AESGCM(keys[credential.key_version]).decrypt(value[:12], value[12:], aad(credential)).decode()
    except (KeyError, ValueError, InvalidTag, UnicodeError):
        raise VaultError("credential_unreadable") from None


def require_owner(credential, user):
    if not user.is_active or user.is_bot or credential.owner_id != user.pk:
        raise VaultError("credential_unavailable")
    if credential.revoked_at or (credential.expires_at and credential.expires_at <= timezone.now()):
        raise VaultError("credential_unavailable")
    if not credential.instance.enabled:
        raise VaultError("instance_disabled")


def selected_credential(user, repository):
    """Resolve only an explicit personal selection; never choose a fallback."""
    from .api import visible_projects

    if not user.is_active or user.is_bot or not repository.enabled or not repository.instance.enabled:
        raise VaultError("repository_unavailable")
    if (
        not visible_projects(user).filter(pk=repository.project_id).exists()
        or not ProjectMember.objects.filter(project_id=repository.project_id, member=user, is_active=True).exists()
    ):
        raise VaultError("repository_unavailable")
    selection = (
        RepositorySelection.objects.filter(owner=user, repository=repository)
        .select_related("credential__instance")
        .first()
    )
    if not selection:
        raise VaultError("select_repository_credential")
    if selection.anonymous:
        return None, None
    credential = selection.credential
    require_owner(credential, user)
    if credential.instance_id != repository.instance_id:
        raise VaultError("credential_unavailable")
    return credential, unseal(credential)


@transaction.atomic
def rotate_credentials():
    """Re-encrypt all live secrets atomically; retain old keys in backups."""
    count = 0
    current, _ = keyring()
    for credential in (
        RepositoryCredential.objects.select_for_update().filter(revoked_at__isnull=True).exclude(key_version=current)
    ):
        seal(credential, unseal(credential))
        credential.save(update_fields=["key_version", "encrypted_material", "updated_at"])
        count += 1
    return count
