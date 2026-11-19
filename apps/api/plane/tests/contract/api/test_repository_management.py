# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import json
from urllib.parse import unquote
from unittest.mock import patch

import pytest
from django.db import transaction
from plane.db.models import (
    Project,
    ProjectMember,
    ProjectRepository,
    ProjectRepositoryBinding,
    ProjectRepositoryBindingRevision,
    RepositoryProvisioning,
    RepositoryMemberGrant,
    RepositoryIdentity,
    RepositoryManagementEvent,
)
from plane.singularity.repository_management import GitLabRepositoryManager, process_project, request_provisioning
from plane.singularity.repository_transport import RepositoryError
from . import test_repository_api as fixtures
from .test_repository_api import login, endpoint

world = fixtures.world
enabled = fixtures.enabled
pytestmark = pytest.mark.django_db


class FakeGitLab(GitLabRepositoryManager):
    def __init__(self, instance):
        self.instance, self.group_id = instance, "7"
        self.projects = {
            "1": {"id": 1, "namespace": {"id": 7}, "path_with_namespace": "team/source", "description": "external"}
        }
        self.protections, self.direct, self.inherited = {}, {}, {}
        self.calls = []
        self.lose_create_response = False
        self.creation_level = "maintainer"
        self.group_members = {}
        self.ignore_protection_patch = False

    def call(self, method, path, body=None, params=None):
        self.calls.append((method, path, body))
        if path == "/groups/7":
            return {"id": 7, "full_path": "team", "project_creation_level": self.creation_level}
        if path.startswith("/groups/7/members/all/"):
            level = self.group_members.get(path.split("/")[-1])
            if level is None:
                raise RepositoryError("upstream_resource_invisible", 404)
            return {"access_level": level}
        if path == "/projects" and method == "POST":
            assert body["namespace_id"] == "7" and body["visibility"] == "private"
            assert body["initialize_with_readme"] and body["merge_method"] == "ff"
            number = str(100 + len(self.projects))
            value = {
                "id": int(number),
                "namespace": {"id": 7},
                "path_with_namespace": "team/" + body["path"],
                "description": body["description"],
                "default_branch": "main",
            }
            self.projects[number] = value
            if self.lose_create_response:
                self.lose_create_response = False
                raise RepositoryError("upstream_unavailable", 503)
            return value
        parts = path.split("/")
        identifier = unquote(parts[2])
        remote = self.projects.get(identifier) or next(
            (p for p in self.projects.values() if p["path_with_namespace"] == identifier), None
        )
        if remote is None:
            raise RepositoryError("upstream_resource_invisible", 404)
        if len(parts) == 3:
            return remote
        if parts[3] == "protected_branches":
            if method == "DELETE":
                self.protections.pop(identifier, None)
                return None
            if method == "PATCH" and self.ignore_protection_patch:
                return self.protections[identifier]
            if method == "GET":
                if identifier not in self.protections:
                    raise RepositoryError("upstream_resource_invisible", 404)
                return self.protections[identifier]
            self.protections[identifier] = {
                "push_access_levels": [{"id": 1, "access_level": 0}],
                "merge_access_levels": [{"id": 2, "access_level": 40}],
            }
            return self.protections[identifier]
        if parts[3] == "members":
            if method == "GET" and len(parts) == 4:
                return [
                    {"id": int(user), "access_level": level}
                    for (project, user), level in self.direct.items()
                    if project == identifier
                ]
            user_id = str(body["user_id"]) if method == "POST" else parts[-1]
            key = (identifier, user_id)
            if method in ("POST", "PUT"):
                self.direct[key] = int(body["access_level"])
            elif method == "DELETE":
                self.direct.pop(key, None)
                return None
            level = (
                max(self.direct.get(key, 0), self.inherited.get(key, 0)) if "/all/" in path else self.direct.get(key, 0)
            )
            if not level:
                raise RepositoryError("upstream_resource_invisible", 404)
            return {"id": int(user_id), "access_level": level}
        raise AssertionError((method, path, body))


@pytest.fixture
def managed(world, settings):
    alice, bob, repo, *_ = world
    settings.SINGULARITY_REPOSITORY_PROVISIONING_ENABLED = True
    settings.SINGULARITY_REPOSITORY_MANAGEMENT_INSTANCE_ID = str(repo.instance_id)
    settings.SINGULARITY_REPOSITORY_MANAGEMENT_GROUP_ID = "7"
    client = FakeGitLab(repo.instance)
    return alice, bob, repo, client


