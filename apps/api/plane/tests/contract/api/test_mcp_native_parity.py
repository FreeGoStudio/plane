# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Actual native handlers with PAT and exchanged authorization, on PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from django.core.cache import cache
from django.db import close_old_connections
from django.test import Client
from crum import impersonate

from plane.db.models import APIToken, Issue, Label, ProjectMember, State, DelegationAudit
from .test_singularity import config, world, login  # noqa: F401
from .test_native_personal_tokens import exchange

# ruff: noqa: F811
pytestmark = pytest.mark.django_db(transaction=True)


def clients(user):
    token = APIToken.objects.create(user=user)
    child = exchange(token.token).json()["access_token"]
    return token, Client(HTTP_X_API_KEY=token.token), Client(HTTP_AUTHORIZATION="Bearer " + child)


def path(world, item=None):
    base = f"/api/v1/workspaces/{world[2].slug}/projects/{world[3].pk}/work-items/"
    return base + (str(item) + "/" if item else "")


def post(api, url, data, **headers):
    return api.post(url, data, content_type="application/json", **headers)


def test_defaults_complete_fields_validation_and_replay(world):
    _, direct, delegated = clients(world[0])
    pos = world[3]
    pos.default_assignee = world[1]
    pos.save()
    label = Label.objects.create(project=pos, workspace=world[2], name="Parity")
    state = State.objects.filter(project=pos).first()
    base = {"name": "Native defaults", "description_html": "<p>正文</p>"}
    # The same serializer applies the native default assignee and state on both routes.
    left, right = [post(api, path(world), base) for api in (direct, delegated)]
    assert left.status_code == right.status_code == 201, (left.content, right.content)
    for result in (left, right):
        item = Issue.objects.get(pk=result.json()["id"])
        assert item.assignees.filter(pk=world[1].pk).exists()
        assert item.state_id == state.pk
        assert item.created_by_id == world[0].pk
    full = {
        "name": "All fields",
        "state": str(state.pk),
        "priority": "high",
        "labels": [str(label.pk)],
        "assignees": [str(world[0].pk)],
        "start_date": "2026-11-14",
        "target_date": "2026-11-30",
        "parent": left.json()["id"],
    }
    created = post(delegated, path(world), full, HTTP_IDEMPOTENCY_KEY="same-operation")
    assert created.status_code == 201, created.content
    replay = post(direct, path(world), full, HTTP_IDEMPOTENCY_KEY="same-operation")
    assert replay.json() == created.json()
    assert Issue.objects.filter(name="All fields").count() == 1
    item = Issue.objects.get(pk=created.json()["id"])
    assert item.labels.filter(pk=label.pk).exists()
    assert item.priority == "high" and str(item.target_date) == "2026-11-30"
    assert (
        post(direct, path(world), {**full, "name": "changed"}, HTTP_IDEMPOTENCY_KEY="same-operation").status_code == 409
    )
    alien = State.objects.filter(project=world[4]).first()
    for invalid in ({"state": str(alien.pk)}, {"priority": "impossible"}, {"name": ""}, {"assignees": [str(label.pk)]}):
        errors = [post(api, path(world), {**base, **invalid}) for api in (direct, delegated)]
        assert errors[0].status_code == errors[1].status_code == 400
        assert errors[0].json() == errors[1].json()
    assert DelegationAudit.objects.filter(operation="POST IssueListCreateAPIEndpoint", status=201).exists()


@pytest.mark.parametrize("role,active", [(20, True), (15, True), (5, True), (15, False), (None, False)])
def test_current_role_visibility_and_mutations_match(world, role, active):
    token, direct, delegated = clients(world[1])
    member = ProjectMember.objects.get(project=world[3], member=world[1])
    if role is None:
        member.delete()
    else:
        member.role, member.is_active = role, active
        member.save()
    with impersonate(world[0]):
        item = Issue.objects.create(project=world[3], workspace=world[2], name="Admin item")
    for url in (path(world), path(world, item.pk)):
        responses = [api.get(url) for api in (direct, delegated)]
        assert responses[0].status_code == responses[1].status_code
        assert responses[0].json() == responses[1].json()
    responses = [post(api, path(world), {"name": "Role create"}) for api in (direct, delegated)]
    assert responses[0].status_code == responses[1].status_code == (201 if active and role >= 15 else 403)
    responses = [
        api.patch(path(world, item.pk), {"priority": "low"}, content_type="application/json")
        for api in (direct, delegated)
    ]
    assert responses[0].status_code == responses[1].status_code == (200 if active and role >= 15 else 403)
    # Successful delete is replayed against the same source credential, including current permissions.
    responses = [api.delete(path(world, item.pk), HTTP_IDEMPOTENCY_KEY="delete") for api in (direct, delegated)]
    assert responses[0].status_code == responses[1].status_code == (204 if active and role == 20 else 403)
    token.delete()
    assert direct.get(path(world)).status_code in (401, 403)
    assert delegated.get(path(world)).status_code in (401, 403)


def test_shared_quota_exchange_not_business_request(world, settings):
    token, direct, delegated = clients(world[0])
    settings.API_KEY_RATE_LIMIT = "2/minute"
    cache.clear()
    assert direct.get(path(world)).status_code == 200
    assert exchange(token.token).status_code == 200
    assert delegated.get(path(world)).status_code == 200
    assert direct.get(path(world)).status_code == 429
    assert delegated.get(path(world)).status_code == 429


