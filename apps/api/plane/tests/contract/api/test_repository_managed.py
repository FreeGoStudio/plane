# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Company PAT issuance, renewal, recovery and permission boundaries."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from django.utils import timezone
from plane.db.models import (
    CompanyAccount,
    ManagedRepositoryConnection,
    RepositorySelection,
    ProjectRepository,
    ProjectMember,
)
from plane.singularity.company import CompanyError
from plane.singularity.repository_transport import RepositoryError
from plane.singularity.repository_managed import managed_credential, process_connection, maintain_connections
from plane.singularity.repository_add import save_oauth
from plane.singularity.vault import selected_credential, unseal, VaultError
from . import test_repository_vault as fixtures
from .test_repository_api import login, endpoint

pytestmark = pytest.mark.django_db(transaction=True)
world = fixtures.world


class GitLab:
    base = "https://company.test"

    def __init__(self, user, provider):
        self.user, self.provider, self.tokens = user, provider, {}
        self.created, self.lose_response, self.revoked = 0, False, []

    def call(self, method, path, **kwargs):
        if path == "users/42":
            return {
                "id": 42,
                "username": "alice",
                "state": "active",
                "identities": [{"provider": self.provider, "extern_uid": str(self.user.pk)}],
            }
        if path == "application/settings":
            return {"max_personal_access_token_lifetime": 365}
        if path == "users/42/personal_access_tokens":
            self.created += 1
            data = kwargs["json"]
            assert data["scopes"] == ["read_api"]
            token = {
                **data,
                "id": self.created,
                "user_id": 42,
                "token": f"private-{self.created}",
                "revoked": False,
                "expired": False,
            }
            self.tokens[self.created] = token
            if self.lose_response:
                self.lose_response = False
                raise CompanyError("company_unreachable")
            return token
        if path == "personal_access_tokens":
            return [t for t in self.tokens.values() if not t["revoked"] and t["name"] == kwargs["params"]["search"]]
        pk = int(path.split("/")[-1])
        if pk not in self.tokens:
            raise CompanyError("company_http_404")
        if method == "DELETE":
            self.tokens[pk]["revoked"] = True
            self.revoked.append(pk)
            return None
        return self.tokens[pk]


@pytest.fixture
def managed(world, settings):
    alice, _, repo, *_ = world
    settings.SINGULARITY_MANAGED_REPOSITORY_TOKENS = True
    settings.SINGULARITY_COMPANY_ENABLED = True
    settings.SINGULARITY_COMPANY_URL = "https://company.test"
    settings.SINGULARITY_REPOSITORIES_ENABLED = True
    repo.instance.company_primary = True
    repo.instance.save()
    CompanyAccount.objects.update_or_create(
        user=alice, defaults={"status": "linked", "external_id": 42, "instance_url": "https://company.test"}
    )
    old = save_oauth(alice, repo.instance, "old-oauth", "42", "alice", timezone.now() - timedelta(days=1))
    RepositorySelection.objects.filter(owner=alice, repository=repo).update(credential=old)
    client = GitLab(alice, settings.SINGULARITY_COMPANY_PROVIDER)
    row = ManagedRepositoryConnection.objects.create(owner=alice, instance=repo.instance, external_actor_id="42")
    return client, row


def test_issue_encrypt_reuse_and_replace_old_oauth(world, managed):
    client, row = managed
    alice, _, repo, *_ = world
    second = ProjectRepository.objects.create(
        project=repo.project, instance=repo.instance, external_id="2", path="team/two", purpose="reference"
    )
    old = RepositorySelection.objects.get(owner=alice, repository=repo).credential
    RepositorySelection.objects.create(owner=alice, repository=second, credential=old)
    process_connection(row.pk, client)
    row.refresh_from_db()
    assert row.status == "ready" and row.credential.kind == "managed_pat"
    assert "private-1" not in row.credential.encrypted_material
    assert unseal(row.credential) == "private-1"
    assert selected_credential(alice, repo)[1] == "private-1"
    assert selected_credential(alice, second)[0].pk == row.credential_id
    process_connection(row.pk, client)
    assert client.created == 1
    assert set(RepositorySelection.objects.filter(owner=alice).values_list("credential_id", flat=True)) == {
        row.credential_id
    }


def test_first_read_queues_without_browser_or_admin_network(world, managed):
    _, row = managed
    row.delete()
    alice, _, repo, *_ = world
    with pytest.raises(RepositoryError, match="repository_connection_pending"):
        managed_credential(alice, repo, RepositorySelection.objects.get(owner=alice, repository=repo), wait_seconds=0)
    assert ManagedRepositoryConnection.objects.filter(owner=alice, instance=repo.instance).count() == 1


@pytest.mark.parametrize("expired", [False, True])
def test_expiry_renews_then_revokes_old_token(world, managed, expired):
    client, row = managed
    process_connection(row.pk, client)
    row.refresh_from_db()
    credential_id = row.credential_id
    row.credential.expires_at = timezone.now() + timedelta(days=-1 if expired else 3)
    row.credential.save()
    process_connection(row.pk, client)
    row.refresh_from_db()
    assert row.credential_id == credential_id and row.remote_token_id == 2
    assert client.revoked == [1] and row.retired_token_ids == []
    assert selected_credential(world[0], world[2])[1] == "private-2"


