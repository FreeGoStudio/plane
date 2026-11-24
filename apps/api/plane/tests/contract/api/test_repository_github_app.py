# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Selected repositories, minimum permissions, member ownership and token rotation."""

import json
from copy import deepcopy
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import pytest
from django.utils import timezone
from plane.db.models import RepositoryCredential, RepositoryOAuthApplication, RepositorySelection
from plane.singularity import repository_github_app as github
from plane.singularity.repository_oauth import oauth_config
from plane.singularity.repository_transport import RepositoryError
from plane.singularity.vault import oauth_material, selected_credential
from . import test_repository_oauth_setup as setup
from .test_repository_api import login, endpoint
from .test_repository_connections import callback

world = setup.world
enabled = setup.enabled
admin = setup.admin
pytestmark = pytest.mark.django_db
APP = {"id": 12, "slug": "plane-reader", "client_id": "new-client", "permissions": github.PERMISSIONS}
INSTALL = {
    "id": 34,
    "app_id": 12,
    "repository_selection": "selected",
    "suspended_at": None,
    "permissions": github.PERMISSIONS,
    "account": {"id": 56},
}
TOKEN = {
    "access_token": "ghu_personal",
    "refresh_token": "ghr_refresh",
    "expires_in": 28800,
    "refresh_token_expires_in": 15897600,
}


@pytest.fixture
def host(world, admin):
    instance = world[2].instance
    instance.provider, instance.web_url, instance.api_url = "github", "https://github.com", "https://api.github.com"
    instance.save()
    with patch.object(github.RepositoryTransport, "get", return_value=APP):
        response = setup.save(admin, instance_id=str(instance.pk), github_app_slug="plane-reader")
    assert response.status_code == 200, response.content
    world[2].instance = instance
    return instance


@pytest.fixture
def upstream():
    state = {"install": deepcopy(INSTALL), "ids": ["1", "2"]}

    def get(_http, path, params=None):
        if path == "/user/installations":
            return {"installations": [state["install"]]}
        if path == "/user/installations/34/repositories":
            return {"repositories": [{"id": int(i)} for i in state["ids"]]}
        if path == "/user":
            return {"id": 42, "login": "bob"}
        if path.startswith(("/repositories/", "/repos/")):
            return {"id": 1, "full_name": "team/source", "default_branch": "main"}
        raise AssertionError(path)

    with (
        patch.object(github.RepositoryTransport, "get", autospec=True, side_effect=get),
        patch.object(github.RepositoryTransport, "request", return_value={"token": "ghu_only_repository_1"}) as request,
    ):
        yield state, request


def connect(world, host, metadata=None):
    metadata = metadata or {"external_id": "1", "path": "team/source"}
    return github.save_connection(world[1], host, TOKEN, ("42", "bob"), metadata, oauth_config(host), INSTALL)


def test_github_authorization_and_callback_use_app_without_repo_scope(host, world, upstream):
    client, repo = login(world[1]), world[2]
    response = client.post(
        endpoint(repo) + f"{repo.pk}/connection/", json.dumps({"method": "oauth"}), content_type="application/json"
    )
    assert response.status_code == 200
    params = parse_qs(urlsplit(response.json()["authorization_url"]).query)
    assert params["scope"] == ["offline_access"]
    assert params["code_challenge_method"] == ["S256"]
    with patch("plane.singularity.repository_oauth.exchange", return_value=TOKEN):
        result = callback(client, params["state"][0], code="once")
    assert result.url.endswith("connection=connected")
    row = RepositorySelection.objects.get(owner=world[1], repository=repo).credential
    assert row.kind == "github_app" and row.github_repository_id == "1"
    assert row.github_installation_id == 34
    assert "ghu_personal" not in row.encrypted_material
    assert callback(client, params["state"][0], code="again").status_code == 400


def test_read_scopes_token_to_exact_repository_and_read_permissions(host, world, upstream):
    row = connect(world, host)
    assert github.read_token(world[1], row, "1") == "ghu_only_repository_1"
    call = upstream[1].call_args
    assert call.args == ("POST", "/applications/new-client/token/scoped")
    assert call.kwargs["body"] == {
        "access_token": "ghu_personal",
        "target_id": 56,
        "repository_ids": [1],
        "permissions": github.PERMISSIONS,
    }
    assert call.kwargs["json_body"] is True
    with pytest.raises(RepositoryError, match="github_app_connection_required"):
        github.read_token(world[1], row, "2")


@pytest.mark.parametrize(
    "change", ["unselected", "all", "suspended", "wrong_app", "write", "extra", "wrong_installation"]
)
def test_next_read_rejects_removed_or_expanded_grants(host, world, upstream, change):
    row = connect(world, host)
    state, request = upstream
    if change == "unselected":
        state["ids"] = ["2"]
    elif change == "all":
        state["install"]["repository_selection"] = "all"
    elif change == "suspended":
        state["install"]["suspended_at"] = "2026-01-01T00:00:00Z"
    elif change == "wrong_app":
        state["install"]["app_id"] = 999
    elif change == "wrong_installation":
        state["install"]["id"] = 999
    else:
        state["install"]["permissions"] = {
            **github.PERMISSIONS,
            **({"contents": "write"} if change == "write" else {"issues": "read"}),
        }
    with pytest.raises(RepositoryError):
        github.read_token(world[1], row, "1")
    request.assert_not_called()


