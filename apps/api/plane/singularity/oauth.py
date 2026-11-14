# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""DOT protocol/client lifecycle with a digest-only delegation storage adapter."""

import hashlib
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from oauthlib.oauth2 import Server
from oauth2_provider.oauth2_backends import OAuthLibCore
from oauth2_provider.oauth2_validators import OAuth2Validator
from oauth2_provider.views.mixins import OAuthLibMixin
from django.db.models import Q
from plane.db.models import Delegation, DelegationCode, DelegationToken
from plane.utils.personal_tokens import valid_personal_tokens

SCOPES = ["projects:read", "workitems:read", "workitems:write", "capabilities:read", "repositories:read"]
CLIENT_ID = "singularity-codex"


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def active_tokens():
    return DelegationToken.objects.filter(
        revoked=False, grant__revoked_at__isnull=True, grant__user__is_active=True
    ).filter(
        Q(grant__source_api_token__isnull=True) | Q(grant__source_api_token__in=valid_personal_tokens().values("pk"))
    )


class Validator(OAuth2Validator):
    """Validate only the pre-registered public client and rotation-bound grants."""

    def validate_client_id(self, client_id, request, *args, **kwargs):
        if client_id != CLIENT_ID or not super().validate_client_id(client_id, request, *args, **kwargs):
            return False
        return (
            request.client.client_type == request.client.CLIENT_PUBLIC
            and request.client.authorization_grant_type == request.client.GRANT_AUTHORIZATION_CODE
            and not request.client.algorithm
        )

    def authenticate_client(self, request, *args, **kwargs):
        # This registered MCP client only supports token_endpoint_auth_method=none.
        return False

    def authenticate_client_id(self, client_id, request, *args, **kwargs):
        return self.validate_client_id(client_id, request, *args, **kwargs)

    def validate_redirect_uri(self, client_id, redirect_uri, request, *args, **kwargs):
        return (
            redirect_uri in settings.SINGULARITY_REDIRECT_URIS and redirect_uri in request.client.redirect_uris.split()
        )

    def get_default_redirect_uri(self, client_id, request, *args, **kwargs):
        return None

    def validate_response_type(self, client_id, response_type, client, request, *args, **kwargs):
        return response_type == "code" and super().validate_response_type(client_id, response_type, client, request)

    def validate_grant_type(self, client_id, grant_type, client, request, *args, **kwargs):
        return grant_type in ("authorization_code", "refresh_token") and super().validate_grant_type(
            client_id, grant_type, client, request
        )

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
        deadline = request.grant.created_at + timedelta(days=30)
        token["expires_in"] = min(token["expires_in"], max(0, int((deadline - timezone.now()).total_seconds())))
        DelegationToken.objects.create(
            digest=digest(token["access_token"]),
            refresh_digest=digest(token["refresh_token"]),
            grant=request.grant,
            audience="gateway",
            scopes=token["scope"],
            expires_at=min(deadline, timezone.now() + timedelta(seconds=token["expires_in"])),
            refresh_expires_at=deadline,
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
                grant__created_at__gt=timezone.now() - timedelta(days=30),
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

    def revoke_token(self, token, token_type_hint, request, *args, **kwargs):
        """Revoke the original grant, invalidating both resource audiences."""
        value = digest(token)
        rows = DelegationToken.objects.filter(
            Q(digest=value) | Q(refresh_digest=value),
            audience="gateway",
            grant__client_id=request.client.client_id,
        )
        Delegation.objects.filter(pk__in=rows.values("grant_id")).update(revoked_at=timezone.now())


class MCPOAuthLibCore(OAuthLibCore):
    """Keep the public MCP issuer independent of proxy headers and OIDC issuer."""

    def _get_escaped_full_path(self, request):
        return settings.SINGULARITY_ISSUER.rstrip("/") + super()._get_escaped_full_path(request)


class MCPOAuthBackend(OAuthLibMixin):
    """Use DOT's backend lifecycle without enabling OIDC grants at MCP endpoints."""

    server_class = Server
    validator_class = Validator
    oauthlib_backend_class = MCPOAuthLibCore


def get_backend():
    return MCPOAuthBackend.get_oauthlib_core()
