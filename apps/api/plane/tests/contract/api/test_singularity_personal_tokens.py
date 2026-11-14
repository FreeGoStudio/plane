# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Personal-token ownership, expiry and delegation contracts."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone
from plane.db.models import DelegationToken
from plane.singularity.oauth import digest
from .test_singularity import config, world, login, RESOURCE  # noqa: F401

# pytest resolves imported fixtures by name; test parameters intentionally shadow them.
# ruff: noqa: F811

pytestmark = pytest.mark.django_db(transaction=True)
URL = "/auth/singularity/personal-tokens/"


def test_personal_token_exchange_scope_and_revocation(world):
    """A personal token uses the same actor and cannot bypass grant revocation."""
    user, other, *_ = world
    client = Client()
    client.force_login(user)
    response = client.post(URL, {"scope": ["projects:read"], "days": "30"})
    assert response.status_code == 200
    raw = response.context["token"]
    row = DelegationToken.objects.get(digest=digest(raw))
    assert row.grant.user_id == user.id
    assert row.scopes == "projects:read"
    assert row.refresh_expires_at <= timezone.now()
    assert "no-store" in response["Cache-Control"]
    assert response["Referrer-Policy"] == "same-origin"
    assert raw not in client.get(URL).content.decode()
    assert raw not in client.get("/auth/singularity/connections/").content.decode()
    params = {"subject_token": raw}
    header = {"HTTP_X_GATEWAY_SECRET": "isolated-test-gateway-secret"}
    delegated = client.post("/auth/singularity/exchange/", params, **header)
    assert delegated.status_code == 200
    assert delegated.json()["subject"] == str(user.id)
    api = Client(HTTP_AUTHORIZATION="Bearer " + delegated.json()["access_token"])
    assert api.get("/api/singularity/v1/projects/").status_code == 200
    client.force_login(other)
    client.post("/auth/singularity/connections/", {"grant": str(row.grant_id)})
    assert client.post("/auth/singularity/exchange/", params, **header).status_code == 200
    client.force_login(user)
    client.post("/auth/singularity/connections/", {"grant": str(row.grant_id)})
    assert client.post("/auth/singularity/exchange/", params, **header).status_code == 401
    assert api.get("/api/singularity/v1/projects/").status_code == 401


@pytest.mark.parametrize(
    "data",
    [
        {"scope": ["admin"], "days": "30"},
        {"days": "30"},
        {"scope": ["projects:read"], "days": "91"},
        {"scope": ["projects:read"], "days": "0"},
        {"scope": ["projects:read"], "days": "bad"},
    ],
)
def test_personal_token_rejects_invalid_grants(world, data):
    client = Client()
    client.force_login(world[0])
    assert client.post(URL, data).status_code == 400
    assert not DelegationToken.objects.exists()


def test_personal_token_requires_session_csrf_and_human(world):
    assert Client().post(URL, {"scope": ["projects:read"]}).status_code == 401
    client = Client(enforce_csrf_checks=True)
    client.force_login(world[0])
    response = client.post(URL, {"scope": ["projects:read"]})
    # Plane's existing CSRF failure page returns HTTP 200. Assert rejection by
    # the security boundary rather than changing unrelated login behavior.
    assert "csrf_failure.html" in [template.name for template in response.templates]
    assert not DelegationToken.objects.exists()
    user = world[0]
    user.is_bot = True
    user.save()
    client = Client()
    client.force_login(user)
    assert client.post(URL, {"scope": ["projects:read"]}).status_code == 401


def test_exchange_cannot_extend_personal_token_expiry(world):
    client = Client()
    client.force_login(world[0])
    raw = client.post(URL, {"scope": ["projects:read"]}).context["token"]
    row = DelegationToken.objects.get(digest=digest(raw))
    row.expires_at = timezone.now() + timedelta(seconds=20)
    row.save()
    response = client.post(
        "/auth/singularity/exchange/", {"subject_token": raw}, HTTP_X_GATEWAY_SECRET="isolated-test-gateway-secret"
    )
    assert response.status_code == 200
    child = DelegationToken.objects.get(digest=digest(response.json()["access_token"]))
    assert child.expires_at <= row.expires_at


def test_oauth_refresh_cannot_slide_beyond_thirty_days(world):
    from urllib.parse import urlencode
    from plane.db.models import Delegation

    _, client, tokens, _ = login(world[0])
    row = DelegationToken.objects.get(digest=digest(tokens["access_token"]))
    created = timezone.now() - timedelta(days=29, hours=23, minutes=59)
    Delegation.objects.filter(pk=row.grant_id).update(created_at=created)
    response = client.post(
        "/auth/singularity/token/",
        urlencode(
            {
                "client_id": "singularity-codex",
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "resource": RESOURCE,
            }
        ),
        content_type="application/x-www-form-urlencoded",
    )
    assert response.status_code == 200, response.content
    refreshed = DelegationToken.objects.get(digest=digest(response.json()["access_token"]))
    deadline = created + timedelta(days=30)
    assert refreshed.refresh_expires_at == deadline
    assert refreshed.expires_at <= deadline + timedelta(seconds=1)


@pytest.mark.parametrize("company_enabled", [False, True])
def test_deactivation_permanently_revokes_sessions_and_grants(world, settings, company_enabled):
    """Reactivation must never revive pre-disable sessions or delegated credentials."""
    from plane.db.models import Session, Delegation

    settings.SINGULARITY_COMPANY_ENABLED = company_enabled
    user = world[0]
    api, client, tokens, downstream = login(user)
    other_api, other_client, _, _ = login(world[1])
    other_session_key = other_client.session.session_key
    session_key = client.session.session_key
    raw = client.post(URL, {"scope": ["projects:read"]}).context["token"]
    user.is_active = False
    user.save(update_fields=["is_active"])
    assert not Session.objects.filter(session_key=session_key).exists()
    assert not Delegation.objects.filter(user=user, revoked_at__isnull=True).exists()
    user.is_active = True
    user.save(update_fields=["is_active"])
    assert client.get(URL).status_code == 401
    assert Session.objects.filter(session_key=other_session_key).exists()
    assert other_api.get("/api/singularity/v1/me/").status_code == 200
    assert api.get("/api/singularity/v1/me/").status_code == 401
    for credential in (raw, tokens["access_token"]):
        assert (
            Client()
            .post(
                "/auth/singularity/exchange/",
                {"subject_token": credential},
                HTTP_X_GATEWAY_SECRET="isolated-test-gateway-secret",
            )
            .status_code
            == 401
        )
