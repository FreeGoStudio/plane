# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Repository API contracts using real sessions, PostgreSQL and owner isolation."""

import json
from unittest.mock import patch
import pytest
from django.core.cache import cache
from django.test import Client
from plane.db.models import RepositoryCredential, RepositoryAccessAudit, ProjectMember
from . import test_repository_vault as fixtures

world = fixtures.world

pytestmark = pytest.mark.django_db
ROOT = "/api/singularity/v1/"


@pytest.fixture(autouse=True)
def enabled(settings):
    settings.SINGULARITY_REPOSITORIES_ENABLED = True
    cache.clear()


def login(user, csrf=False):
    client = Client(enforce_csrf_checks=csrf)
    client.force_login(user)
    return client


def endpoint(repo):
    return f"{ROOT}workspaces/{repo.project.workspace.slug}/projects/{repo.project_id}/repositories/"


def test_credentials_never_read_back_secret_or_other_users_material(world):
    alice, bob, repo, credential, _, _ = world
    client = login(alice)
    with patch("plane.singularity.repository_api.RepositoryProvider") as provider:
        provider.return_value.actor.return_value = ("99", "project-bot")
        response = client.post(
            ROOT + "repository-credentials/",
            json.dumps(
                {"instance_id": str(repo.instance_id), "label": "bot identity", "token": "user-provided-secret"}
            ),
            content_type="application/json",
        )
    assert response.status_code == 201, response.content
    assert response.json()["external_actor_label"] == "project-bot"
    assert "user-provided-secret" not in response.content.decode()
    assert "encrypted_material" not in response.content.decode()
    assert not login(bob).get(ROOT + "repository-credentials/").json()
    url = ROOT + f"repository-credentials/{credential.pk}/"
    assert login(bob).get(url).status_code == 404
    assert login(bob).delete(url).status_code == 404
    assert client.delete(url).status_code == 204
    credential.refresh_from_db()
    assert credential.revoked_at and not credential.encrypted_material
    audit = json.dumps(list(RepositoryAccessAudit.objects.values()), default=str)
    assert "user-provided-secret" not in audit and "secret-material" not in audit


def test_spoofed_owner_and_cross_owner_selection_rejected(world):
    alice, bob, repo, credential, _, _ = world
    client = login(bob)
    response = client.post(
        ROOT + "repository-credentials/",
        json.dumps(
            {"instance_id": str(repo.instance_id), "label": "fake", "token": "secret", "owner_id": str(alice.pk)}
        ),
        content_type="application/json",
    )
    assert response.status_code == 400
    response = client.post(
        endpoint(repo) + f"{repo.pk}/access/",
        json.dumps({"credential_id": str(credential.pk)}),
        content_type="application/json",
    )
    assert response.status_code == 404


def test_reads_use_current_selection_and_current_membership(world):
    alice, bob, repo, credential, _, _ = world
    client = login(alice)
    url = endpoint(repo) + f"{repo.pk}/file/?path=README.md&ref=main"
    with patch("plane.singularity.repository_api.RepositoryProvider") as provider:
        provider.return_value.file.return_value = {"content": "actual untrusted text", "commit_sha": "a" * 40}
        response = client.get(url)
        assert response.status_code == 200, response.content
        assert response.json()["content"] == "actual untrusted text"
        assert response["Cache-Control"] == "no-store"
        assert response["X-Trace-ID"]
        assert provider.call_args.args[1] == "secret-material"
        provider.reset_mock()
        assert login(bob).get(url).status_code == 403
        provider.assert_not_called()
        ProjectMember.objects.filter(project=repo.project, member=alice).delete()
        assert client.get(url).status_code == 404
        provider.assert_not_called()


def test_admin_cannot_borrow_credentials_and_member_cannot_configure_repository(world):
    alice, bob, repo, credential, _, _ = world
    ProjectMember.objects.filter(project=repo.project, member=bob).update(role=15)
    body = {"instance_id": str(repo.instance_id), "path": "team/new", "purpose": "reference", "anonymous": True}
    with patch("plane.singularity.repository_api.RepositoryProvider") as provider:
        assert login(bob).post(endpoint(repo), json.dumps(body), content_type="application/json").status_code == 403
        provider.assert_not_called()
        provider.return_value.metadata.return_value = {"external_id": "2", "path": "team/new", "default_branch": "main"}
        response = login(alice).post(endpoint(repo), json.dumps(body), content_type="application/json")
        assert response.status_code == 201, response.content
    rows = login(bob).get(endpoint(repo)).json()
    assert all(row["credential_id"] is None and not row["anonymous"] for row in rows)
    assert login(alice).post(ROOT + "repository-hosts/", {}, content_type="application/json").status_code == 403


def test_csrf_disabled_account_and_feature_flag(world, settings):
    alice, _, repo, credential, _, _ = world
    assert login(alice, csrf=True).delete(ROOT + f"repository-credentials/{credential.pk}/").status_code == 403
    client = login(alice)
    alice.is_active = False
    alice.save()
    assert client.get(endpoint(repo)).status_code == 401
    settings.SINGULARITY_REPOSITORIES_ENABLED = False
    assert client.get(endpoint(repo)).status_code == 404


def test_replace_credential_and_revocation_blocks_following_read(world):
    alice, _, repo, credential, _, _ = world
    client = login(alice)
    url = ROOT + f"repository-credentials/{credential.pk}/"
    with patch("plane.singularity.repository_api.RepositoryProvider") as provider:
        provider.return_value.actor.return_value = ("2", "real-user")
        assert (
            client.post(
                url, json.dumps({"label": "replacement", "token": "new-secret"}), content_type="application/json"
            ).status_code
            == 200
        )
        assert client.delete(url).status_code == 204
        provider.reset_mock()
        assert client.get(endpoint(repo) + f"{repo.pk}/tree/").status_code == 403
        provider.assert_not_called()
    assert RepositoryCredential.objects.get(pk=credential.pk).encrypted_material == ""