def initialize(managed):
    alice, _, repo, client = managed
    request_provisioning(repo.project, alice)
    process_project(repo.project_id, client)
    return ProjectRepositoryBinding.objects.get(project=repo.project)


def link(user, repo, external_id):
    RepositoryIdentity.objects.create(
        owner=user, instance=repo.instance, external_id=str(external_id), method="verified-test"
    )


def test_project_creation_persists_intent_and_rollbacks_do_not_leave_work(managed):
    _, _, repo, client = managed
    project = Project.objects.create(name="Automatic", identifier="AUTO", workspace=repo.project.workspace)
    assert RepositoryProvisioning.objects.get(project=project).status == "pending"
    project.name = "Renamed"
    project.save()
    assert RepositoryProvisioning.objects.filter(project=project).count() == 1
    with pytest.raises(RuntimeError), transaction.atomic():
        failed = Project.objects.create(name="Rollback", identifier="ROLL", workspace=project.workspace)
        raise RuntimeError("rollback")
    assert not RepositoryProvisioning.objects.filter(project_id=failed.pk).exists()
    assert client.calls == []


def test_ce_ignored_protection_patch_recreates_before_binding_only_without_direct_members(managed):
    _, _, _, client = managed
    client.ignore_protection_patch = True
    current = {
        "push_access_levels": [{"id": 1, "access_level": 40}],
        "merge_access_levels": [{"id": 2, "access_level": 40}],
    }
    client.protections["1"] = current
    client.direct[("1", "11")] = 30
    with pytest.raises(RepositoryError, match="repository_protection_requires_manual_review"):
        client.protect(client.projects["1"])
    assert not any(method == "DELETE" for method, *_ in client.calls)
    client.direct.clear()
    client.protect(client.projects["1"])
    assert client.protections["1"]["push_access_levels"][0]["access_level"] == 0
    assert ("DELETE", "/projects/1/protected_branches/main", None) in client.calls


def test_native_browser_project_creation_queues_automatic_repositories(managed):
    alice, _, repo, _ = managed
    with (
        patch("plane.app.views.project.base.model_activity.delay"),
        patch("plane.app.views.project.base.base_host", return_value="http://testserver"),
    ):
        response = login(alice).post(
            f"/api/workspaces/{repo.project.workspace.slug}/projects/",
            json.dumps({"name": "Auto native", "identifier": "ANAT"}),
            content_type="application/json",
        )
    assert response.status_code == 201, response.content
    assert RepositoryProvisioning.objects.filter(project_id=response.json()["id"]).exists()


def test_response_loss_recovers_same_repositories_and_keeps_separate_execution_identity(managed):
    alice, _, repo, client = managed
    request_provisioning(repo.project, alice)
    client.lose_create_response = True
    process_project(repo.project_id, client)
    row = RepositoryProvisioning.objects.get(project=repo.project)
    assert row.status == "retry"
    assert row.slots["documentation"]["marker"]
    process_project(repo.project_id, client)
    binding = ProjectRepositoryBinding.objects.get(project=repo.project)
    assert binding.documentation_repository_id != binding.prototype_repository_id
    assert len([c for c in client.calls if c[:2] == ("POST", "/projects")]) == 2
    process_project(repo.project_id, client)
    assert len([c for c in client.calls if c[:2] == ("POST", "/projects")]) == 2
    assert ProjectRepositoryBindingRevision.objects.filter(project=repo.project).count() == 2
    assert not binding.documentation_repository.repositoryselection_set.exists()


def test_existing_same_path_without_operation_marker_is_not_adopted(managed):
    alice, _, repo, client = managed
    row = request_provisioning(repo.project, alice)
    name = f"team/plane-{repo.project_id.hex}-documentation"
    client.projects["999"] = {
        "id": 999,
        "path_with_namespace": name,
        "description": "someone else",
        "namespace": {"id": 7},
    }
    process_project(repo.project_id, client)
    row.refresh_from_db()
    assert row.status == "blocked" and row.error_code == "repository_initialization_ownership_conflict"
    assert not ProjectRepositoryBinding.objects.get(project=repo.project).documentation_repository_id
    assert not any(method != "GET" for method, *_ in client.calls)


