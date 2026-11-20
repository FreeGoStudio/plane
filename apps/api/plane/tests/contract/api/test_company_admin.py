# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Administrator credential handover, crash recovery and restart contracts."""

import base64
import json
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone
from plane.singularity.company import CompanyError
from plane.singularity.company_admin import AdminCredentialStore


class GitLab:
    def __init__(self):
        self.tokens = {
            1: dict(
                id=1,
                user_id=1,
                token="bootstrap-secret",
                scopes=["api"],
                active=True,
                revoked=False,
                expires_at="2026-12-13",
            )
        }
        self.lose_response = False
        self.fail_delete = False
        self.maximum = 365
        self.admin = True

    def client(self, token):
        return SimpleNamespace(
            call=lambda method, path, **kwargs: self.call(token, method, path, **kwargs),
            session=SimpleNamespace(close=lambda: None),
        )

    def call(self, raw, method, path, **kwargs):
        own = next(t for t in self.tokens.values() if t["token"] == raw)
        if own["revoked"]:
            raise CompanyError("company_http_401")
        if path == "personal_access_tokens/self":
            return dict(own)
        if path == "user":
            return dict(id=1, is_admin=self.admin, state="active")
        if path == "application/settings":
            return {"max_personal_access_token_lifetime": self.maximum}
        if path == "users/1/personal_access_tokens":
            pk = max(self.tokens) + 1
            token = dict(kwargs["json"], id=pk, user_id=1, token=f"replacement-secret-{pk}", active=True, revoked=False)
            self.tokens[pk] = token
            if self.lose_response:
                self.lose_response = False
                raise CompanyError("company_unreachable")
            return dict(token)
        if path == "personal_access_tokens":
            return [t for t in self.tokens.values() if not t["revoked"] and t.get("name") == kwargs["params"]["search"]]
        if method == "DELETE":
            if self.fail_delete:
                raise CompanyError("company_unreachable")
            self.tokens[int(path.split("/")[-1])]["revoked"] = True
            return None
        raise AssertionError(path)


@pytest.fixture
def rotation(tmp_path, settings):
    settings.SINGULARITY_COMPANY_URL = "https://company.test"
    keys = tmp_path / "keys"
    keys.write_text(json.dumps({"current": "v1", "keys": {"v1": base64.b64encode(b"a" * 32).decode()}}))
    settings.SINGULARITY_REPOSITORY_KEY_FILE = str(keys)
    bootstrap = tmp_path / "bootstrap"
    bootstrap.write_text("bootstrap-secret")
    store = AdminCredentialStore(tmp_path / "state", bootstrap)
    remote = GitLab()
    with patch("plane.singularity.company_admin.GitLabCompanyClient", remote.client):
        yield store, remote


def test_bootstrap_encrypt_replace_revoke_restart(rotation):
    store, remote = rotation
    with store.client() as client:
        assert client.call("GET", "personal_access_tokens/self")["id"] == 2
    assert remote.tokens[1]["revoked"]
    assert "secret" not in store.path.read_text()
    store.bootstrap.unlink()
    restarted = AdminCredentialStore(store.directory, store.bootstrap)
    with restarted.client() as client:
        assert client.call("GET", "personal_access_tokens/self")["id"] == 2
    assert len(remote.tokens) == 2


def test_due_rotation_and_provider_lifetime(rotation):
    store, remote = rotation
    with store.client():
        pass
    remote.maximum = 40
    remote.tokens[2]["expires_at"] = (timezone.now().date() + timedelta(days=3)).isoformat()
    state = store.load()
    state["next_check"] = 0
    store.save(state)
    with store.client() as client:
        current = client.call("GET", "personal_access_tokens/self")
    assert current["id"] == 3 and remote.tokens[2]["revoked"]
    assert current["expires_at"] == (timezone.now().date() + timedelta(days=40)).isoformat()


def test_lost_creation_response_preserves_old_and_cleans_orphan(rotation):
    store, remote = rotation
    remote.lose_response = True
    with pytest.raises(CompanyError):
        with store.client():
            pass
    assert not remote.tokens[1]["revoked"]
    assert store.load()["pending"]
    with store.client() as client:
        assert client.call("GET", "personal_access_tokens/self")["id"] == 3
    assert remote.tokens[1]["revoked"] and remote.tokens[2]["revoked"]


def test_persistence_failure_does_not_revoke_current(rotation):
    store, remote = rotation
    save = store.save

    def fail(state):
        if state.get("managed"):
            raise OSError("disk unavailable")
        save(state)

    with patch.object(store, "save", fail), pytest.raises(OSError):
        with store.client():
            pass
    assert not remote.tokens[1]["revoked"]
    with store.client():
        pass
    assert remote.tokens[1]["revoked"] and remote.tokens[2]["revoked"]


def test_revoke_response_failure_resumes_using_durable_new_token(rotation):
    store, remote = rotation
    remote.fail_delete = True
    with pytest.raises(CompanyError):
        with store.client():
            pass
    assert store.load()["id"] == 2 and store.load()["retired"] == [1]
    remote.fail_delete = False
    store.bootstrap.unlink()
    with store.client() as client:
        assert client.call("GET", "personal_access_tokens/self")["id"] == 2
    assert remote.tokens[1]["revoked"] and len(remote.tokens) == 2


def test_corruption_never_falls_back_to_bootstrap(rotation):
    store, remote = rotation
    with store.client():
        pass
    store.path.write_text("{}")
    with pytest.raises(CompanyError, match="admin_state_unreadable"):
        with store.client():
            pass
    assert len(remote.tokens) == 2


def test_removed_admin_permission_does_not_issue(rotation):
    store, remote = rotation
    remote.admin = False
    with pytest.raises(CompanyError, match="admin_identity_invalid"):
        with store.client():
            pass
    assert len(remote.tokens) == 1


def test_instance_cipher_binding(rotation, settings):
    store, _ = rotation
    with store.client():
        pass
    settings.SINGULARITY_COMPANY_URL = "https://other.test"
    other = AdminCredentialStore(store.directory, store.bootstrap)
    with pytest.raises(CompanyError, match="admin_state_unreadable"):
        other.load()


def test_concurrent_consumers_issue_once(rotation):
    store, remote = rotation

    def consume(_):
        other = AdminCredentialStore(store.directory, store.bootstrap)
        with other.client() as client:
            return client.call("GET", "personal_access_tokens/self")["id"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(consume, range(4))) == [2] * 4
    assert len(remote.tokens) == 2


def test_revoked_admin_does_not_recreate(rotation):
    store, remote = rotation
    with store.client():
        pass
    remote.tokens[2]["revoked"] = True
    state = store.load()
    state["next_check"] = 0
    store.save(state)
    with pytest.raises(CompanyError, match="company_http_401"):
        with store.client():
            pass
    assert len(remote.tokens) == 2
