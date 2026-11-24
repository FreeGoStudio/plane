# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""GitLab-only registration and legacy-provider isolation without affecting GitLab data."""

import json
from unittest.mock import patch
import pytest
from plane.db.models import RepositoryInstance, RepositorySelection
from plane.singularity.repository_oauth import oauth_config
from plane.singularity.repository_transport import RepositoryError
from plane.singularity.vault import selected_credential, VaultError
from .test_repository_api import login, endpoint, ROOT
from . import test_repository_oauth_setup as fixtures

world = fixtures.world
enabled = fixtures.enabled
admin = fixtures.admin
pytestmark = pytest.mark.django_db


def test_registration_and_setup_accept_only_gitlab(admin):
    data = {
        "name": "Legacy",
        "provider": "github",
        "web_url": "https://github.com",
        "api_url": "https://api.github.com",
    }
    assert admin.post(ROOT + "repository-hosts/", json.dumps(data), content_type="application/json").status_code == 400
    assert admin.get(fixtures.URL, {"provider": "github", "web_url": data["web_url"]}).status_code == 400
    assert fixtures.save(admin, provider="github", web_url=data["web_url"]).status_code == 400
    assert not RepositoryInstance.objects.filter(provider="github").exists()


def test_legacy_github_hidden_and_cannot_connect_or_read(admin, world):
    user, _, repo, credential, *_ = world
    host = repo.instance
    host.provider = "github"
    host.save(update_fields=["provider"])
    with patch("socket.getaddrinfo") as network:
        assert not admin.get(ROOT + "repository-hosts/").json()
        assert not admin.get(ROOT + "repository-credentials/").json()
        assert not admin.get(endpoint(repo)).json()
        connections = admin.get(endpoint(repo).replace("repositories/", "repository-connections/")).json()
        assert not connections["hosts"] and not connections["credentials"]
        assert admin.get(fixtures.URL, {"instance_id": str(host.pk)}).status_code == 404
        assert fixtures.save(admin, instance_id=str(host.pk)).status_code == 404
        for operation in ["file/?path=README.md", "tree/"]:
            assert admin.get(endpoint(repo) + f"{repo.pk}/" + operation).status_code == 404
        assert (
            admin.post(
                endpoint(repo) + f"{repo.pk}/connection/",
                json.dumps({"method": "oauth"}),
                content_type="application/json",
            ).status_code
            == 404
        )
        assert (
            admin.post(
                ROOT + f"repository-credentials/{credential.pk}/",
                json.dumps({"label": "new", "token": "secret"}),
                content_type="application/json",
            ).status_code
            == 404
        )
        with pytest.raises(RepositoryError, match="unsupported_provider"):
            oauth_config(host)
        with pytest.raises(VaultError, match="repository_unavailable"):
            selected_credential(user, repo)
        RepositorySelection.objects.filter(repository=repo).update(credential=None, anonymous=True)
        with pytest.raises(VaultError, match="repository_unavailable"):
            selected_credential(user, repo)
        network.assert_not_called()


def test_existing_gitlab_connection_still_selected_without_reauthorization(world):
    user, _, repo, credential, *_ = world
    selected, token = selected_credential(user, repo)
    assert selected.pk == credential.pk
    assert token == "secret-material"
    assert login(user).get(endpoint(repo)).json()[0]["id"] == str(repo.pk)
