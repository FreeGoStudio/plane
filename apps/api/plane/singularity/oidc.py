# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Plane identity provider for explicitly registered company SSO clients."""

from functools import wraps
import json
import re

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import render
from oauth2_provider.oauth2_validators import OAuth2Validator
from oauth2_provider.views import AuthorizationView, ConnectDiscoveryInfoView


def eligible(user):
    """Only verified, active human identities may authenticate to company SSO."""
    return bool(user and user.is_authenticated and user.is_active and user.is_email_verified and not user.is_bot)


def company_authorized(user, client_id):
    if client_id != settings.SINGULARITY_COMPANY_OIDC_CLIENT_ID:
        return True
    if not settings.SINGULARITY_COMPANY_ENABLED:
        return False
    from .company import linked

    return linked(user)


def oidc_enabled(view):
    """Keep all OIDC endpoints unavailable until a signing key is configured."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not settings.SINGULARITY_ENABLED or not settings.SINGULARITY_OIDC_ENABLED:
            raise Http404
        if not settings.OAUTH2_PROVIDER.get("OIDC_RSA_PRIVATE_KEY"):
            raise Http404
        response = view(request, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    return wrapped


class PlaneOIDCValidator(OAuth2Validator):
    """Apply current Plane account state and separate SSO from MCP authorization."""

    def validate_grant_type(self, client_id, grant_type, client, request, *args, **kwargs):
        return (
            grant_type == "authorization_code"
            and client.client_type == "confidential"
            and client.algorithm == "RS256"
            and super().validate_grant_type(client_id, grant_type, client, request, *args, **kwargs)
        )

    def validate_scopes(self, client_id, scopes, client, request, *args, **kwargs):
        return "openid" in scopes and set(scopes) <= {"openid", "profile", "email"}

    def validate_code(self, client_id, code, client, request, *args, **kwargs):
        return (
            super().validate_code(client_id, code, client, request, *args, **kwargs)
            and eligible(request.user)
            and company_authorized(request.user, client_id)
        )

    def validate_bearer_token(self, token, scopes, request):
        return (
            super().validate_bearer_token(token, scopes, request)
            and eligible(request.user)
            and company_authorized(request.user, request.client.client_id)
        )

    def save_bearer_token(self, token, request, *args, **kwargs):
        """SSO establishes a browser identity; it does not issue offline access."""
        token.pop("refresh_token", None)
        return super().save_bearer_token(token, request, *args, **kwargs)

    def get_additional_claims(self, request):
        claims = {}
        if "email" in request.scopes:
            claims.update(email=request.user.email, email_verified=request.user.is_email_verified)
        if "profile" in request.scopes:
            claims.update(
                name=request.user.display_name or request.user.first_name,
                preferred_username="plane_" + request.user.pk.hex,
            )
        return claims


class PlaneAuthorizationView(AuthorizationView):
    template_name = "singularity/oidc_consent.html"

    def dispatch(self, request, *args, **kwargs):
        if not eligible(request.user):
            return render(request, "singularity/login.html", {"return_url": request.get_full_path()}, status=401)
        params = request.POST if request.method == "POST" else request.GET
        if not company_authorized(request.user, params.get("client_id")):
            from .company import request_account

            if settings.SINGULARITY_COMPANY_ENABLED:
                request_account(request.user)
            return render(request, "singularity/company_pending.html", status=409)
        if (
            params.get("code_challenge_method") != "S256"
            or not re.fullmatch(r"[A-Za-z0-9_-]{43}", params.get("code_challenge", ""))
            or not 1 <= len(params.get("state", "")) <= 1024
            or not 1 <= len(params.get("nonce", "")) <= 1024
        ):
            return JsonResponse({"error": "invalid_request"}, status=400)
        return super().dispatch(request, *args, **kwargs)


class PlaneDiscoveryView(ConnectDiscoveryInfoView):
    """Advertise only the protocol modes accepted by Plane's registered clients."""

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        data = json.loads(response.content)
        data.update(
            response_types_supported=["code"],
            grant_types_supported=["authorization_code"],
            code_challenge_methods_supported=["S256"],
            id_token_signing_alg_values_supported=["RS256"],
        )
        response.content = json.dumps(data)
        return response
