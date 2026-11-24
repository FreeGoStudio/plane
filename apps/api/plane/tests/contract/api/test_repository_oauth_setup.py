# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Administrator registration guidance, encrypted storage and authorization continuation."""

import json
from urllib.parse import parse_qs, urlsplit
import pytest
from django.utils import timezone
from plane.db.models import RepositoryInstance, RepositoryOAuthApplication
from plane.license.models import Instance, InstanceAdmin
from plane.singularity.repository_oauth import oauth_config
from plane.singularity.repository_oauth_setup import application_secret
from plane.singularity.vault import VaultError
from . import test_repository_connections as fixtures
from .test_repository_api import login, endpoint

world = fixtures.world
enabled = fixtures.enabled
pytestmark = pytest.mark.django_db
URL = "/api/singularity/v1/repository-oauth-setup/"


@pytest.fixture
def admin(world):
    instance = Instance.objects.create(
        instance_name="Test", instance_id="test", current_version="1", last_checked_at=timezone.now()
    )
    InstanceAdmin.objects.create(instance=instance, user=world[0], role=20)
    return login(world[0])


def save(client, **data):
    return client.post(
        URL,
        json.dumps({"client_id": "new-client", "client_secret": "new-secret", **data}),
        content_type="application/json",
    )


def test_existing_host_guide_save_and_authorize(admin, world):
    host = world[2].instance
    response = admin.get(URL, {"instance_id": str(host.pk)})
    assert response.status_code == 200
    assert response.json()["create_url"] == "https://company.test/-/user_settings/applications"
    assert response.json()["callback_url"] == "https://plane.test/auth/singularity/repository-callback/"
    assert response.json()["configured"] is True
    assert "server-only" not in response.content.decode()
    result = save(admin, instance_id=str(host.pk))
    assert result.status_code == 200, result.content
    assert "new-secret" not in result.content.decode()
    app = RepositoryOAuthApplication.objects.get(instance=host)
    assert "new-secret" not in app.encrypted_secret
    assert oauth_config(host) == {"client_id": "new-client", "client_secret": "new-secret"}
    host.refresh_from_db()
    assert host.api_url == "https://company.test/api/v4"
    auth = admin.post(
        endpoint(world[2]) + f"{world[2].pk}/connection/",
        json.dumps({"method": "oauth"}),
        content_type="application/json",
    )
    assert auth.status_code == 200, auth.content
    params = parse_qs(urlsplit(auth.json()["authorization_url"]).query)
    assert params["client_id"] == ["new-client"]
    assert params["scope"] == ["read_api"]
    assert "new-secret" not in auth.content.decode()


@pytest.mark.parametrize(
    "provider,site,create,api",
    [
        ("gitlab", "https://git.example.test", "/-/user_settings/applications", "https://git.example.test/api/v4"),
    ],
)
def test_new_host_guide_does_not_create_until_saved(admin, provider, site, create, api):
    data = {"provider": provider, "web_url": site}
    response = admin.get(URL, data)
    assert response.status_code == 200, response.content
    assert response.json()["create_url"] == site + create
    assert response.json()["api_url"] == api
    assert not RepositoryInstance.objects.filter(web_url=site).exists()
    result = save(admin, **data, allowed_networks=["192.168.3.56/32"])
    assert result.status_code == 200, result.content
    host = RepositoryInstance.objects.get(web_url=site)
    assert host.allowed_networks == ["192.168.3.56/32"]
    assert oauth_config(host)["client_secret"] == "new-secret"


def test_project_admin_cannot_manage_platform_secret(world):
    client = login(world[1])
    assert client.get(URL, {"instance_id": str(world[2].instance_id)}).status_code == 403
    assert save(client, instance_id=str(world[2].instance_id)).status_code == 403
    assert not RepositoryOAuthApplication.objects.exists()


def test_csrf_required(admin, world):
    assert save(login(world[0], csrf=True), instance_id=str(world[2].instance_id)).status_code == 403


@pytest.mark.parametrize(
    "extra",
    [{"allowed_networks": ["0.0.0.0/0"]}, {"web_url": "http://git.example.test"}, {"client_secret": "bad\nsecret"}],
)
def test_invalid_configuration_is_atomic(admin, extra):
    response = save(admin, **({"provider": "gitlab", "web_url": "https://git.example.test"} | extra))
    assert response.status_code in (400, 403)
    assert not RepositoryInstance.objects.filter(web_url__contains="git.example.test").exists()
    assert not RepositoryOAuthApplication.objects.exists()


def test_ciphertext_bound_to_host(admin, world):
    assert save(admin, instance_id=str(world[2].instance_id)).status_code == 200
    app = RepositoryOAuthApplication.objects.get()
    app.instance_id = "00000000-0000-0000-0000-000000000000"
    with pytest.raises(VaultError, match="credential_unreadable"):
        application_secret(app)


def test_unknown_repository_exposes_setup_only_to_platform_admin(admin, world):
    url = endpoint(world[2]).replace("repositories/", "repository-add/")
    data = json.dumps({"url": "https://git.example.test/team/app", "purpose": "development", "method": "inspect"})
    response = admin.post(url, data, content_type="application/json")
    assert response.status_code == 200, response.content
    assert response.json()["unregistered"] is True
    response = login(world[1]).post(url, data, content_type="application/json")
    assert response.status_code == 400
    assert response.json()["error"] == "repository_host_not_configured"