def test_existing_manual_binding_is_never_replaced_and_unsafe_group_blocks_creation(managed):
    alice, _, repo, client = managed
    repo.purpose = "documentation"
    repo.save()
    ProjectRepositoryBinding.objects.create(project=repo.project, documentation_repository=repo)
    binding = initialize(managed)
    assert binding.documentation_repository_id == repo.pk
    assert len([c for c in client.calls if c[:2] == ("POST", "/projects")]) == 1
    client.creation_level = "developer"
    request_provisioning(repo.project, alice)
    process_project(repo.project_id, client)
    assert (
        RepositoryProvisioning.objects.get(project=repo.project).error_code == "group_project_creation_not_restricted"
    )


def test_managed_members_follow_plane_roles_and_removal_preserves_inherited_access(managed):
    alice, bob, repo, client = managed
    link(alice, repo, 11)
    link(bob, repo, 12)
    binding = initialize(managed)
    external = binding.documentation_repository.external_id
    assert client.direct[(external, "12")] == 40
    ProjectMember.objects.filter(project=repo.project, member=bob).update(role=15)
    process_project(repo.project_id, client)
    assert client.direct[(external, "12")] == 30
    client.inherited[(external, "12")] = 20
    ProjectMember.objects.filter(project=repo.project, member=bob).update(is_active=False)
    process_project(repo.project_id, client)
    assert (external, "12") not in client.direct
    grant = RepositoryMemberGrant.objects.get(repository=binding.documentation_repository, user=bob)
    assert grant.status == "inherited" and grant.effective_access == 20


def test_unverified_identity_never_grants_and_external_direct_permissions_require_adoption(managed):
    alice, bob, repo, client = managed
    link(alice, repo, 11)
    client.direct[("1", "11")] = 30
    initialize(managed)
    grant = RepositoryMemberGrant.objects.get(repository=repo, user=alice)
    assert grant.status == "unmanaged" and client.direct[("1", "11")] == 30
    assert RepositoryMemberGrant.objects.get(repository=repo, user=bob).status == "waiting_identity"
    url = endpoint(repo) + str(repo.pk) + f"/members/{alice.pk}/"
    response = login(alice).patch(
        url,
        json.dumps(
            {"expected_revision": 0, "access_override": 20, "adopt_existing": True, "expected_direct_access": 30}
        ),
        content_type="application/json",
    )
    assert response.status_code == 202, response.content
    process_project(repo.project_id, client)
    grant.refresh_from_db()
    assert grant.managed and client.direct[("1", "11")] == 20
    assert RepositoryManagementEvent.objects.filter(operation="repository_member_access_requested").exists()


def test_external_permission_change_after_adoption_request_is_not_overwritten(managed):
    alice, _, repo, client = managed
    link(alice, repo, 11)
    client.direct[("1", "11")] = 30
    initialize(managed)
    grant = RepositoryMemberGrant.objects.get(repository=repo, user=alice)
    grant.adopt_requested, grant.access_override = True, 20
    grant.save()
    client.direct[("1", "11")] = 40
    process_project(repo.project_id, client)
    grant.refresh_from_db()
    assert grant.error_code == "external_permission_changed_before_adoption"
    assert client.direct[("1", "11")] == 40


def test_member_configuration_requires_admin_csrf_revision_and_bounded_roles(managed):
    alice, bob, repo, client = managed
    initialize(managed)
    url = endpoint(repo) + str(repo.pk) + f"/members/{bob.pk}/"
    body = {"expected_revision": 0, "access_override": 30}
    assert login(alice, csrf=True).patch(url, json.dumps(body), content_type="application/json").status_code == 403
    ProjectMember.objects.filter(project=repo.project, member=bob).update(role=15)
    assert login(bob).patch(url, json.dumps(body), content_type="application/json").status_code == 403
    assert (
        login(alice)
        .patch(url, json.dumps({**body, "access_override": 50}), content_type="application/json")
        .status_code
        == 400
    )
    assert login(alice).patch(url, json.dumps(body), content_type="application/json").status_code == 202
    assert login(alice).patch(url, json.dumps(body), content_type="application/json").status_code == 409
    management_url = endpoint(repo).replace("repositories/", "repository-management/")
    assert (
        login(alice)
        .post(management_url, json.dumps({"token": "must-not-be-accepted"}), content_type="application/json")
        .status_code
        == 400
    )
    assert login(bob).post(management_url, {}, content_type="application/json").status_code == 403


