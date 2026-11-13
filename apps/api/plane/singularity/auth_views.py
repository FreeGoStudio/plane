# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Personal consent and confidential, audience-restricted delegation exchange."""

import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST
from oauthlib.oauth2 import OAuth2Error

from plane.db.models import Delegation, DelegationToken
from .oauth import CLIENT_ID, SCOPES, active_tokens, digest, server


def enabled():
    if not settings.SINGULARITY_ENABLED:
        raise Http404


def private_json(data, status=200):
    response = JsonResponse(data, status=status)
    response["Cache-Control"] = "no-store"
    return response


def metadata(request):
    enabled()
    base = settings.SINGULARITY_ISSUER.rstrip("/")
    return private_json(
        {
            "issuer": base,
            "authorization_endpoint": base + "/auth/singularity/authorize/",
            "token_endpoint": base + "/auth/singularity/token/",
            "revocation_endpoint": base + "/auth/singularity/revoke/",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
            "scopes_supported": SCOPES,
            "authorization_response_iss_parameter_supported": True,
        }
    )


@require_http_methods(["GET", "POST"])
def authorize(request):
    """Consent is CSRF protected and bound to the current Plane session."""
    enabled()
    params = request.GET
    if params.get("resource") != settings.SINGULARITY_RESOURCE or params.get("code_challenge_method") != "S256":
        return private_json({"error": "invalid_request"}, 400)
    if not params.get("state") or len(params.get("state", "")) > 1024:
        return private_json({"error": "invalid_request"}, 400)
    uri = settings.SINGULARITY_ISSUER.rstrip("/") + request.get_full_path()
    try:
        scopes, credentials = server.validate_authorization_request(uri)
    except OAuth2Error:
        return private_json({"error": "invalid_request"}, 400)
    if not request.user.is_authenticated or not request.user.is_active or request.user.is_bot:
        return render(request, "singularity/login.html", {"return_url": request.get_full_path()}, status=401)
    if request.method == "GET":
        return render(request, "singularity/consent.html", {"scopes": scopes})
    if request.POST.get("decision") != "allow":
        response = HttpResponse(status=302)
        response["Location"] = (
            params["redirect_uri"]
            + "?"
            + urlencode(
                {
                    "error": "access_denied",
                    "state": params["state"],
                    "iss": settings.SINGULARITY_ISSUER,
                }
            )
        )
        return response
    with transaction.atomic():
        grant = Delegation.objects.create(user=request.user, client_id=CLIENT_ID, scopes=" ".join(scopes))
        credentials.update(user=request.user, grant=grant)
        headers, body, status = server.create_authorization_response(uri, scopes=scopes, credentials=credentials)
        headers["Location"] += "&" + urlencode({"iss": settings.SINGULARITY_ISSUER})
    response = HttpResponse(body or "", status=status, headers=headers)
    response["Cache-Control"] = "no-store"
    return response


