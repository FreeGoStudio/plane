# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Real OAuth and delegated API contracts using an isolated PostgreSQL database."""

import base64
import hashlib
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode, urlparse, parse_qs
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.db import close_old_connections
from django.test import Client
from rest_framework.test import APIClient
from crum import impersonate
from plane.db.models import (
    User,
    Workspace,
    WorkspaceMember,
    Project,
    ProjectMember,
    State,
    Issue,
)
from plane.singularity.oauth import SCOPES

pytestmark = pytest.mark.django_db(transaction=True)
ISSUER = "https://localhost:8444"
RESOURCE = ISSUER + "/mcp"
CALLBACK = "http://127.0.0.1:14551/callback"
VERIFIER = "v" * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()


@pytest.fixture(autouse=True)
def config(settings):
    settings.SINGULARITY_ENABLED = True
    settings.SINGULARITY_ISSUER = ISSUER
    settings.SINGULARITY_RESOURCE = RESOURCE
    settings.SINGULARITY_REDIRECT_URIS = [CALLBACK]
    settings.SINGULARITY_GATEWAY_SECRET = "isolated-test-gateway-secret"
    settings.SINGULARITY_PROJECT_CONFIG = {}
    cache.clear()
    with patch("plane.singularity.api.issue_activity.delay"), patch("plane.singularity.api.model_activity.delay"):
        yield


@pytest.fixture
def world():
    a = User.objects.create(email="alice@singularity.test", username="alice", is_active=True)
    b = User.objects.create(email="bob@singularity.test", username="bob", is_active=True)
    ws = Workspace.objects.create(name="Singularity test", slug="singularity-test", owner=a)
    for user, role in [(a, 20), (b, 15)]:
        WorkspaceMember.objects.create(workspace=ws, member=user, role=role)
    projects = []
    for name in ("POS", "PAY"):
        project = Project.objects.create(name=name, identifier=name, workspace=ws, network=0)
        State.objects.create(name="待整理", project=project, workspace=ws, group="backlog", color="#888888")
        ProjectMember.objects.create(workspace=ws, project=project, member=a, role=20)
        projects.append(project)
    ProjectMember.objects.create(workspace=ws, project=projects[0], member=b, role=15)
    return a, b, ws, projects[0], projects[1]


def authorize(user, scopes=SCOPES, **overrides):
    client = Client()
    client.force_login(user)
    params = dict(
        client_id="singularity-codex",
        response_type="code",
        redirect_uri=CALLBACK,
        scope=" ".join(scopes),
        state="test-state",
        code_challenge=CHALLENGE,
        code_challenge_method="S256",
        resource=RESOURCE,
    )
    params.update(overrides)
    response = client.post("/auth/singularity/authorize/?" + urlencode(params), {"decision": "allow"})
    return client, response


def login(user, scopes=SCOPES):
    client, response = authorize(user, scopes)
    assert response.status_code == 302, response.content
    code = parse_qs(urlparse(response["Location"]).query)["code"][0]
    body = dict(
        grant_type="authorization_code",
        code=code,
        client_id="singularity-codex",
        redirect_uri=CALLBACK,
        code_verifier=VERIFIER,
        resource=RESOURCE,
    )
    response = client.post(
        "/auth/singularity/token/", urlencode(body), content_type="application/x-www-form-urlencoded"
    )
    assert response.status_code == 200, response.content
    tokens = response.json()
    exchange = client.post(
        "/auth/singularity/exchange/",
        {"subject_token": tokens["access_token"]},
        HTTP_X_GATEWAY_SECRET="isolated-test-gateway-secret",
    )
    assert exchange.status_code == 200, exchange.content
    api = Client(HTTP_AUTHORIZATION="Bearer " + exchange.json()["access_token"])
    return api, client, tokens, exchange.json()


def items(project, item=None):
    base = f"/api/singularity/v1/workspaces/{project.workspace.slug}/projects/{project.id}/work-items/"
    return base + f"{item}/" if item else base


