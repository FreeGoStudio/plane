# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""First-repository URL/consent journeys and account connection reuse."""

import json
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
from datetime import timedelta
import pytest
from django.utils import timezone
from plane.db.models import ProjectRepository, RepositoryCredential, RepositorySelection, ProjectMember
from plane.singularity.repository_add import resolve_address, available_credentials, save_oauth
from plane.singularity.repository_transport import RepositoryError
from . import test_repository_connections as fixtures
from .test_repository_connections import callback

from .test_repository_api import login, endpoint

world = fixtures.world
enabled = fixtures.enabled

pytestmark = pytest.mark.django_db


def add(client, repo, method="inspect", **extra):
    return client.post(
        endpoint(repo).replace("repositories/", "repository-add/"),
        json.dumps(
            {
                "url": "https://company.test/team/new.git",
                "purpose": "development",
                "method": method,
                **extra,
            }
        ),
        content_type="application/json",
    )


def test_address_resolves_nested_gitlab_without_network(world):
    host, path = resolve_address("https://company.test/team/sub/new.git")
    assert host == world[2].instance and path == "team/sub/new"
    for address in [
        "https://unknown.test/team/new",
        "https://company.test.evil.test/team/new",
        "https://user:secret@company.test/team/new",
        "https://company.test/team/../new",
        "https://company.test/team/new?token=secret",
    ]:
        with pytest.raises(RepositoryError):
            resolve_address(address)


def test_inspect_is_read_only_and_filters_expired_connections(world):
    alice, _, repo, credential, *_ = world
    client = login(alice)
    before = ProjectRepository.objects.count()
    result = add(client, repo)
    assert result.status_code == 200, result.content
    assert result.json()["oauth_available"] is True
    assert result.json()["credentials"][0]["id"] == str(credential.pk)
    credential.expires_at = timezone.now() - timedelta(seconds=1)
    credential.save()
    assert add(client, repo).json()["credentials"] == []
    assert ProjectRepository.objects.count() == before


def test_first_repository_oauth_add_reuses_account_and_is_idempotent(world):
    alice, _, repo, *_ = world
    client = login(alice)
    before = ProjectRepository.objects.count()
    for _ in range(2):
        response = add(client, repo, "oauth")
        assert response.status_code == 200, response.content
        assert ProjectRepository.objects.count() == before + (_ > 0)
        state = parse_qs(urlsplit(response.json()["authorization_url"]).query)["state"][0]
        with (
            patch("plane.singularity.repository_oauth.exchange", return_value={"access_token": "new-secret"}),
            patch("plane.singularity.repository_oauth.RepositoryProvider") as provider,
        ):
            provider.return_value.actor.return_value = ("42", "alice")
            provider.return_value.metadata.return_value = {
                "external_id": "222",
                "path": "team/new",
                "default_branch": "main",
            }
            result = callback(client, state, code="ok")
            assert result.status_code == 302 and "connection=connected" in result.url, result.content
        assert callback(client, state, code="replay").status_code == 400
    assert ProjectRepository.objects.count() == before + 1
    assert RepositoryCredential.objects.filter(owner=alice, kind="oauth", revoked_at__isnull=True).count() == 1
    assert (
        RepositorySelection.objects.get(repository__external_id="222", owner=alice).credential.external_actor_id == "42"
    )


def test_cancel_or_permission_loss_never_adds_repository(world):
    alice, _, repo, *_ = world
    client = login(alice)
    before = ProjectRepository.objects.count()
    response = add(client, repo, "oauth")
    state = parse_qs(urlsplit(response.json()["authorization_url"]).query)["state"][0]
    assert "connection=cancelled" in callback(client, state, error="access_denied").url
    response = add(client, repo, "oauth")
    state = parse_qs(urlsplit(response.json()["authorization_url"]).query)["state"][0]
    ProjectMember.objects.filter(project=repo.project, member=alice).update(role=15)
    assert callback(client, state, code="ok").status_code == 404
    assert ProjectRepository.objects.count() == before


@pytest.mark.parametrize("method", ["anonymous", "token", "existing"])
def test_direct_add_verifies_before_persisting(world, method):
    alice, _, repo, credential, *_ = world
    client = login(alice)
    with patch("plane.singularity.repository_add.RepositoryProvider") as provider:
        provider.return_value.actor.return_value = ("42", "alice")
        provider.return_value.metadata.return_value = {
            "external_id": "222",
            "path": "team/new",
            "default_branch": "main",
        }
        result = add(client, repo, method, credential_id=str(credential.pk), token="user-token")
        assert result.status_code == 201, result.content
        selected = RepositorySelection.objects.get(owner=alice, repository_id=result.json()["id"])
        assert selected.anonymous == (method == "anonymous")
        provider.return_value.metadata.side_effect = RepositoryError("upstream_access_denied", 403)
        before = ProjectRepository.objects.count()
        assert add(client, repo, method, credential_id=str(credential.pk), token="user-token").status_code == 403
        assert ProjectRepository.objects.count() == before


def test_oauth_duplicates_merge_references_without_merging_tokens(world):
    alice, _, repo, credential, *_ = world
    first = save_oauth(alice, repo.instance, "old", "42", "alice", None)
    duplicate = RepositoryCredential.objects.get(pk=first.pk)
    duplicate.pk = None
    duplicate.save()
    RepositorySelection.objects.filter(owner=alice, repository=repo).update(credential=first)
    assert len([c for c in available_credentials(alice) if c.kind == "oauth"]) == 1
    chosen = save_oauth(alice, repo.instance, "fresh", "42", "alice", None)
    assert RepositorySelection.objects.get(owner=alice, repository=repo).credential_id == chosen.pk
    assert RepositoryCredential.objects.filter(owner=alice, kind="oauth", revoked_at__isnull=True).count() == 1
    credential.refresh_from_db()
    assert credential.revoked_at is None


def test_github_never_lists_or_uses_gitlab_credentials(world):
    from plane.db.models import RepositoryInstance

    alice, _, repo, credential, *_ = world
    RepositoryInstance.objects.create(
        name="GitHub", provider="github", web_url="https://github.com", api_url="https://api.github.com"
    )
    client = login(alice)
    result = add(client, repo, url="https://github.com/team/new")
    assert result.status_code == 400
    assert result.json()["error"] == "unsupported_provider"
    assert (
        add(client, repo, "existing", url="https://github.com/team/new", credential_id=str(credential.pk)).status_code
        == 400
    )


def test_failed_oauth_add_leaves_no_credential_or_repository(world):
    alice, _, repo, *_ = world
    client = login(alice)
    before = (ProjectRepository.objects.count(), RepositoryCredential.objects.count())
    response = add(client, repo, "oauth")
    state = parse_qs(urlsplit(response.json()["authorization_url"]).query)["state"][0]
    with (
        patch("plane.singularity.repository_oauth.exchange", return_value={"access_token": "new-secret"}),
        patch("plane.singularity.repository_oauth.RepositoryProvider") as provider,
    ):
        provider.return_value.actor.return_value = ("42", "alice")
        provider.return_value.metadata.side_effect = RepositoryError("upstream_access_denied", 403)
        assert "connection=upstream_access_denied" in callback(client, state, code="ok").url
    assert (ProjectRepository.objects.count(), RepositoryCredential.objects.count()) == before
