# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""OAuthLib owns authorization-code/PKCE validation; storage never contains bearer secrets."""

import hashlib
from datetime import timedelta
from types import SimpleNamespace

from django.conf import settings
from django.utils import timezone
from oauthlib.oauth2 import RequestValidator, Server
from plane.db.models import DelegationCode, DelegationToken

SCOPES = ["projects:read", "workitems:read", "workitems:write"]
CLIENT_ID = "singularity-codex"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def active_tokens():
    return DelegationToken.objects.filter(revoked=False, grant__revoked_at__isnull=True, grant__user__is_active=True)


class Validator(RequestValidator):
    """Validate only the pre-registered public client and rotation-bound grants."""

    def validate_client_id(self, client_id, request, *args, **kwargs):
        if client_id != CLIENT_ID:
            return False
        request.client = SimpleNamespace(client_id=client_id)
        return True

    def client_authentication_required(self, request, *args, **kwargs):
        return False

    def authenticate_client_id(self, client_id, request, *args, **kwargs):
        return self.validate_client_id(client_id, request)

    def validate_redirect_uri(self, client_id, redirect_uri, request, *args, **kwargs):
        return redirect_uri in settings.SINGULARITY_REDIRECT_URIS

    def get_default_redirect_uri(self, client_id, request, *args, **kwargs):
        return None

    def validate_response_type(self, client_id, response_type, client, request, *args, **kwargs):
        return response_type == "code"

    def validate_grant_type(self, client_id, grant_type, client, request, *args, **kwargs):
        return grant_type in ("authorization_code", "refresh_token")

    def get_default_scopes(self, client_id, request, *args, **kwargs):
        return SCOPES[:2]

    def validate_scopes(self, client_id, scopes, client, request, *args, **kwargs):
        return bool(scopes) and set(scopes) <= set(SCOPES)

    def is_pkce_required(self, client_id, request):
        return True

    def save_authorization_code(self, client_id, code, request, *args, **kwargs):
        DelegationCode.objects.create(
            digest=digest(code["code"]),
            grant=request.grant,
            redirect_uri=request.redirect_uri,
            challenge=request.code_challenge,
            expires_at=timezone.now() + timedelta(minutes=2),
        )

    def validate_code(self, client_id, code, client, request, *args, **kwargs):
        row = (
            DelegationCode.objects.select_for_update()
            .filter(
                digest=digest(code),
                grant__client_id=client_id,
                grant__revoked_at__isnull=True,
                grant__user__is_active=True,
                expires_at__gt=timezone.now(),
            )
            .select_related("grant__user")
            .first()
        )
        if not row:
            return False
        request.grant = row.grant
        request.user = row.grant.user
        request.scopes = row.grant.scopes.split()
        request.code_row = row
        return True

    def confirm_redirect_uri(self, client_id, code, redirect_uri, client, request, *args, **kwargs):
        return request.code_row.redirect_uri == redirect_uri

    def get_code_challenge(self, code, request):
        return request.code_row.challenge

    def get_code_challenge_method(self, code, request):
        return "S256"

    def invalidate_authorization_code(self, client_id, code, request, *args, **kwargs):
        request.code_row.delete()

    def save_bearer_token(self, token, request, *args, **kwargs):
        if getattr(request, "refresh_row", None):
            self.invalidate_refresh_token(request)
        DelegationToken.objects.create(
            digest=digest(token["access_token"]),
            refresh_digest=digest(token["refresh_token"]),
            grant=request.grant,
            audience="gateway",
            scopes=token["scope"],
            expires_at=timezone.now() + timedelta(seconds=token["expires_in"]),
            refresh_expires_at=timezone.now() + timedelta(days=7),
        )

    def validate_refresh_token(self, refresh_token, client, request, *args, **kwargs):
        row = (
            active_tokens()
            .select_for_update()
            .filter(
                refresh_digest=digest(refresh_token),
                audience="gateway",
                grant__client_id=client.client_id,
                refresh_expires_at__gt=timezone.now(),
            )
            .select_related("grant__user")
            .first()
        )
        if not row:
            return False
        request.grant, request.user, request.refresh_row = row.grant, row.grant.user, row
        return True

    def get_original_scopes(self, refresh_token, request, *args, **kwargs):
        return request.refresh_row.scopes.split()

    def is_within_original_scope(self, request_scopes, refresh_token, request, *args, **kwargs):
        return set(request_scopes) <= set(request.refresh_row.scopes.split())

    def rotate_refresh_token(self, request):
        return True

    def invalidate_refresh_token(self, request):
        request.refresh_row.revoked = True
        request.refresh_row.save(update_fields=["revoked"])


server = Server(Validator(), token_expires_in=600)