def test_lost_creation_response_revokes_orphan_before_retry(world, managed):
    client, row = managed
    client.lose_response = True
    process_connection(row.pk, client)
    row.refresh_from_db()
    assert row.status == "error" and row.credential_id is None and row.pending_name
    process_connection(row.pk, client)
    row.refresh_from_db()
    assert row.status == "ready" and row.remote_token_id == 2
    assert client.revoked == [1]


def test_remote_revocation_stops_without_automatic_recreation(world, managed):
    client, row = managed
    process_connection(row.pk, client)
    client.tokens[1]["revoked"] = True
    process_connection(row.pk, client)
    maintain_connections(client)
    row.refresh_from_db()
    assert row.status == "revoked" and client.created == 1
    with pytest.raises(RepositoryError, match="repository_connection_disabled"):
        selected_credential(world[0], world[2])


def test_disconnect_is_durable_and_personal_pat_untouched(world, managed):
    client, row = managed
    alice, _, repo, personal, *_ = world
    process_connection(row.pk, client)
    response = login(alice).delete(endpoint(repo) + f"{repo.pk}/connection/")
    assert response.status_code == 204
    with pytest.raises(RepositoryError, match="repository_connection_disabled"):
        selected_credential(alice, repo)
    personal.refresh_from_db()
    assert not personal.revoked_at and unseal(personal) == "secret-material"


def test_removed_member_and_other_user_cannot_read(world, managed):
    client, row = managed
    alice, bob, repo, *_ = world
    process_connection(row.pk, client)
    with pytest.raises(RepositoryError, match="repository_company_identity_required"):
        selected_credential(bob, repo)
    ProjectMember.objects.filter(member=alice, project=repo.project).delete()
    with pytest.raises(VaultError, match="repository_unavailable"):
        selected_credential(alice, repo)


def test_disabled_user_revokes_managed_token(world, managed):
    client, row = managed
    process_connection(row.pk, client)
    user = world[0]
    user.is_active = False
    user.save()
    process_connection(row.pk, client)
    row.refresh_from_db()
    assert row.status == "disabled" and client.tokens[1]["revoked"]


def test_delegated_read_uses_existing_plane_identity(world, managed):
    client, row = managed
    process_connection(row.pk, client)
    alice, _, repo, *_ = world
    url = endpoint(repo).replace("/repositories/", "/ai-repositories/") + f"{repo.pk}/tree/"
    with (
        patch(
            "plane.singularity.api.DelegatedAuthentication.authenticate",
            return_value=(alice, SimpleNamespace(scopes="repositories:read")),
        ),
        patch("plane.singularity.repository_api.RepositoryProvider") as provider,
    ):
        provider.return_value.directory.return_value = {"commit_sha": "a" * 40}
        response = login(alice).get(url)
        assert response.status_code == 200 and response.json()["commit_sha"] == "a" * 40
        assert provider.call_args.args[1] == "private-1"


def test_concurrent_workers_issue_once(world, managed):
    from concurrent.futures import ThreadPoolExecutor
    from django.db import close_old_connections

    client, row = managed

    def execute():
        close_old_connections()
        try:
            process_connection(row.pk, client)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: execute(), range(4)))
    assert client.created == 1


def test_upstream_expiry_recovers_in_same_read_without_oauth(world, managed):
    client, row = managed
    process_connection(row.pk, client)
    client.tokens[1]["expires_at"] = (timezone.now().date() - timedelta(days=1)).isoformat()
    client.tokens[1]["active"] = False
    alice, _, repo, *_ = world

    def recover(owner, credential):
        process_connection(row.pk, client)
        row.refresh_from_db()
        return row.credential

    with (
        patch("plane.singularity.repository_managed.recover_managed_read", side_effect=recover),
        patch("plane.singularity.repository_api.RepositoryProvider") as provider,
    ):
        provider.return_value.directory.side_effect = [
            RepositoryError("upstream_authentication_required", 401),
            {"commit_sha": "b" * 40},
        ]
        response = login(alice).get(endpoint(repo) + f"{repo.pk}/tree/")
        assert response.status_code == 200
        assert [call.args[1] for call in provider.call_args_list] == ["private-1", "private-2"]
    assert client.created == 2 and client.revoked == [1]


def test_transient_rotation_failure_keeps_current_token(world, managed):
    client, row = managed
    process_connection(row.pk, client)
    row.refresh_from_db()
    row.credential.expires_at = timezone.now() + timedelta(days=3)
    row.credential.save()
    with patch.object(client, "call", side_effect=CompanyError("company_unreachable")):
        process_connection(row.pk, client)
    assert selected_credential(world[0], world[2])[1] == "private-1"
    assert client.revoked == []
