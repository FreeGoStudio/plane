# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Audience-bound delegated authentication shared by native and extension APIs."""

from django.conf import settings
from django.http import Http404
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .oauth import active_tokens, digest
from .personal_tokens import native_delegation


def enabled():
    if not settings.SINGULARITY_ENABLED:
        raise Http404


class DelegatedAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        enabled()
        raw = request.headers.get("Authorization", "")
        personal = request.headers.get("X-Api-Key")
        if personal:
            token = native_delegation(personal)
            return token.grant.user, token
        if not raw.startswith("Bearer "):
            raise AuthenticationFailed("Plane delegation required")
        token = (
            active_tokens()
            .filter(
                digest=digest(raw[7:]),
                audience="plane",
                expires_at__gt=timezone.now(),
            )
            .select_related("grant__user")
            .first()
        )
        if not token:
            token = native_delegation(raw[7:])
        if token.grant.user.is_bot and not token.grant.source_api_token:
            raise AuthenticationFailed("Plane delegation expired or revoked")
        return token.grant.user, token
