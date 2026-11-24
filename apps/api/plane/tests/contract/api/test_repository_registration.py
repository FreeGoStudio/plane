# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Project registration is independent of personal GitLab authorization."""

import json
from unittest.mock import patch
import pytest
from plane.db.models import (
    RepositoryRegistration,
    ProjectRepository,
    RepositorySelection,
    RepositoryMemberGrant,
    ProjectMember,
)
from plane.singularity.repository_registration import process_registration
from plane.singularity.repository_transport import RepositoryError
from .test_repository_api import login, endpoint
from . import test_repository_management as fixtures
from .test_repository_management import link

world = fixtures.world
enabled = fixtures.enabled
managed = fixtures.managed

pytestmark = pytest.mark.django_db


def register(client, repo, path="external/source"):
    return client.post(
        endpoint(repo).replace("repositories/", "repository-add/"),
        json.dumps(
            {
                "url": "https://company.test/" + path,
                "purpose": "development",
                "method": "register",
            }
        ),
        content_type="application/json",
    )


def test_register_without_personal_access_is_durable_and_idempotent(managed):
    alice, _, repo, _ = managed
    RepositorySelection.objects.filter(owner=alice).delete()
    client = login(alice)
    before = ProjectRepository.objects.count()
    with patch("plane.singularity.repository_add.RepositoryProvider") as provider:
        first = register(client, repo)
        again = register(client, repo, "external/source.git")
    assert first.status_code == again.status_code == 202
    assert first.json()["id"] == again.json()["id"]
    assert first.json()["status"] == "pending"
    assert not first.json()["repository_id"]
    provider.assert_not_called()
    assert ProjectRepository.objects.count() == before
    assert not RepositorySelection.objects.filter(owner=alice).exists()
    listed = client.get(endpoint(repo).replace("repositories/", "repository-add/"))
    assert listed.json()[0]["id"] == first.json()["id"]


def test_platform_denial_then_retry_syncs_external_group_without_initializing(managed):
    alice, bob, repo, platform = managed
    link(alice, repo, "41")
    link(bob, repo, "42")
    client = login(alice)
    pk = register(client, repo).json()["id"]
    process_registration(pk, platform)
    pending = RepositoryRegistration.objects.get(pk=pk)
    assert pending.status == "waiting_access" and pending.repository_id is None
    assert pending.error_code == "upstream_resource_invisible"
    platform.projects["222"] = {
        "id": 222,
        "path_with_namespace": "external/source",
        "namespace": {"id": 99},
        "default_branch": "main",
    }
    platform.direct[("222", "42")] = 30  # Preserve externally assigned Developer.
    assert register(client, repo).json()["id"] == pk
    process_registration(pk, platform)
    pending.refresh_from_db()
    assert pending.status == "ready"
    assert pending.repository.external_id == "222"
    assert platform.direct[("222", "41")] == 40
    assert platform.direct[("222", "42")] == 30
    assert not RepositorySelection.objects.filter(repository=pending.repository).exists()
    assert not any(path == "/projects" or "protected_branches" in path for _, path, _ in platform.calls)
    process_registration(pk, platform)
    assert ProjectRepository.objects.filter(external_id="222").count() == 1
    pending.repository.enabled = False
    pending.repository.save()
    process_registration(pk, platform)
    pending.refresh_from_db()
    assert pending.status == "disabled"
    assert ("222", "41") not in platform.direct
    assert platform.direct[("222", "42")] == 30
    pending.repository.enabled = True
    pending.repository.save()
    process_registration(pk, platform)
    assert platform.direct[("222", "41")] == 40
    ProjectMember.objects.filter(project=repo.project, member=alice).delete()
    process_registration(pk, platform)
    assert ("222", "41") not in platform.direct
    assert platform.direct[("222", "42")] == 30


