# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""User journeys: on-demand consent, project membership, callback and read retry."""

import json
from urllib.parse import urlsplit, parse_qs
from unittest.mock import patch
from types import SimpleNamespace
import pytest
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from plane.db.models import ProjectMember, RepositoryCredential, RepositorySelection
from plane.singularity.repository_transport import RepositoryError
from .test_repository_api import login, endpoint
from . import test_repository_vault as fixtures

world = fixtures.world

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def enabled(settings, tmp_path, world):
    settings.SINGULARITY_REPOSITORIES_ENABLED = True
    settings.SINGULARITY_ENABLED = True
    settings.WEB_URL = "https://plane.test"
    file = tmp_path / "oauth.json"
    file.write_text(
        json.dumps({str(world[2].instance_id): {"client_id": "registered", "client_secret": "server-only"}})
    )
    settings.SINGULARITY_REPOSITORY_OAUTH_FILE = str(file)
    cache.clear()


def begin(client, repo):
    response = client.post(
        endpoint(repo) + f"{repo.pk}/connection/", json.dumps({"method": "oauth"}), content_type="application/json"
    )
    assert response.status_code == 200, response.content
    assert "server-only" not in response.content.decode()
    params = parse_qs(urlsplit(response.json()["authorization_url"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["scope"] == ["read_api"]
    return params["state"][0]


def callback(client, state, **params):
    return client.get("/auth/singularity/repository-callback/", {"state": state, **params})


def test_missing_connection_oauth_return_then_read(world):
    _, bob, repo, *_ = world
    client = login(bob)
    read = endpoint(repo) + f"{repo.pk}/file/?path=README.md"
    missing = client.get(read)
    assert missing.status_code == 403
    assert missing.json()["status"] == "authorization_required"
    assert f"/settings/projects/{repo.project_id}/repositories/" in missing.json()["authorization_url"]
    state = begin(client, repo)
    with (
        patch(
            "plane.singularity.repository_oauth.exchange",
            return_value={"access_token": "oauth-secret", "expires_in": 7200},
        ),
        patch("plane.singularity.repository_oauth.RepositoryProvider") as provider,
    ):
        provider.return_value.actor.return_value = ("42", "bob")
        result = callback(client, state, code="once")
        assert result.status_code == 302, result.content
        assert result.url.endswith("connection=connected")
        assert "oauth-secret" not in result.url
    selected = RepositorySelection.objects.get(owner=bob, repository=repo)
    assert selected.credential.kind == "oauth"
    with patch("plane.singularity.repository_api.RepositoryProvider") as provider:
        provider.return_value.file.return_value = {"content": "README", "commit_sha": "a" * 40}
        assert client.get(read).json()["content"] == "README"
        assert provider.call_args.args[1] == "oauth-secret"
    assert callback(client, state, code="again").status_code == 400


def test_callback_user_binding_cancel_and_removed_membership(world):
    alice, bob, repo, *_ = world
    a, b = login(alice), login(bob)
    state = begin(a, repo)
    assert callback(b, state, code="stolen").status_code == 400
    assert callback(a, state, error="access_denied").url.endswith("connection=cancelled")
    state = begin(a, repo)
    ProjectMember.objects.filter(project=repo.project, member=alice).delete()
    with patch("plane.singularity.repository_oauth.exchange") as exchange:
        assert callback(a, state, code="removed").status_code == 404
        exchange.assert_not_called()
    assert a.get(endpoint(repo)).status_code == 404


@pytest.mark.parametrize(
    "code,status",
    [("upstream_access_denied", 403), ("upstream_unavailable", 503), ("upstream_resource_invisible", 404)],
)
def test_callback_does_not_claim_connection_on_inaccessible_repository(world, code, status):
    _, bob, repo, *_ = world
    client = login(bob)
    state = begin(client, repo)
    with (
        patch("plane.singularity.repository_oauth.exchange", return_value={"access_token": "secret"}),
        patch("plane.singularity.repository_oauth.RepositoryProvider") as provider,
    ):
        provider.return_value.actor.return_value = ("42", "bob")
        provider.return_value.metadata.side_effect = RepositoryError(code, status)
        result = callback(client, state, code="valid")
    assert result.url.endswith("connection=" + code)
    assert not RepositorySelection.objects.filter(owner=bob, repository=repo).exists()
    assert not RepositoryCredential.objects.filter(owner=bob).exists()


def test_project_token_connection_and_csrf(world):
    alice, bob, repo, *_ = world
    url = endpoint(repo) + f"{repo.pk}/connection/"
    body = json.dumps({"label": "Mine", "token": "secret-new"})
    assert login(bob, csrf=True).post(url, body, content_type="application/json").status_code == 403
    with patch("plane.singularity.repository_api.RepositoryProvider") as provider:
        provider.return_value.actor.return_value = ("42", "bob")
        client = login(bob)
        response = client.post(url, body, content_type="application/json")
        assert response.status_code == 201, response.content
        assert "secret-new" not in response.content.decode()
        assert client.delete(url).status_code == 204
        assert RepositorySelection.objects.filter(owner=alice, repository=repo).exists()
    repo.project.network = 2
    repo.project.save()
    ProjectMember.objects.filter(project=repo.project, member=bob).delete()
    assert client.get(endpoint(repo)).status_code == 404
    assert client.post(url, body, content_type="application/json").status_code == 404


def test_upstream_errors_and_expired_credentials_are_distinct(world):
    alice, _, repo, credential, *_ = world
    client = login(alice)
    url = endpoint(repo) + f"{repo.pk}/tree/"
    with patch("plane.singularity.repository_api.RepositoryProvider") as provider:
        for code, status in [
            ("upstream_access_denied", 403),
            ("upstream_unavailable", 503),
            ("upstream_rate_limited", 429),
        ]:
            provider.return_value.directory.side_effect = RepositoryError(code, status)
            assert client.get(url).json() == {"error": code}
        provider.return_value.directory.side_effect = RepositoryError("upstream_authentication_required", 401)
        assert client.get(url).json()["status"] == "authorization_required"
    credential.expires_at = timezone.now() - timedelta(seconds=1)
    credential.save()
    assert client.get(url).json()["status"] == "authorization_required"


def test_ai_scope_and_session_only_configuration(world):
    _, bob, repo, *_ = world
    client = login(bob)
    url = endpoint(repo).replace("/repositories/", "/ai-repositories/")
    with patch(
        "plane.singularity.api.DelegatedAuthentication.authenticate",
        return_value=(bob, SimpleNamespace(scopes="projects:read")),
    ):
        assert client.get(url).status_code == 403
    with patch(
        "plane.singularity.api.DelegatedAuthentication.authenticate",
        return_value=(bob, SimpleNamespace(scopes="repositories:read")),
    ):
        assert client.get(url).json()["results"][0]["id"] == str(repo.pk)
        assert client.get(url + f"{repo.pk}/tree/").json()["status"] == "authorization_required"
        assert client.post(url, {}).status_code == 405