def create(api, project, **extra):
    payload = {"title": "Discussed decision", "description_markdown": "A confirmed result", **extra}
    if "decision_id" not in payload:
        prepared = api.post(items(project) + "prepare/", payload, content_type="application/json")
        if prepared.status_code != 202:
            return prepared
        payload["decision_id"] = prepared.json()["decision_id"]
    return api.post(items(project), payload, content_type="application/json")


def test_a01_a03_real_actor_and_no_default_assignment(world):
    a, b, ws, pos, pay = world
    pos.default_assignee = a
    pos.save()
    for user in (a, b):
        api, _, _, _ = login(user)
        result = create(api, pos)
        assert result.status_code == 201, result.content
        issue = Issue.objects.get(pk=result.json()["id"])
        assert issue.created_by_id == user.id
        assert not issue.assignees.exists()


def test_a02_a04_hidden_project_and_guest_edit(world):
    a, b, ws, pos, pay = world
    api, _, _, _ = login(b)
    listed = api.get("/api/singularity/v1/projects/")
    assert [p["name"] for p in listed.json()["results"]] == ["POS"]
    assert api.get(items(pay)).status_code == 404
    assert create(api, pay).status_code == 404
    admin, _, _, _ = login(a)
    issue = create(admin, pos).json()
    ProjectMember.objects.filter(project=pos, member=b).update(role=5)
    denied = api.post(
        items(pos, issue["id"]),
        {"decision_id": str(uuid.uuid4()), "title": "Forbidden", "expected_updated_at": issue["updated_at"]},
        content_type="application/json",
    )
    assert denied.status_code in (403, 404)
    assert Issue.objects.get(pk=issue["id"]).name == "Discussed decision"


@pytest.mark.parametrize("field", ["user_id", "role", "permission_grants", "plane_token", "url", "assignees", "state"])
def test_a05_a11_a13_field_whitelist(world, field):
    api, _, _, _ = login(world[1])
    assert create(api, world[3], **{field: "malicious"}).status_code == 400
    assert api.delete(items(world[3])).status_code == 405


def test_a06_missing_scope(world):
    api, _, _, _ = login(world[1], SCOPES[:2])
    assert create(api, world[3]).status_code == 403


def test_a07_removed_member(world):
    api, _, _, _ = login(world[1])
    assert create(api, world[3]).status_code == 201
    ProjectMember.objects.filter(project=world[3], member=world[1]).delete()
    assert api.get(items(world[3])).status_code == 404
    assert create(api, world[3]).status_code == 404


def test_a08_concurrent_and_restart_replay(world):
    api, _, _, token = login(world[1])
    key = api.post(
        items(world[3]) + "prepare/",
        {"title": "Discussed decision", "description_markdown": "A confirmed result"},
        content_type="application/json",
    ).json()["decision_id"]

    def send():
        close_old_connections()
        try:
            return create(Client(HTTP_AUTHORIZATION="Bearer " + token["access_token"]), world[3], decision_id=key)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: send(), range(2)))
    assert sorted(r.status_code for r in responses) == [200, 201], [r.content for r in responses]
    assert len({r.json()["id"] for r in responses}) == 1
    assert Issue.objects.filter(project=world[3]).count() == 1
    assert create(api, world[3], decision_id=key).status_code == 200


def test_a09_conflict_and_append_preserve_fields(world):
    api, _, _, _ = login(world[1])
    result = create(api, world[3]).json()
    issue = Issue.objects.get(pk=result["id"])
    issue.name = "Human edit"
    with impersonate(world[0]):
        issue.save()
    payload = {
        "description_markdown": "More",
        "expected_updated_at": result["updated_at"],
    }
    payload["decision_id"] = api.post(
        items(world[3], issue.id) + "prepare/", payload, content_type="application/json"
    ).json()["decision_id"]
    assert api.post(items(world[3], issue.id), payload, content_type="application/json").status_code == 409
    payload.pop("decision_id")
    payload["expected_updated_at"] = issue.updated_at.isoformat()
    payload["decision_id"] = api.post(
        items(world[3], issue.id) + "prepare/", payload, content_type="application/json"
    ).json()["decision_id"]
    response = api.post(items(world[3], issue.id), payload, content_type="application/json")
    assert response.status_code == 200, response.content
    issue.refresh_from_db()
    assert issue.name == "Human edit"
    assert "A confirmed result" in issue.description_html and "More" in issue.description_html