def test_path_change_is_verified_and_appends_binding_history(managed):
    alice, _, repo, _ = managed
    repo.purpose = "documentation"
    repo.save()
    ProjectRepositoryBinding.objects.create(project=repo.project, documentation_repository=repo)
    url = endpoint(repo) + str(repo.pk) + "/"
    with patch("plane.singularity.repository_api.RepositoryProvider") as provider:
        provider.return_value.metadata.return_value = {
            "external_id": "1",
            "path": "team/renamed",
            "default_branch": "main",
        }
        assert (
            login(alice).patch(url, json.dumps({"path": "team/renamed"}), content_type="application/json").status_code
            == 200
        )
        provider.return_value.metadata.return_value = {
            "external_id": "99",
            "path": "team/other",
            "default_branch": "main",
        }
        response = login(alice).patch(url, json.dumps({"path": "team/other"}), content_type="application/json")
        assert response.status_code == 409
    repo.refresh_from_db()
    assert repo.path == "team/renamed"
    assert (
        ProjectRepositoryBindingRevision.objects.get(project=repo.project).snapshot["documentation"]["path"]
        == "team/renamed"
    )


def test_repository_outside_managed_group_never_receives_grants(managed):
    alice, _, repo, client = managed
    link(alice, repo, 11)
    client.projects["1"]["namespace"]["id"] = 99
    initialize(managed)
    grant = RepositoryMemberGrant.objects.get(repository=repo, user=alice)
    assert grant.error_code == "repository_outside_managed_group"
    assert not any(method != "GET" and path.startswith("/projects/1/") for method, path, _ in client.calls)


def test_execution_identity_with_group_creation_rights_is_reported_without_grants(managed):
    alice, _, repo, client = managed
    link(alice, repo, 11)
    client.group_members["11"] = 40
    initialize(managed)
    grant = RepositoryMemberGrant.objects.get(repository=repo, user=alice)
    assert grant.error_code == "execution_identity_has_group_creation_rights"
    assert not client.direct
    client.group_members["11"] = 30
    process_project(repo.project_id, client)
    assert client.direct[("1", "11")] == 40  # Project Maintainer, group Developer.


def test_manual_migration_remains_authoritative_and_reconciles_only_owned_grants(managed):
    alice, _, repo, client = managed
    link(alice, repo, 11)
    binding = initialize(managed)
    old = binding.documentation_repository
    replacement = ProjectRepository.objects.create(
        project=repo.project, instance=repo.instance, external_id="500", path="team/migrated", purpose="documentation"
    )
    client.projects["500"] = {
        "id": 500,
        "path_with_namespace": "team/migrated",
        "namespace": {"id": 7},
        "description": "existing migrated repository",
    }
    url = endpoint(repo).replace("repositories/", "repository-bindings/")
    result = login(alice).patch(
        url,
        json.dumps({"expected_revision": binding.revision, "documentation_repository_id": str(replacement.pk)}),
        content_type="application/json",
    )
    assert result.status_code == 200, result.content
    process_project(repo.project_id, client)
    binding.refresh_from_db()
    assert binding.documentation_repository_id == replacement.pk
    assert (old.external_id, "11") not in client.direct
    assert client.direct[("500", "11")] == 40
    assert len([c for c in client.calls if c[:2] == ("POST", "/projects")]) == 2
    assert old.external_id in client.projects  # Never delete an old repository during migration.


def test_ready_reconciliation_never_reports_creation(managed):
    initialize(managed)
    _, _, repo, client = managed
    with (
        patch("plane.singularity.repository_management.provision_slots") as provision,
        patch("plane.singularity.repository_management.sync_members") as sync,
    ):

        def observe(row, client):
            assert RepositoryProvisioning.objects.get(project=repo.project).status == "syncing"

        sync.side_effect = observe
        process_project(repo.project_id, client)
        provision.assert_called_once()
        assert RepositoryProvisioning.objects.get(project=repo.project).status == "ready"
        sync.side_effect = RepositoryError("upstream_unavailable", 503)
        process_project(repo.project_id, client)
        assert RepositoryProvisioning.objects.get(project=repo.project).status == "sync_error"
