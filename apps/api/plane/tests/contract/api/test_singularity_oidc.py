# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Exercise the real OIDC authorization-code exchange with Plane identities."""

import base64
import hashlib
from urllib.parse import urlencode, urlparse, parse_qs

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import Client
from oauth2_provider.models import get_application_model
from plane.db.models import User

pytestmark = pytest.mark.django_db(transaction=True)
BASE = "/auth/singularity/oidc/"
REDIRECT = "https://gitlab.company.test/users/auth/openid_connect/callback"
VERIFIER = "p" * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()


@pytest.fixture
def oidc_world(settings):
    settings.SINGULARITY_COMPANY_OIDC_CLIENT_ID = "provisioned-company-client"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings.SINGULARITY_ENABLED = True
    settings.SINGULARITY_OIDC_ENABLED = True
    settings.OAUTH2_PROVIDER = {
        **settings.OAUTH2_PROVIDER,
        "OIDC_RSA_PRIVATE_KEY": key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode(),
    }
    app = get_application_model().objects.create(
        client_id="company-gitlab",
        client_secret="test-client-secret",
        name="Company GitLab",
        client_type="confidential",
        authorization_grant_type="authorization-code",
        redirect_uris=REDIRECT,
        algorithm="RS256",
    )
    user = User.objects.create(
        email="oidc@singularity.test", username="oidc-user", is_active=True, is_email_verified=True
    )
    return user, app, key


def authorize(user, **changes):
    client = Client()
    client.force_login(user)
    params = dict(
        client_id="company-gitlab",
        response_type="code",
        redirect_uri=REDIRECT,
        scope="openid profile email",
        state="sso-state",
        nonce="sso-nonce",
        code_challenge=CHALLENGE,
        code_challenge_method="S256",
    )
    params.update(changes)
    return client, params


def test_oidc_identity_exchange_and_audience_isolation(oidc_world, settings):
    user, app, key = oidc_world
    client, params = authorize(user)
    assert client.get(BASE + "authorize/?" + urlencode(params)).status_code == 200
    response = client.post(BASE + "authorize/", {**params, "allow": "true"})
    assert response.status_code == 302, response.content
    code = parse_qs(urlparse(response["Location"]).query)["code"][0]
    response = client.post(
        BASE + "token/",
        {
            "client_id": app.client_id,
            "client_secret": "test-client-secret",
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT,
            "code_verifier": VERIFIER,
        },
    )
    assert response.status_code == 200, response.content
    tokens = response.json()
    assert "refresh_token" not in tokens
    claims = jwt.decode(
        tokens["id_token"],
        key.public_key(),
        algorithms=["RS256"],
        audience=app.client_id,
        issuer=settings.OAUTH2_PROVIDER["OIDC_ISS_ENDPOINT"],
    )
    assert claims["sub"] == str(user.pk)
    assert claims["nonce"] == "sso-nonce"
    assert claims["email"] == user.email
    identity = Client(HTTP_AUTHORIZATION="Bearer " + tokens["access_token"])
    assert identity.get(BASE + "userinfo/").json()["sub"] == str(user.pk)
    assert identity.get("/api/singularity/v1/projects/").status_code == 401
    user.is_active = False
    user.save()
    assert identity.get(BASE + "userinfo/").status_code == 401


def test_oidc_discovery_and_closed_by_default(oidc_world, settings):
    client = Client()
    response = client.get(BASE + ".well-known/openid-configuration")
    assert response.status_code == 200, response.content
    assert response.json()["issuer"] == settings.OAUTH2_PROVIDER["OIDC_ISS_ENDPOINT"]
    keys = client.get(BASE + ".well-known/jwks.json").json()["keys"]
    assert keys and all("d" not in key for key in keys)
    assert client.get(BASE + "applications/register/").status_code == 404
    settings.SINGULARITY_OIDC_ENABLED = False
    assert client.get(BASE + ".well-known/openid-configuration").status_code == 404


@pytest.mark.parametrize("field", ["is_bot", "is_email_verified", "is_active"])
def test_oidc_denies_ineligible_accounts(oidc_world, field):
    user = oidc_world[0]
    setattr(user, field, field == "is_bot")
    user.save()
    client, params = authorize(user)
    assert client.get(BASE + "authorize/?" + urlencode(params)).status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"redirect_uri": "https://attacker.test/callback"},
        {"scope": "openid workitems:write"},
        {"response_type": "token"},
        {"code_challenge": ""},
        {"code_challenge_method": "plain"},
        {"state": ""},
        {"nonce": ""},
    ],
)
def test_oidc_rejects_invalid_authorization(oidc_world, changes):
    client, params = authorize(oidc_world[0], **changes)
    response = client.get(BASE + "authorize/?" + urlencode(params))
    if response.status_code == 302:
        assert response["Location"].startswith(REDIRECT)
        assert "error=" in response["Location"]
    else:
        assert response.status_code in (200, 400)
        if response.headers.get("Content-Type", "").startswith("application/json"):
            assert response.json()["error"]
        else:
            assert response.context["error"]


def test_oidc_code_rejects_account_disabled_after_consent(oidc_world):
    user, app, _ = oidc_world
    client, params = authorize(user)
    response = client.post(BASE + "authorize/", {**params, "allow": "true"})
    code = parse_qs(urlparse(response["Location"]).query)["code"][0]
    user.is_active = False
    user.save()
    response = client.post(
        BASE + "token/",
        {
            "client_id": app.client_id,
            "client_secret": "test-client-secret",
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT,
            "code_verifier": VERIFIER,
        },
    )
    assert response.status_code == 400
    assert "access_token" not in response.json()


def test_operator_registration_keeps_secret_private_and_refuses_overwrite(tmp_path):
    from io import StringIO
    from django.core.management import call_command, CommandError
    from django.contrib.auth.hashers import check_password

    secret = "isolated-test-client-secret-" + "s" * 32
    path = tmp_path / "client-secret"
    path.write_text(secret)
    output = StringIO()
    args = dict(client_id="operator-client", redirect_uri=REDIRECT, secret_file=str(path), stdout=output)
    call_command("register_company_oidc_client", **args)
    app = get_application_model().objects.get(client_id="operator-client")
    assert secret not in output.getvalue()
    assert check_password(secret, app.client_secret)
    with pytest.raises(CommandError):
        call_command("register_company_oidc_client", **args)
    with pytest.raises(CommandError):
        call_command(
            "register_company_oidc_client",
            **{**args, "client_id": "bad-client", "redirect_uri": "https://*.company.test/callback"},
        )