@csrf_exempt
@require_POST
def token(request):
    enabled()
    # Every token request is bound to the single registered MCP resource.
    if request.POST.get("resource") != settings.SINGULARITY_RESOURCE:
        return private_json({"error": "invalid_target"}, 400)
    with transaction.atomic():
        headers, body, status = server.create_token_response(
            settings.SINGULARITY_ISSUER + request.path,
            http_method="POST",
            body=request.body.decode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    return HttpResponse(body, status=status, headers=headers)


@csrf_exempt
@require_POST
def revoke(request):
    enabled()
    if request.POST.get("client_id") != CLIENT_ID:
        return private_json({"error": "invalid_client"}, 400)
    value = digest(request.POST.get("token", ""))
    from django.db.models import Q

    rows = DelegationToken.objects.filter(Q(digest=value) | Q(refresh_digest=value), audience="gateway")
    Delegation.objects.filter(pk__in=rows.values("grant_id")).update(revoked_at=timezone.now())
    return private_json({})


@require_http_methods(["GET", "POST"])
def connections(request):
    enabled()
    if not request.user.is_authenticated or not request.user.is_active or request.user.is_bot:
        return render(request, "singularity/login.html", {"return_url": request.path}, status=401)
    if request.method == "POST":
        import uuid

        try:
            grant_id = uuid.UUID(request.POST.get("grant", ""))
        except ValueError:
            return private_json({"error": "invalid_request"}, 400)
        Delegation.objects.filter(pk=grant_id, user=request.user).update(revoked_at=timezone.now())
    return render(
        request,
        "singularity/connections.html",
        {
            "connections": Delegation.objects.filter(user=request.user, revoked_at__isnull=True).order_by(
                "-created_at"
            ),
        },
    )


@require_http_methods(["GET", "POST"])
def personal_tokens(request):
    """Issue a scoped, non-refreshable personal credential to its session owner.

    The plaintext appears only in the creation response. The existing grant
    revocation and audience exchange apply equally to OAuth and personal tokens.
    """
    enabled()
    if not request.user.is_authenticated or not request.user.is_active or request.user.is_bot:
        return render(request, "singularity/login.html", {"return_url": request.path}, status=401)
    context = {"scopes": SCOPES}
    if request.method == "POST":
        scopes = request.POST.getlist("scope")
        try:
            days = int(request.POST.get("days", "30"))
        except ValueError:
            return private_json({"error": "invalid_expiration"}, 400)
        if not scopes or not set(scopes) <= set(SCOPES) or not 1 <= days <= 90:
            return private_json({"error": "invalid_scope_or_expiration"}, 400)
        raw = "sgp_" + secrets.token_urlsafe(48)
        expires = timezone.now() + timedelta(days=days)
        with transaction.atomic():
            grant = Delegation.objects.create(
                user=request.user, client_id="singularity-personal-token", scopes=" ".join(sorted(set(scopes)))
            )
            DelegationToken.objects.create(
                digest=digest(raw),
                refresh_digest=digest(secrets.token_urlsafe(48)),
                grant=grant,
                audience="gateway",
                scopes=grant.scopes,
                expires_at=expires,
                refresh_expires_at=timezone.now(),
            )
        context.update(token=raw, expires=expires)
    response = render(request, "singularity/personal_tokens.html", context)
    response["Cache-Control"] = "no-store"
    # Native same-origin form POSTs must retain Origin for Django CSRF checks.
    response["Referrer-Policy"] = "same-origin"
    return response


@csrf_exempt
@require_POST
def exchange(request):
    """Only the registered Gateway may exchange a gateway token for a Plane token.

    This is a private delegation exchange, not an ordinary resource endpoint.
    User identity, grant and scopes are derived exclusively from the presented
    gateway credential. Checking on every MCP invocation makes revocation immediate.
    """
    enabled()
    secret = settings.SINGULARITY_GATEWAY_SECRET
    if not secret or not secrets.compare_digest(request.headers.get("X-Gateway-Secret", ""), secret):
        return private_json({"error": "invalid_client"}, 401)
    row = (
        active_tokens()
        .filter(
            digest=digest(request.POST.get("subject_token", "")),
            audience="gateway",
            expires_at__gt=timezone.now(),
        )
        .select_related("grant")
        .first()
    )
    if not row:
        return private_json({"error": "invalid_token"}, 401)
    if request.POST.get("inspect") == "1":
        return private_json(
            {
                "subject": str(row.grant.user_id),
                "connection_id": str(row.grant_id),
                "scope": row.scopes,
                "expires_at": int(row.expires_at.timestamp()),
            }
        )
    access, refresh = secrets.token_urlsafe(48), secrets.token_urlsafe(48)
    expires = min(row.expires_at, timezone.now() + timedelta(minutes=5))
    DelegationToken.objects.create(
        digest=digest(access),
        refresh_digest=digest(refresh),
        grant=row.grant,
        audience="plane",
        scopes=row.scopes,
        expires_at=expires,
        refresh_expires_at=expires,
    )
    return private_json(
        {
            "access_token": access,
            "refresh_token": refresh,
            "expires_in": max(0, int((expires - timezone.now()).total_seconds())),
            "connection_id": str(row.grant_id),
            "subject": str(row.grant.user_id),
            "scope": row.scopes,
        }
    )