def test_metadata_access_does_not_hide_member_sync_failure(managed):
    alice, _, repo, platform = managed
    link(alice, repo, "41")
    platform.projects["222"] = {"id": 222, "path_with_namespace": "external/source"}
    pk = register(login(alice), repo).json()["id"]
    original = platform.call

    def deny_write(method, path, *args, **kwargs):
        if method != "GET":
            raise RepositoryError("upstream_access_denied", 403)
        return original(method, path, *args, **kwargs)

    platform.call = deny_write
    process_registration(pk, platform)
    row = RepositoryRegistration.objects.get(pk=pk)
    assert row.repository_id and row.status == "sync_error"
    assert RepositoryMemberGrant.objects.filter(repository=row.repository, status="error").exists()


def test_registration_requires_project_admin_and_registered_instance(managed):
    alice, bob, repo, _ = managed
    ProjectMember.objects.filter(project=repo.project, member=bob).update(role=15)
    assert register(login(bob), repo).status_code == 403
    response = login(alice).post(
        endpoint(repo).replace("repositories/", "repository-add/"),
        json.dumps(
            {
                "url": "https://unknown.test/group/repo",
                "purpose": "development",
                "method": "register",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert not RepositoryRegistration.objects.exists()


def test_personal_connect_reuses_existing_connection_without_oauth(managed):
    alice, _, repo, _ = managed
    with (
        patch("plane.singularity.repository_api.RepositoryProvider") as provider,
        patch("plane.singularity.repository_oauth.start") as start,
    ):
        response = login(alice).post(
            endpoint(repo) + f"{repo.pk}/connection/",
            json.dumps({"method": "connect"}),
            content_type="application/json",
        )
    assert response.status_code == 200 and response.json() == {"connected": True}
    provider.return_value.metadata.assert_called_once_with(repo.external_id)
    start.assert_not_called()


def test_personal_access_denial_is_not_replaced_by_platform_or_oauth(managed):
    alice, _, repo, _ = managed
    with (
        patch("plane.singularity.repository_api.RepositoryProvider") as provider,
        patch("plane.singularity.repository_oauth.start") as start,
    ):
        provider.return_value.metadata.side_effect = RepositoryError("upstream_resource_invisible", 404)
        response = login(alice).post(
            endpoint(repo) + f"{repo.pk}/connection/",
            json.dumps({"method": "connect"}),
            content_type="application/json",
        )
    assert response.status_code == 404
    start.assert_not_called()


def test_register_existing_repository_preserves_purpose_and_personal_selection(managed):
    alice, bob, repo, platform = managed
    link(alice, repo, "41")
    link(bob, repo, "42")
    repo.purpose = "documentation"
    repo.save()
    before = RepositorySelection.objects.get(owner=alice, repository=repo).credential_id
    pk = register(login(alice), repo, "team/source").json()["id"]
    process_registration(pk, platform)
    row = RepositoryRegistration.objects.get(pk=pk)
    assert row.repository_id == repo.pk
    repo.refresh_from_db()
    assert repo.purpose == "documentation"
    assert RepositorySelection.objects.get(owner=alice, repository=repo).credential_id == before


def test_unconfigured_platform_is_visible_without_waiting_for_worker(managed, settings):
    alice, _, repo, _ = managed
    settings.SINGULARITY_REPOSITORY_PROVISIONING_ENABLED = False
    response = register(login(alice), repo)
    assert response.status_code == 202
    assert response.json()["status"] == "waiting_access"
    assert response.json()["error_code"] == "repository_management_not_configured"


def test_builtin_repository_registration_preserves_creation_rights_boundary(managed):
    from .test_repository_management import initialize

    alice, bob, repo, platform = managed
    binding = initialize(managed)
    builtin = binding.documentation_repository
    link(alice, repo, "41")
    link(bob, repo, "42")
    platform.group_members["41"] = 50
    pk = register(login(alice), repo, builtin.path).json()["id"]
    process_registration(pk, platform)
    grant = RepositoryMemberGrant.objects.get(repository=builtin, user=alice)
    assert grant.error_code == "execution_identity_has_group_creation_rights"
    assert (builtin.external_id, "41") not in platform.direct
