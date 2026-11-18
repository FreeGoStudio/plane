# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.db import IntegrityError, transaction
from plane.db.models import (
    Project,
    ProjectMember,
    ProjectRepository,
    ProjectRepositoryBinding,
    ProjectRepositoryBindingRevision,
)
from . import test_repository_api as repository_fixtures
from .test_repository_api import login, endpoint

world = repository_fixtures.world
enabled = repository_fixtures.enabled

pytestmark = pytest.mark.django_db


def binding_url(repo):
    return endpoint(repo).replace("repositories/", "repository-bindings/")


def configure(client, repo, revision=0, **values):
    return client.patch(
        binding_url(repo), json.dumps({"expected_revision": revision, **values}), content_type="application/json"
    )


def docs(repo):
    repo.purpose = "documentation"
    repo.save()
    return repo


def test_missing_binding_never_discovers_or_creates(world):
    alice, _, repo, *_ = world
    docs(repo)
    client = login(alice)
    assert client.get(binding_url(repo)).json()["documentation_repository_id"] is None
    with patch("plane.singularity.repository_api.RepositoryProvider") as provider:
        result = client.get(endpoint(repo).replace("repositories/", "bound-repositories/documentation/"))
        assert result.status_code == 409
        assert result.json()["error"] == "project_repository_binding_required"
        provider.assert_not_called()


def test_two_slots_resolve_stable_identity_and_read_uses_selection(world):
    alice, bob, repo, *_ = world
    docs(repo)
    prototype = ProjectRepository.objects.create(
        project=repo.project, instance=repo.instance, external_id="20", path="team/storybook", purpose="prototype"
    )
    client = login(alice)
    response = configure(
        client, repo, documentation_repository_id=str(repo.pk), prototype_repository_id=str(prototype.pk)
    )
    assert response.status_code == 200, response.content
    assert response.json()["revision"] == 1
    url = endpoint(repo).replace("repositories/", "bound-repositories/documentation/")
    assert client.get(url).json()["external_id"] == repo.external_id
    with patch("plane.singularity.repository_api.RepositoryProvider") as provider:
        provider.return_value.file.return_value = {"content": "fixed document", "commit_sha": "a" * 40}
        assert client.get(url + "file/?path=requirement.md&ref=" + "a" * 40).status_code == 200
        assert provider.return_value.file.call_args.args[0].pk == repo.pk
        provider.reset_mock()
        assert login(bob).get(url + "file/").status_code == 403
        provider.assert_not_called()


def test_binding_permissions_role_cross_project_and_conflicts(world):
    alice, bob, repo, *_ = world
    client = login(alice)
    assert configure(client, repo, documentation_repository_id=str(repo.pk)).status_code == 400
    docs(repo)
    ProjectMember.objects.filter(project=repo.project, member=bob).update(role=15)
    assert configure(login(bob), repo, documentation_repository_id=str(repo.pk)).status_code == 403
    other = Project.objects.create(name="Other", identifier="OTH", workspace=repo.project.workspace)
    foreign = ProjectRepository.objects.create(
        project=other, instance=repo.instance, external_id="21", path="other/docs", purpose="documentation"
    )
    assert configure(client, repo, documentation_repository_id=str(foreign.pk)).status_code == 404
    assert configure(client, repo, documentation_repository_id=str(repo.pk)).status_code == 200
    assert configure(client, repo, documentation_repository_id=str(repo.pk)).status_code == 409
    assert configure(client, repo, 1, documentation_repository_id=str(repo.pk)).json()["revision"] == 1
    assert configure(client, repo, 1, documentation_repository_id=None).status_code == 400
    assert configure(login(alice, csrf=True), repo, 1, documentation_repository_id=str(repo.pk)).status_code == 403


