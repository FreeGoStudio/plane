# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""One native credential, current permissions and immediate downstream revocation."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.exceptions import AuthenticationFailed

from plane.db.models import APIToken, DelegationToken, ProjectMember
from plane.api.middleware.api_authentication import APIKeyAuthentication
from plane.app.middleware.api_authentication import APIKeyAuthentication as AppAuthentication
from plane.singularity.oauth import SCOPES, digest
from .test_singularity import config, world  # noqa: F401

# ruff: noqa: F811
pytestmark = pytest.mark.django_db(transaction=True)


def issue(user):
    client = APIClient()
    client.force_authenticate(user)
    response = client.post("/api/users/api-tokens/", {"label": "API and MCP"}, format="json")
    assert response.status_code == 201
    return client, response.json()


def exchange(raw, **extra):
    return Client().post(
        "/auth/singularity/exchange/",
        {"subject_token": raw, **extra},
        HTTP_X_GATEWAY_SECRET="isolated-test-gateway-secret",
    )


def test_native_creation_same_actor_permissions_and_secret_not_read_back(world):
    client, data = issue(world[0])
    raw = data["token"]
    stored = APIToken.objects.get(pk=data["id"])
    assert stored.token != raw
    for authenticator in (APIKeyAuthentication(), AppAuthentication()):
        assert authenticator.validate_api_token(raw)[0] == world[0]
        with pytest.raises(AuthenticationFailed):
            authenticator.validate_api_token(stored.token)
    for response in (
        client.get("/api/users/api-tokens/"),
        client.patch(f"/api/users/api-tokens/{data['id']}/", {"label": "renamed"}, format="json"),
    ):
        assert raw not in response.content.decode()
        assert stored.token not in response.content.decode()
    downstream = exchange(raw).json()
    assert set(downstream["scope"].split()) == set(SCOPES)
    assert downstream["subject"] == str(world[0].pk)
    assert exchange(raw, inspect="1").json()["connection_id"] == downstream["connection_id"]
    for header in (
        {"HTTP_X_API_KEY": raw},
        {"HTTP_AUTHORIZATION": "Bearer " + raw},
        {"HTTP_AUTHORIZATION": "Bearer " + downstream["access_token"]},
    ):
        assert Client(**header).get("/api/singularity/v1/projects/").status_code == 200
    stored.refresh_from_db()
    assert stored.last_used


@pytest.mark.parametrize("change", ["delete", "disable", "expire", "deactivate"])
def test_native_revocation_invalidates_existing_downstream(world, change):
    client, data = issue(world[0])
    raw = data["token"]
    downstream = exchange(raw).json()["access_token"]
    row = APIToken.objects.get(pk=data["id"])
    if change == "delete":
        assert client.delete(f"/api/users/api-tokens/{row.pk}/").status_code == 204
    elif change == "deactivate":
        user = world[0]
        user.is_active = False
        user.save()
        user.is_active = True
        user.save()
    else:
        if change == "disable":
            row.is_active = False
        else:
            row.expired_at = timezone.now() - timedelta(seconds=1)
        row.save()
    assert exchange(raw).status_code == 401
    assert Client(HTTP_AUTHORIZATION="Bearer " + downstream).get("/api/singularity/v1/me/").status_code == 401
    with pytest.raises(AuthenticationFailed):
        APIKeyAuthentication().validate_api_token(raw)


def test_existing_native_token_expiry_and_member_removal(world):
    row = APIToken.objects.create(user=world[1], expired_at=timezone.now() + timedelta(seconds=40))
    downstream = exchange(row.token).json()
    child = DelegationToken.objects.get(digest=digest(downstream["access_token"]))
    assert child.expires_at <= row.expired_at
    api = Client(HTTP_AUTHORIZATION="Bearer " + downstream["access_token"])
    url = f"/api/singularity/v1/workspaces/{world[2].slug}/projects/{world[3].pk}/work-items/"
    assert api.get(url).status_code == 200
    ProjectMember.objects.filter(member=world[1], project=world[3]).delete()
    assert api.get(url).status_code == 404
    # A different user cannot revoke the owner's native credential.
    other = APIClient()
    other.force_authenticate(world[0])
    assert other.delete(f"/api/users/api-tokens/{row.pk}/").status_code != 204
    assert exchange(row.token).status_code == 200


def test_native_and_exchanged_writes_share_decision_and_rbac(world):
    from .test_singularity import create, items

    _, data = issue(world[1])
    raw = data["token"]
    direct = Client(HTTP_X_API_KEY=raw)
    payload = {"title": "Discussed decision", "description_markdown": "A confirmed result"}
    key = direct.post(items(world[3]) + "prepare/", payload, content_type="application/json").json()["decision_id"]
    delegated = Client(HTTP_AUTHORIZATION="Bearer " + exchange(raw).json()["access_token"])
    result = create(delegated, world[3], decision_id=key)
    assert result.status_code == 201
    assert create(direct, world[3], decision_id=key).json()["id"] == result.json()["id"]
    assert create(delegated, world[4]).status_code == 404
    # Another credential of the same user is a different authorization connection.
    _, second = issue(world[1])
    assert create(Client(HTTP_X_API_KEY=second["token"]), world[3], decision_id=key).status_code == 409


def test_connection_revocation_cannot_leave_native_api_access_active(world):
    _, data = issue(world[0])
    grant_id = exchange(data["token"]).json()["connection_id"]
    session = Client()
    session.force_login(world[0])
    session.post("/auth/singularity/connections/", {"grant": grant_id})
    assert exchange(data["token"]).status_code == 401
    with pytest.raises(AuthenticationFailed):
        APIKeyAuthentication().validate_api_token(data["token"])
