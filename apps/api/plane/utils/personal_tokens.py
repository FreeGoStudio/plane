# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Shared native API and MCP personal-token validation."""

import hashlib

from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from plane.db.models import APIToken


def token_digest(raw):
    return "plane_sha256_" + hashlib.sha256(raw.encode()).hexdigest()


def valid_personal_tokens():
    return APIToken.objects.filter(
        Q(expired_at__gt=timezone.now()) | Q(expired_at__isnull=True),
        is_active=True,
        user__is_active=True,
    )


def authenticate_personal_token(raw):
    """Accept existing plaintext rows and new digest rows, never digest-as-bearer."""
    if not raw or raw.startswith("plane_sha256_"):
        raise AuthenticationFailed("Given API token is not valid")
    row = valid_personal_tokens().filter(Q(token=raw) | Q(token=token_digest(raw))).select_related("user").first()
    if row is None:
        raise AuthenticationFailed("Given API token is not valid")
    APIToken.objects.filter(pk=row.pk).update(last_used=timezone.now())
    return row