def test_a10_revocation_and_inactive_user(world):
    api, client, tokens, exchange = login(world[1])
    assert api.get("/api/singularity/v1/me/").status_code == 200
    client.post("/auth/singularity/connections/", {"grant": exchange["connection_id"]})
    assert api.get("/api/singularity/v1/me/").status_code == 401
    api, client, tokens, _ = login(world[1])
    User.objects.filter(pk=world[1].pk).update(is_active=False)
    assert api.get("/api/singularity/v1/me/").status_code == 401
    assert (
        client.post(
            "/auth/singularity/exchange/",
            {"subject_token": tokens["access_token"]},
            HTTP_X_GATEWAY_SECRET="isolated-test-gateway-secret",
        ).status_code
        == 401
    )


def test_a13_html_cleaned_a14_similar_titles_do_not_overwrite(world):
    api, _, _, _ = login(world[1])
    one = create(api, world[3], description_markdown="<script>alert(1)</script> [bad](javascript:alert(1))")
    two = create(api, world[3])
    assert one.status_code == two.status_code == 201
    assert one.json()["id"] != two.json()["id"]
    assert "<script>" not in one.json()["description_html"]
    assert 'href="javascript:' not in one.json()["description_html"]


def test_pkce_redirect_resource_and_code_replay(world):
    for changes in [
        {"redirect_uri": "https://evil.invalid"},
        {"resource": "https://evil.invalid"},
        {"code_challenge_method": "plain"},
    ]:
        _, response = authorize(world[1], **changes)
        assert response.status_code == 400
    client, response = authorize(world[1])
    code = parse_qs(urlparse(response["Location"]).query)["code"][0]
    data = dict(
        grant_type="authorization_code",
        code=code,
        client_id="singularity-codex",
        redirect_uri=CALLBACK,
        code_verifier="x" * 64,
        resource=RESOURCE,
    )
    assert (
        client.post(
            "/auth/singularity/token/", urlencode(data), content_type="application/x-www-form-urlencoded"
        ).status_code
        == 400
    )
    data["code_verifier"] = VERIFIER
    assert (
        client.post(
            "/auth/singularity/token/", urlencode(data), content_type="application/x-www-form-urlencoded"
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/auth/singularity/token/", urlencode(data), content_type="application/x-www-form-urlencoded"
        ).status_code
        == 400
    )


def test_refresh_rotation_and_audience(world):
    api, client, tokens, exchange = login(world[1])
    wrong = Client(HTTP_AUTHORIZATION="Bearer " + tokens["access_token"])
    assert wrong.get("/api/singularity/v1/me/").status_code == 401
    assert (
        client.post(
            "/auth/singularity/exchange/",
            {"subject_token": exchange["access_token"]},
            HTTP_X_GATEWAY_SECRET="isolated-test-gateway-secret",
        ).status_code
        == 401
    )
    data = dict(
        grant_type="refresh_token",
        refresh_token=tokens["refresh_token"],
        client_id="singularity-codex",
        resource=RESOURCE,
    )
    first = client.post("/auth/singularity/token/", urlencode(data), content_type="application/x-www-form-urlencoded")
    assert first.status_code == 200, first.content
    assert (
        client.post(
            "/auth/singularity/token/", urlencode(data), content_type="application/x-www-form-urlencoded"
        ).status_code
        == 400
    )


def test_connection_isolation_and_csrf(world):
    api, a, _, connection = login(world[0])
    _, b, _, _ = login(world[1])
    b.post("/auth/singularity/connections/", {"grant": connection["connection_id"]})
    assert api.get("/api/singularity/v1/me/").status_code == 200
    csrf = Client(enforce_csrf_checks=True)
    csrf.force_login(world[0])
    csrf.post("/auth/singularity/connections/", {"grant": connection["connection_id"]})
    # Plane's existing CSRF failure page responds with 200; the security
    # invariant is that no revocation was executed.
    assert api.get("/api/singularity/v1/me/").status_code == 200


