# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Plane identity provider for explicitly registered company SSO clients."""

from functools import wraps
import json
import re
import secrets
import time
from urllib.parse import urlencode

from django.conf import settings
from django.http import Http404, JsonResponse, HttpResponseRedirect
from django.shortcuts import render
from oauth2_provider.oauth2_validators import OAuth2Validator
from oauth2_provider.views import AuthorizationView, ConnectDiscoveryInfoView
from oauth2_provider.exceptions import OAuthToolkitError
from oauth2_provider.models import get_application_model


def eligible(user):
    """Active human Plane identities may authenticate to company SSO."""
    return bool(user and user.is_authenticated and user.is_active and not user.is_bot)


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
        # Keep the complete request server-side: native next_path rejects long or
        # nested URLs. Tickets are short-lived, session-bound and single-use.
        if request.method == "GET" and "login_resume" in request.GET:
            tickets = request.session.get("company_oidc_login", {})
            saved = tickets.pop(request.GET["login_resume"], None)
            request.session["company_oidc_login"] = tickets
            if not saved or saved["expires"] < time.time():
                return JsonResponse({"error": "login_request_expired"}, status=400)
            return HttpResponseRedirect(saved["path"])
        params = request.POST if request.method == "POST" else request.GET
        company = params.get("client_id") == settings.SINGULARITY_COMPANY_OIDC_CLIENT_ID
        if company and request.method == "GET" and not request.user.is_authenticated:
            try:
                self.validate_authorization_request(request)
            except OAuthToolkitError as error:
                return self.error_response(error, application=None)
            if "none" in request.GET.get("prompt", "").split():
                return self.handle_no_permission()
            tickets = {
                k: v for k, v in request.session.get("company_oidc_login", {}).items() if v["expires"] > time.time()
            }
            tickets = dict(list(tickets.items())[-4:])
            ticket = secrets.token_urlsafe(24)
            tickets[ticket] = {"path": request.get_full_path(), "expires": time.time() + 600}
            request.session["company_oidc_login"] = tickets
            resume = request.path + "?" + urlencode({"login_resume": ticket})
            return HttpResponseRedirect("/?" + urlencode({"next_path": resume}))
        if not eligible(request.user):
            return render(request, "singularity/login.html", {"return_url": request.get_full_path()}, status=401)
        if not company_authorized(request.user, params.get("client_id")):
            from .company import request_account

            if settings.SINGULARITY_COMPANY_ENABLED:
                request_account(request.user)
            response = render(request, "singularity/company_pending.html", status=409)
            if request.method == "GET" and settings.SINGULARITY_COMPANY_ENABLED:
                from plane.db.models import CompanyAccount

                if CompanyAccount.objects.filter(
                    user=request.user, status__in=["pending", "processing", "retry"]
                ).exists():
                    response["Refresh"] = "3"
            return response
        if (
            params.get("code_challenge_method") != "S256"
            or not re.fullmatch(r"[A-Za-z0-9_-]{43}", params.get("code_challenge", ""))
            or not 1 <= len(params.get("state", "")) <= 1024
            or not 1 <= len(params.get("nonce", "")) <= 1024
        ):
            return JsonResponse({"error": "invalid_request"}, status=400)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        """Only the configured company client receives automatic authorization."""
        if request.GET.get("client_id") != settings.SINGULARITY_COMPANY_OIDC_CLIENT_ID:
            return super().get(request, *args, **kwargs)
        try:
            scopes, credentials = self.validate_authorization_request(request)
            application = get_application_model().objects.get(client_id=credentials["client_id"])
            uri, _, _, _ = self.create_authorization_response(
                request=request, scopes=" ".join(scopes), credentials=credentials, allow=True
            )
            return self.redirect(uri, application)
        except OAuthToolkitError as error:
            return self.error_response(error, application=None)


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
