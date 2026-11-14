# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Adapt native personal credentials to stable, revocation-bound delegations."""

from datetime import timedelta
from types import SimpleNamespace

from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from plane.db.models import Delegation
from plane.utils.personal_tokens import authenticate_personal_token
from .oauth import SCOPES


def native_delegation(raw):
    """Native tokens retain their full permissions; resource RBAC stays authoritative."""
    source = authenticate_personal_token(raw)
    grant, _ = Delegation.objects.get_or_create(
        source_api_token=source.pk,
        defaults={"user": source.user, "client_id": "plane-personal-token", "scopes": " ".join(SCOPES)},
    )
    if grant.revoked_at or grant.user_id != source.user_id:
        raise AuthenticationFailed("Given API token is not valid")
    return SimpleNamespace(
        grant=grant,
        grant_id=grant.pk,
        scopes=grant.scopes,
        expires_at=source.expired_at or timezone.now() + timedelta(minutes=5),
    )