def test_members_keep_their_own_connections_and_repository_grants(host, world, upstream):
    a = connect(world, host)
    RepositorySelection.objects.create(owner=world[1], repository=world[2], credential=a)
    b = connect(world, host, {"external_id": "2", "path": "team/other"})
    assert a.pk != b.pk
    assert RepositorySelection.objects.get(owner=world[1], repository=world[2]).credential_id == a.pk
    with pytest.raises(RepositoryError, match="github_app_connection_required"):
        github.read_token(world[0], a, "1")
    upstream[0]["ids"] = []
    with pytest.raises(RepositoryError, match="github_selected_repository_required"):
        github.read_token(world[1], a, "1")


def test_refresh_commits_before_later_permission_failure(host, world, upstream):
    row = connect(world, host)
    row.expires_at = timezone.now() - timedelta(seconds=1)
    row.save()
    upstream[0]["ids"] = []
    replacement = {**TOKEN, "access_token": "ghu_rotated", "refresh_token": "ghr_rotated"}
    with patch("plane.singularity.repository_oauth.token_request", return_value=replacement) as refresh:
        with pytest.raises(RepositoryError, match="github_selected_repository_required"):
            github.read_token(world[1], row, "1")
    refresh.assert_called_once()
    row.refresh_from_db()
    assert oauth_material(row)["refresh_token"] == "ghr_rotated"
    upstream[0]["ids"] = ["1"]
    with patch("plane.singularity.repository_oauth.token_request") as refresh:
        assert github.read_token(world[1], row, "1")
        refresh.assert_not_called()


def test_refresh_expiry_requires_reauthorization(host, world):
    row = connect(world, host)
    row.expires_at = row.refresh_expires_at = timezone.now() - timedelta(seconds=1)
    row.save()
    with patch("plane.singularity.repository_oauth.token_request") as refresh:
        with pytest.raises(RepositoryError, match="upstream_authentication_required"):
            github.read_token(world[1], row, "1")
        refresh.assert_not_called()


def test_old_credentials_and_manual_token_routes_cannot_bypass(host, world):
    alice, _, repo, old, *_ = world
    with pytest.raises(RepositoryError, match="github_app_connection_required"):
        selected_credential(alice, repo)
    client = login(alice)
    urls = [endpoint(repo) + f"{repo.pk}/connection/", "/api/singularity/v1/repository-credentials/"]
    for url in urls:
        response = client.post(
            url,
            json.dumps({"instance_id": str(host.pk), "label": "old", "token": "pat"}),
            content_type="application/json",
        )
        assert response.status_code == 403, response.content
    add = client.post(
        endpoint(repo).replace("repositories/", "repository-add/"),
        json.dumps(
            {
                "url": "https://github.com/team/source",
                "purpose": "development",
                "method": "token",
                "token": "pat",
            }
        ),
        content_type="application/json",
    )
    assert add.status_code == 403
    assert RepositoryCredential.objects.count() == 1


def test_changed_application_requires_reconnection(host, world):
    row = connect(world, host)
    RepositoryOAuthApplication.objects.filter(instance=host).update(client_id="replacement")
    with pytest.raises(RepositoryError, match="github_app_connection_required"):
        github.read_token(world[1], row, "1")


def test_configuration_checks_app_identity_and_permissions(admin, world):
    instance = world[2].instance
    instance.provider = "github"
    instance.save()
    for app in ({**APP, "client_id": "other"}, {**APP, "permissions": {**github.PERMISSIONS, "contents": "write"}}):
        with patch.object(github.RepositoryTransport, "get", return_value=app):
            response = setup.save(admin, instance_id=str(instance.pk), github_app_slug="plane-reader")
        assert response.status_code in (400, 403)
        assert not RepositoryOAuthApplication.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_github_reads_rotate_once(host, world, upstream):
    from concurrent.futures import ThreadPoolExecutor
    from django.db import close_old_connections
    from threading import Barrier

    row = connect(world, host)
    row.expires_at = timezone.now() - timedelta(seconds=1)
    row.save()
    barrier = Barrier(3)

    def read():
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return github.read_token(world[1], row, "1")
        finally:
            close_old_connections()

    with patch("plane.singularity.repository_oauth.token_request", return_value=TOKEN) as refresh:
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(read) for _ in range(3)]
            assert [future.result(timeout=15) for future in futures] == ["ghu_only_repository_1"] * 3
        refresh.assert_called_once()


def test_scoping_failure_never_falls_back_to_parent_token(host, world, upstream):
    row = connect(world, host)
    RepositorySelection.objects.create(owner=world[1], repository=world[2], credential=row)
    upstream[1].side_effect = RepositoryError("upstream_access_denied", 403)
    with pytest.raises(RepositoryError, match="upstream_access_denied"):
        selected_credential(world[1], world[2])


def test_installation_pagination_and_malformed_response_fail_closed(host):
    from unittest.mock import Mock

    http = Mock()
    http.get.side_effect = [{"installations": [{"id": i} for i in range(100)]}, {"installations": [{"id": 101}]}]
    assert len(list(github.pages(http, "/user/installations", "installations"))) == 101
    assert http.get.call_args.args[1]["page"] == 2
    http.get.side_effect = None
    http.get.return_value = {"installations": [None]}
    with pytest.raises(RepositoryError, match="invalid_upstream_response"):
        list(github.pages(http, "/user/installations", "installations"))


def test_github_bad_refresh_token_requires_consent_not_configuration_change(host):
    from plane.singularity.repository_oauth import token_request

    with patch.object(github.RepositoryTransport, "request", return_value={"error": "bad_refresh_token"}) as request:
        with pytest.raises(RepositoryError, match="upstream_authentication_required"):
            token_request(host, oauth_config(host), {"grant_type": "refresh_token", "refresh_token": "revoked"})
    assert request.call_args.args == ("POST", "/login/oauth/access_token")