def test_replacement_preserves_history_disabled_binding_fails_closed(world):
    alice, _, repo, *_ = world
    docs(repo)
    client = login(alice)
    configure(client, repo, documentation_repository_id=str(repo.pk))
    replacement = ProjectRepository.objects.create(
        project=repo.project, instance=repo.instance, external_id="22", path="team/new-docs", purpose="documentation"
    )
    assert configure(client, repo, 1, documentation_repository_id=str(replacement.pk)).status_code == 200
    history = ProjectRepositoryBindingRevision.objects.order_by("revision")
    assert history.count() == 2
    assert history[0].snapshot["documentation_repository_id"] == str(repo.pk)
    assert history[1].snapshot["documentation_repository_id"] == str(replacement.pk)
    url = endpoint(repo) + str(replacement.pk) + "/"
    assert client.patch(url, json.dumps({"purpose": "development"}), content_type="application/json").status_code == 409
    replacement.enabled = False
    replacement.save()
    response = client.get(endpoint(repo).replace("repositories/", "bound-repositories/documentation/"))
    assert response.status_code == 409
    assert response.json()["error"] == "project_repository_binding_unavailable"
    assert ProjectRepositoryBinding.objects.get(project=repo.project).documentation_repository_id == replacement.pk


def test_database_rejects_duplicate_project_slots_and_same_repository(world):
    _, _, repo, *_ = world
    ProjectRepositoryBinding.objects.create(project=repo.project, documentation_repository=repo)
    with pytest.raises(IntegrityError), transaction.atomic():
        ProjectRepositoryBinding.objects.create(project=repo.project)
    with pytest.raises(IntegrityError), transaction.atomic():
        ProjectRepositoryBinding.objects.filter(project=repo.project).update(prototype_repository=repo)


def test_delegated_scope_membership_and_no_unbound_id_bypass(world):
    alice, _, repo, *_ = world
    docs(repo)
    client = login(alice)
    configure(client, repo, documentation_repository_id=str(repo.pk))
    other = ProjectRepository.objects.create(
        project=repo.project, instance=repo.instance, external_id="30", path="other/docs", purpose="documentation"
    )
    url = endpoint(repo).replace("repositories/", "ai-bound-repositories/documentation/")
    with patch(
        "plane.singularity.api.DelegatedAuthentication.authenticate",
        return_value=(alice, SimpleNamespace(scopes="projects:read")),
    ):
        assert client.get(url).status_code == 403
    with patch(
        "plane.singularity.api.DelegatedAuthentication.authenticate",
        return_value=(alice, SimpleNamespace(scopes="repositories:read")),
    ):
        assert client.get(url).json()["repository_id"] == str(repo.pk)
        assert client.post(url, {}).status_code == 405
        bypass = endpoint(repo).replace("repositories/", "ai-repositories/") + str(other.pk) + "/file/"
        assert client.get(bypass).json()["error"] == "repository_not_project_binding"
        with patch("plane.singularity.repository_api.RepositoryProvider") as provider:
            provider.return_value.file.return_value = {"content": "document", "commit_sha": "a" * 40}
            assert client.get(url + "file/?path=test.md").status_code == 200
        ProjectMember.objects.filter(project=repo.project, member=alice).delete()
        assert client.get(url).status_code == 404


def test_executor_bot_can_resolve_but_cannot_configure(world):
    alice, _, repo, *_ = world
    docs(repo)
    client = login(alice)
    configure(client, repo, documentation_repository_id=str(repo.pk))
    alice.is_bot = True
    alice.save()
    with patch(
        "plane.singularity.api.DelegatedAuthentication.authenticate",
        return_value=(alice, SimpleNamespace(scopes="repositories:read")),
    ):
        url = endpoint(repo).replace("repositories/", "ai-bound-repositories/documentation/")
        assert client.get(url).json()["repository_id"] == str(repo.pk)
        assert client.patch(url, {}, content_type="application/json").status_code == 405
    assert configure(client, repo, 1, documentation_repository_id=str(repo.pk)).status_code == 403