def test_missing_initial_state_and_off_switch(world, settings):
    api, _, _, _ = login(world[1])
    State.objects.filter(project=world[3], name="待整理").update(name="Other")
    response = create(api, world[3])
    assert response.status_code == 409 and response.json()["error"] == "initial_state_not_configured"
    settings.SINGULARITY_ENABLED = False
    assert api.get("/api/singularity/v1/me/").status_code == 404


def test_native_edit_serializes_before_delegated_version_check(world):
    """A real native PATCH holds the same row lock before a delegated writer reads."""
    from plane.app.serializers import IssueCreateSerializer

    api, _, _, downstream = login(world[1])
    item = create(api, world[3]).json()
    delegated_payload = {"description_markdown": "AI append", "expected_updated_at": item["updated_at"]}
    delegated_payload["decision_id"] = api.post(
        items(world[3], item["id"]) + "prepare/", delegated_payload, content_type="application/json"
    ).json()["decision_id"]
    entered, release = threading.Event(), threading.Event()
    original_update = IssueCreateSerializer.update

    def paused_update(serializer, instance, validated_data):
        entered.set()
        assert release.wait(10)
        return original_update(serializer, instance, validated_data)

    def native_edit():
        close_old_connections()
        try:
            native = APIClient()
            native.force_authenticate(user=world[0])
            with impersonate(world[0]):
                return native.patch(
                    f"/api/workspaces/{world[2].slug}/projects/{world[3].id}/issues/{item['id']}/",
                    {"name": "Concurrent human edit"},
                    format="json",
                )
        finally:
            close_old_connections()

    def delegated_edit():
        close_old_connections()
        try:
            delegated = Client(HTTP_AUTHORIZATION="Bearer " + downstream["access_token"])
            return delegated.post(
                items(world[3], item["id"]),
                delegated_payload,
                content_type="application/json",
            )
        finally:
            close_old_connections()

    with patch.object(IssueCreateSerializer, "update", paused_update), ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(native_edit)
        try:
            assert entered.wait(10)
            second = pool.submit(delegated_edit)
        finally:
            release.set()
        assert first.result().status_code == 204
        assert second.result().status_code == 409
    assert Issue.objects.get(pk=item["id"]).name == "Concurrent human edit"


def test_plane_preparation_binds_actor_project_payload_and_never_writes_early(world):
    from plane.db.models import DiscussionReceipt

    alice, _, _, _ = login(world[0])
    bob, _, _, _ = login(world[1])
    payload = {"title": "Explicitly prepared", "description_markdown": "Private discussion"}
    # A client without an ID receives a draft, never an implicit work-item create.
    prepared = alice.post(items(world[3]), payload, content_type="application/json")
    assert prepared.status_code == 202 and prepared.json()["status"] == "prepared"
    assert Issue.objects.count() == 0
    key = prepared.json()["decision_id"]
    row = DiscussionReceipt.objects.get(pk=key)
    assert row.issue_id is None and row.result == {} and len(row.payload_digest) == 64
    body = {**payload, "decision_id": key}
    assert bob.post(items(world[3]), body, content_type="application/json").status_code == 409
    assert alice.post(items(world[4]), body, content_type="application/json").status_code == 409
    assert (
        alice.post(items(world[3]), {**body, "title": "Different content"}, content_type="application/json").status_code
        == 409
    )
    assert (
        alice.post(items(world[3]), {**body, "decision_id": str(uuid.uuid4())}, content_type="application/json").json()[
            "error"
        ]
        == "decision_not_prepared"
    )
    assert Issue.objects.count() == 0
    saved = alice.post(items(world[3]), body, content_type="application/json")
    assert saved.status_code == 201
    assert saved.json()["url"].endswith(f"/{world[2].slug}/browse/{saved.json()['work_item_identifier']}/")
    assert alice.post(items(world[3]), body, content_type="application/json").status_code == 200
    assert Issue.objects.count() == 1
