# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Credential ownership, authenticated encryption, rotation and restore contracts."""

import base64
import json
from datetime import timedelta

import pytest
from django.utils import timezone
from plane.db.models import (
    User,
    Workspace,
    WorkspaceMember,
    Project,
    ProjectMember,
    RepositoryInstance,
    ProjectRepository,
    RepositoryCredential,
    RepositorySelection,
)
from plane.singularity.vault import VaultError, seal, unseal, selected_credential, rotate_credentials

pytestmark = pytest.mark.django_db


@pytest.fixture
def world(settings, tmp_path):
    file = tmp_path / "repository-keys.json"
    keys = {"v1": base64.b64encode(b"a" * 32).decode()}
    file.write_text(json.dumps({"current": "v1", "keys": keys}))
    settings.SINGULARITY_REPOSITORY_KEY_FILE = str(file)
    alice = User.objects.create(username="vault-a", email="a@vault.test", is_active=True)
    bob = User.objects.create(username="vault-b", email="b@vault.test", is_active=True)
    workspace = Workspace.objects.create(name="Vault", slug="vault", owner=alice)
    project = Project.objects.create(name="Vault", identifier="VLT", workspace=workspace, network=0)
    for user in (alice, bob):
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=20)
        ProjectMember.objects.create(project=project, workspace=workspace, member=user, role=20)
    host = RepositoryInstance.objects.create(
        name="Company", provider="gitlab", api_url="https://company.test/api/v4", web_url="https://company.test"
    )
    repo = ProjectRepository.objects.create(
        project=project, instance=host, external_id="1", path="team/source", purpose="development"
    )
    credential = RepositoryCredential(owner=alice, instance=host, label="Personal")
    seal(credential, "secret-material")
    credential.save()
    RepositorySelection.objects.create(owner=alice, repository=repo, credential=credential)
    return alice, bob, repo, credential, file, keys


def test_owner_cipher_binding_and_no_fallback(world):
    alice, bob, repo, credential, _, _ = world
    assert "secret-material" not in credential.encrypted_material
    assert selected_credential(alice, repo)[1] == "secret-material"
    with pytest.raises(VaultError, match="select_repository_credential"):
        selected_credential(bob, repo)
    RepositorySelection.objects.create(owner=bob, repository=repo, credential=credential)
    with pytest.raises(VaultError, match="credential_unavailable"):
        selected_credential(bob, repo)
    credential.owner = bob
    with pytest.raises(VaultError, match="credential_unreadable"):
        unseal(credential)


def test_instance_isolation_and_same_repository_name(world):
    alice, _, repo, credential, _, _ = world
    other = RepositoryInstance.objects.create(
        name="Customer", provider="gitlab", api_url="https://customer.test/api/v4", web_url="https://customer.test"
    )
    twin = ProjectRepository.objects.create(
        project=repo.project, instance=other, external_id=repo.external_id, path=repo.path, purpose="reference"
    )
    RepositorySelection.objects.create(owner=alice, repository=twin, credential=credential)
    with pytest.raises(VaultError, match="credential_unavailable"):
        selected_credential(alice, twin)
    credential.instance = other
    with pytest.raises(VaultError, match="credential_unreadable"):
        unseal(credential)


@pytest.mark.parametrize("change", ["revoked", "expired", "disabled", "removed", "instance", "repository"])
def test_next_read_rechecks_live_permissions(world, change):
    alice, _, repo, credential, _, _ = world
    assert selected_credential(alice, repo)[1]
    if change == "revoked":
        credential.revoked_at = timezone.now()
        credential.save()
    elif change == "expired":
        credential.expires_at = timezone.now() - timedelta(seconds=1)
        credential.save()
    elif change == "disabled":
        alice.is_active = False
        alice.save()
    elif change == "removed":
        ProjectMember.objects.filter(project=repo.project, member=alice).delete()
    elif change == "instance":
        repo.instance.enabled = False
        repo.instance.save()
    else:
        repo.enabled = False
        repo.save()
    with pytest.raises(VaultError):
        selected_credential(alice, repo)


def test_anonymous_must_be_explicit(world):
    alice, _, repo, credential, _, _ = world
    credential.revoked_at = timezone.now()
    credential.save()
    with pytest.raises(VaultError):
        selected_credential(alice, repo)
    RepositorySelection.objects.filter(owner=alice, repository=repo).update(credential=None, anonymous=True)
    assert selected_credential(alice, repo) == (None, None)


def test_rotation_and_backup_restore(world):
    alice, _, repo, credential, file, keys = world
    old_cipher = credential.encrypted_material
    keys["v2"] = base64.b64encode(b"b" * 32).decode()
    file.write_text(json.dumps({"current": "v2", "keys": keys}))
    assert rotate_credentials() == 1
    credential.refresh_from_db()
    assert credential.key_version == "v2" and credential.encrypted_material != old_cipher
    assert selected_credential(alice, repo)[1] == "secret-material"
    assert rotate_credentials() == 0
    # Restored old DB data remains readable with the backed-up key version.
    credential.key_version, credential.encrypted_material = "v1", old_cipher
    assert unseal(credential) == "secret-material"
    file.write_text(json.dumps({"current": "v2", "keys": {"v2": keys["v2"]}}))
    with pytest.raises(VaultError, match="credential_unreadable"):
        unseal(credential)


def test_tamper_or_missing_key_fails_closed(world):
    _, _, _, credential, file, _ = world
    credential.encrypted_material = credential.encrypted_material[:-8] + "AAAAAAAA"
    with pytest.raises(VaultError, match="credential_unreadable"):
        unseal(credential)
    file.unlink()
    with pytest.raises(VaultError, match="vault_unavailable"):
        seal(credential, "new-secret")
