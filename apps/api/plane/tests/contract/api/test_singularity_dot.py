# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""DOT cutover contracts: explicit clients, legacy digests and grant revocation."""

from datetime import timedelta
from urllib.parse import urlencode, parse_qs, urlsplit

import pytest
from django.core.management import call_command, CommandError
from django.test import Client
from django.utils import timezone
from oauth2_provider.models import get_application_model, get_access_token_model, get_grant_model
from oauth2_provider.oauth2_backends import OAuthLibCore
from oauth2_provider.oauth2_validators import OAuth2Validator
from plane.db.models import Delegation, DelegationCode, DelegationToken
from plane.singularity.oauth import CLIENT_ID, digest, get_backend
from .test_singularity import config, world, authorize, login, CALLBACK, CHALLENGE, VERIFIER, RESOURCE  # noqa: F401

# pytest imported fixtures are resolved by name.
# ruff: noqa: F811
pytestmark = pytest.mark.django_db(transaction=True)


def post_token(client, **values):
    return client.post(
        "/auth/singularity/token/",
        urlencode({"client_id": CLIENT_ID, "resource": RESOURCE, **values}),
        content_type="application/x-www-form-urlencoded",
    )


def test_dot_backend_registration_and_no_plaintext_token_tables(world):
    assert isinstance(get_backend(), OAuthLibCore)
    assert isinstance(get_backend().server.request_validator, OAuth2Validator)
    _, _, tokens, _ = login(world[0])
    assert DelegationToken.objects.filter(digest=digest(tokens["access_token"])).exists()
    assert not get_access_token_model().objects.exists()
    assert not get_grant_model().objects.exists()
    app = get_application_model().objects.get(client_id=CLIENT_ID)
    call_command("register_mcp_oauth_client")
    assert get_application_model().objects.filter(client_id=CLIENT_ID).count() == 1
    app.delete()
    assert authorize(world[0])[1].status_code == 400
    assert post_token(Client(), grant_type="refresh_token", refresh_token=tokens["refresh_token"]).status_code >= 400


@pytest.mark.parametrize(
    "changes",
    [
        {"client_type": "confidential"},
        {"authorization_grant_type": "client-credentials"},
        {"redirect_uris": "https://wrong.example/callback"},
        {"algorithm": "RS256"},
    ],
)
def test_conflicting_registration_never_overwritten(world, changes):
    get_application_model().objects.filter(client_id=CLIENT_ID).update(**changes)
    with pytest.raises(CommandError):
        call_command("register_mcp_oauth_client")
    assert authorize(world[0])[1].status_code == 400


@pytest.mark.parametrize(
    "callback",
    [
        "http://external.example/callback",
        "http://localhost:14551/callback",
        "https://example.test/*",
        "https://user:secret@example.test/callback",
        "https://example.test/callback#fragment",
        "https://example.test/callback https://other.test/",
    ],
)
def test_registration_rejects_unsafe_callbacks(settings, callback):
    settings.SINGULARITY_REDIRECT_URIS = [callback]
    with pytest.raises(CommandError):
        call_command("register_mcp_oauth_client")


def test_pending_legacy_code_and_refresh_keep_grant_identity(world):
    # These are precisely the digest rows written by the pre-DOT adapter.
    grant = Delegation.objects.create(user=world[0], client_id=CLIENT_ID, scopes="projects:read")
    DelegationCode.objects.create(
        digest=digest("legacy-code"),
        grant=grant,
        redirect_uri=CALLBACK,
        challenge=CHALLENGE,
        expires_at=timezone.now() + timedelta(minutes=2),
    )
    client = Client()
    response = post_token(
        client, grant_type="authorization_code", code="legacy-code", redirect_uri=CALLBACK, code_verifier=VERIFIER
    )
    assert response.status_code == 200
    assert DelegationToken.objects.get(digest=digest(response.json()["access_token"])).grant_id == grant.id
    assert (
        post_token(
            client, grant_type="authorization_code", code="legacy-code", redirect_uri=CALLBACK, code_verifier=VERIFIER
        ).status_code
        == 400
    )
    row = DelegationToken.objects.create(
        digest=digest("legacy-access"),
        refresh_digest=digest("legacy-refresh"),
        grant=grant,
        audience="gateway",
        scopes="projects:read",
        expires_at=timezone.now() + timedelta(minutes=10),
        refresh_expires_at=grant.created_at + timedelta(days=30),
    )
    exchanged = client.post(
        "/auth/singularity/exchange/",
        {"subject_token": "legacy-access"},
        HTTP_X_GATEWAY_SECRET="isolated-test-gateway-secret",
    )
    assert exchanged.status_code == 200 and exchanged.json()["connection_id"] == str(grant.id)
    refreshed = post_token(client, grant_type="refresh_token", refresh_token="legacy-refresh")
    assert refreshed.status_code == 200
    row.refresh_from_db()
    assert row.revoked
    current = DelegationToken.objects.get(digest=digest(refreshed.json()["access_token"]))
    assert current.grant_id == grant.id and current.refresh_expires_at == row.refresh_expires_at
    assert post_token(client, grant_type="refresh_token", refresh_token="legacy-refresh").status_code == 400
    assert (
        client.post(
            "/auth/singularity/revoke/", {"client_id": CLIENT_ID, "token": refreshed.json()["refresh_token"]}
        ).status_code
        == 200
    )
    downstream = Client(HTTP_AUTHORIZATION="Bearer " + exchanged.json()["access_token"])
    assert downstream.get("/api/singularity/v1/me/").status_code == 401
    assert (
        post_token(client, grant_type="refresh_token", refresh_token=refreshed.json()["refresh_token"]).status_code
        == 400
    )


def test_scope_narrowing_and_issuer_stay_mcp_specific(world):
    client, auth = authorize(world[0])
    assert parse_qs(urlsplit(auth["Location"]).query)["iss"] == ["https://localhost:8444"]
    _, client, tokens, _ = login(world[0], scopes=["projects:read"])
    rejected = post_token(
        client, grant_type="refresh_token", refresh_token=tokens["refresh_token"], scope="workitems:write"
    )
    assert rejected.status_code == 400
    assert (
        post_token(
            client, grant_type="refresh_token", refresh_token=tokens["refresh_token"], scope="projects:read"
        ).status_code
        == 200
    )
    assert authorize(world[0], scopes=["openid"])[1].status_code == 400
    assert authorize(world[0], client_id="company-gitlab")[1].status_code == 400
