# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Expired GitLab connections recover without interactive authorization."""

from datetime import timedelta
from unittest.mock import patch
import json
import base64

import pytest
from django.utils import timezone
from plane.db.models import RepositoryCredential, RepositorySelection, ProjectRepository
from plane.singularity.vault import (
    seal_oauth,
    unseal,
    oauth_material,
    selected_credential,
    rotate_credentials,
    VaultError,
)
from plane.singularity.repository_add import save_oauth, available_credentials
from plane.singularity.repository_transport import RepositoryError
from . import test_repository_connections as fixtures
from .test_repository_api import login, endpoint
from .test_repository_connections import begin, callback

world = fixtures.world
enabled = fixtures.enabled
pytestmark = pytest.mark.django_db


def connection(world):
    alice, _, repo, *_ = world
    row = save_oauth(
        alice, repo.instance, "old-access", "42", "alice", timezone.now() - timedelta(seconds=5), "refresh-1"
    )
    RepositorySelection.objects.filter(owner=alice, repository=repo).update(credential=row)
    return row


def test_callback_keeps_refresh_encrypted_and_rotation_preserves_it(world):
    alice, _, repo, _, keyfile, keys = world
    client = login(alice)
    state = begin(client, repo)
    with (
        patch(
            "plane.singularity.repository_oauth.exchange",
            return_value={
                "access_token": "access",
                "refresh_token": "refresh-private",
                "expires_in": 7200,
            },
        ),
        patch("plane.singularity.repository_oauth.RepositoryProvider") as provider,
    ):
        provider.return_value.actor.return_value = ("42", "alice")
        assert callback(client, state, code="once").url.endswith("connection=connected")
    row = RepositorySelection.objects.get(owner=alice, repository=repo).credential
    assert "refresh-private" not in row.encrypted_material
    keys["v2"] = base64.b64encode(b"b" * 32).decode()
    keyfile.write_text(json.dumps({"current": "v2", "keys": keys}))
    rotate_credentials()
    row.refresh_from_db()
    assert unseal(row) == "access"
    assert oauth_material(row)["refresh_token"] == "refresh-private"


def test_expired_read_refreshes_twice_without_consent_and_reuses_latest_token(world):
    row = connection(world)
    alice, _, repo, *_ = world
    client = login(alice)
    url = endpoint(repo) + f"{repo.pk}/tree/"
    with (
        patch("plane.singularity.repository_oauth.token_request") as refresh,
        patch("plane.singularity.repository_api.RepositoryProvider") as provider,
    ):
        provider.return_value.directory.return_value = {"commit_sha": "a" * 40, "entries": []}
        for number in (1, 2):
            refresh.return_value = {
                "access_token": f"access-{number}",
                "refresh_token": f"refresh-{number + 1}",
                "expires_in": 7200,
            }
            assert client.get(url).status_code == 200
            assert refresh.call_args.args[2]["refresh_token"] == f"refresh-{number}"
            assert provider.call_args.args[1] == f"access-{number}"
            assert client.get(url).status_code == 200
            assert refresh.call_count == number
            RepositoryCredential.objects.filter(pk=row.pk).update(expires_at=timezone.now() - timedelta(seconds=1))


def test_old_selection_repaired_for_same_account_only(world):
    alice, bob, repo, *_ = world
    old = connection(world)
    newer = RepositoryCredential(
        owner=alice,
        instance=repo.instance,
        kind="oauth",
        external_actor_id="42",
        validated_at=timezone.now(),
        expires_at=timezone.now() + timedelta(hours=2),
    )
    seal_oauth(newer, "new-access", "new-refresh")
    newer.save()
    second = ProjectRepository.objects.create(
        project=repo.project, instance=repo.instance, external_id="2", path="team/second", purpose="reference"
    )
    RepositorySelection.objects.create(owner=alice, repository=second, credential=old)
    assert selected_credential(alice, repo)[1] == "new-access"
    assert set(RepositorySelection.objects.filter(owner=alice).values_list("credential_id", flat=True)) == {newer.pk}
    with pytest.raises(VaultError):
        selected_credential(bob, repo)