def test_oauth_scopes_remain_explicit(world):
    api, _, _, _ = login(world[0], ["workitems:read", "workitems:write"])
    assert api.get(path(world)).status_code == 200
    result = post(api, path(world), {"name": "OAuth write"})
    assert result.status_code == 201, result.content
    assert api.delete(path(world, result.json()["id"])).status_code == 403
    assert DelegationAudit.objects.filter(operation="DELETE IssueDetailAPIEndpoint", status=403).exists()
    assert api.get("/api/v1/users/me/").status_code == 403
    all_api, _, _, _ = login(world[0])
    assert all_api.get("/api/v1/users/me/").status_code == 200
    assert all_api.delete(path(world, result.json()["id"])).status_code == 204


def test_gateway_audience_is_not_a_native_api_token(world):
    _, _, tokens, _ = login(world[0])
    wrong_audience = Client(HTTP_AUTHORIZATION="Bearer " + tokens["access_token"])
    assert wrong_audience.get(path(world)).status_code in (401, 403)


def test_web_edit_conflicts_with_stale_delegated_version(world):
    _, direct, delegated = clients(world[0])
    created = post(direct, path(world), {"name": "Initial"}).json()
    web = Client()
    web.force_login(world[0])
    url = f"/api/workspaces/{world[2].slug}/projects/{world[3].pk}/issues/{created['id']}/"
    edited = web.patch(url, {"name": "Human edit"}, content_type="application/json")
    assert edited.status_code in (200, 204), edited.content
    stale = delegated.patch(
        path(world, created["id"]),
        {"name": "AI stale edit"},
        content_type="application/json",
        HTTP_IF_MATCH=created["updated_at"],
    )
    assert stale.status_code == 409
    assert Issue.objects.get(pk=created["id"]).name == "Human edit"


def test_capability_hints_follow_native_mutation_rules(world):
    _, direct, delegated = clients(world[1])
    created = post(direct, path(world), {"name": "Member item"}).json()
    url = path(world, created["id"]).replace("/api/v1/", "/api/singularity/v1/") + "capabilities/"
    hints = delegated.get(url).json()
    assert hints["can_create"] and hints["can_update"] and hints["can_delete"]
    ProjectMember.objects.filter(project=world[3], member=world[1]).update(role=5)
    hints = delegated.get(url).json()
    assert not hints["can_create"] and not hints["can_update"] and not hints["can_delete"]


def test_native_conditional_update_and_delete(world):
    _, direct, delegated = clients(world[0])
    created = post(direct, path(world), {"name": "Keep title", "description_html": "<p>Keep body</p>"}).json()
    url = path(world, created["id"])
    first = delegated.patch(
        url,
        {"priority": "high"},
        content_type="application/json",
        HTTP_IF_MATCH=created["updated_at"],
        HTTP_IDEMPOTENCY_KEY="patch",
    )
    assert first.status_code == 200
    assert first.json()["name"] == "Keep title"
    assert (
        direct.patch(
            url,
            {"priority": "high"},
            content_type="application/json",
            HTTP_IF_MATCH=created["updated_at"],
            HTTP_IDEMPOTENCY_KEY="patch",
        ).json()
        == first.json()
    )
    assert (
        direct.patch(
            url, {"name": "stale"}, content_type="application/json", HTTP_IF_MATCH=created["updated_at"]
        ).status_code
        == 409
    )
    assert direct.delete(url, HTTP_IF_MATCH=created["updated_at"]).status_code == 409
    assert (
        delegated.delete(url, HTTP_IF_MATCH=first.json()["updated_at"], HTTP_IDEMPOTENCY_KEY="delete").status_code
        == 204
    )
    assert (
        direct.delete(url, HTTP_IF_MATCH=first.json()["updated_at"], HTTP_IDEMPOTENCY_KEY="delete").status_code == 204
    )


def test_concurrent_create_and_conditional_update(world):
    token, direct, delegated = clients(world[0])
    child = exchange(token.token).json()["access_token"]
    barrier = threading.Barrier(2)

    def run(index):
        close_old_connections()
        try:
            api = Client(
                **({"HTTP_X_API_KEY": token.token} if index == 0 else {"HTTP_AUTHORIZATION": "Bearer " + child})
            )
            barrier.wait(timeout=10)
            response = post(api, path(world), {"name": "Concurrent"}, HTTP_IDEMPOTENCY_KEY="parallel")
            return response.status_code, response.json()
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert results[0] == results[1] and results[0][0] == 201
    assert Issue.objects.filter(name="Concurrent").count() == 1
    item = results[0][1]
    barrier = threading.Barrier(2)

    def update(index):
        close_old_connections()
        try:
            api = Client(
                **({"HTTP_X_API_KEY": token.token} if index == 0 else {"HTTP_AUTHORIZATION": "Bearer " + child})
            )
            barrier.wait(timeout=10)
            return api.patch(
                path(world, item["id"]),
                {"name": f"Edit {index}"},
                content_type="application/json",
                HTTP_IF_MATCH=item["updated_at"],
            ).status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(update, range(2))) == [200, 409]