@pytest.mark.parametrize(
    "code,status",
    [("upstream_unavailable", 503), ("upstream_rate_limited", 429), ("upstream_authentication_required", 401)],
)
def test_refresh_failure_retains_tokens_and_distinguishes_network(world, code, status):
    row = connection(world)
    alice, _, repo, *_ = world
    before = row.encrypted_material
    with patch("plane.singularity.repository_oauth.token_request", side_effect=RepositoryError(code, status)):
        response = login(alice).get(endpoint(repo) + f"{repo.pk}/tree/")
    assert response.status_code == (403 if status == 401 else status)
    assert response.json()["error"] == ("repository_authorization_required" if status == 401 else code)
    row.refresh_from_db()
    assert row.encrypted_material == before and row.revoked_at is None


def test_expired_refreshable_connection_is_available_for_reuse(world):
    row = connection(world)
    assert row.pk in {c.pk for c in available_credentials(world[0], world[2].instance)}


def test_revoked_connection_does_not_refresh(world):
    row = connection(world)
    row.revoked_at = timezone.now()
    row.save()
    with patch("plane.singularity.repository_oauth.token_request") as refresh, pytest.raises(VaultError):
        selected_credential(world[0], world[2])
    refresh.assert_not_called()


@pytest.mark.django_db(transaction=True)
def test_concurrent_expired_reads_rotate_only_once(world):
    from concurrent.futures import ThreadPoolExecutor
    from django.db import close_old_connections
    import time

    connection(world)
    alice, _, repo, *_ = world

    def read():
        close_old_connections()
        try:
            return selected_credential(alice, repo)[1]
        finally:
            close_old_connections()

    def exchange(*args):
        time.sleep(0.15)
        return {"access_token": "concurrent-access", "refresh_token": "rotated-refresh", "expires_in": 7200}

    with patch("plane.singularity.repository_oauth.token_request", side_effect=exchange) as refresh:
        with ThreadPoolExecutor(max_workers=4) as pool:
            assert list(pool.map(lambda _: read(), range(4))) == ["concurrent-access"] * 4
        assert refresh.call_count == 1


def test_other_account_cannot_replace_expired_connection(world):
    alice, _, repo, *_ = world
    old = connection(world)
    save_oauth(
        alice,
        repo.instance,
        "other-access",
        "different-actor",
        "other",
        timezone.now() + timedelta(hours=2),
        "other-refresh",
    )
    with patch(
        "plane.singularity.repository_oauth.token_request", side_effect=RepositoryError("upstream_unavailable", 503)
    ) as refresh:
        with pytest.raises(RepositoryError):
            selected_credential(alice, repo)
        assert refresh.call_args.args[2]["refresh_token"] == "refresh-1"
    assert RepositorySelection.objects.get(owner=alice, repository=repo).credential_id == old.pk


def test_refresh_exchange_uses_registered_client_and_invalid_grant_is_explicit(world):
    from plane.singularity.repository_oauth import token_request

    with patch("plane.singularity.repository_oauth.RepositoryTransport") as transport:
        transport.return_value.request.return_value = {"error": "invalid_grant", "error_description": "private details"}
        with pytest.raises(RepositoryError, match="upstream_authentication_required"):
            token_request(
                world[2].instance,
                {"client_id": "app", "client_secret": "secret"},
                {"grant_type": "refresh_token", "refresh_token": "refresh"},
            )
        request = transport.return_value.request.call_args
        assert request.args == ("POST", "/oauth/token")
        assert request.kwargs["body"]["client_id"] == "app"
        assert request.kwargs["body"]["redirect_uri"] == "https://plane.test/auth/singularity/repository-callback/"
