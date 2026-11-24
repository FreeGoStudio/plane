# ruff: noqa: F811
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Page/MCP parity and persistence of the human approval boundary."""

import copy
import io
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from django.test import Client
from plane.db.models import Issue, ProjectMember
from plane.singularity.wbs import start_run, review_run, WbsConflict, digest
from plane.singularity.wbs_generation import execute, validate_draft
from .test_singularity import world, config, login, items  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def requirement(world):
    a, _, ws, project, _ = world
    return Issue.objects.create(
        name="Login", description_html="<p>AC01: Login page</p>", project=project, workspace=ws, created_by=a
    )


def payload(issue, key="request-123"):
    return {"confirmed": True, "expected_updated_at": issue.updated_at.isoformat(), "idempotency_key": key}


def draft():
    return {
        "summary": "Draft",
        "coverage": [{"criterion_id": "AC01", "disposition": "gap", "basis": "Required page", "task_ids": ["T1"]}],
        "tasks": [
            {
                "id": "T1",
                "title": "Implement login page",
                "role": "Web",
                "criteria": ["AC01"],
                "scope": "Login UI",
                "deliverable": "Page",
                "dependencies": [],
                "acceptance": "Login fields visible",
            }
        ],
        "questions": [],
    }


def ready(user, issue):
    row = start_run(user, issue, payload(issue))
    row.result = draft()
    row.result_digest = digest(row.result)
    row.status = "ready"
    row.save()
    return row


def decision(row, choice="approve"):
    return {"decision": choice, "result_digest": row.result_digest, "reason": "Revise" if choice == "reject" else ""}


def test_session_and_mcp_share_run_and_require_explicit_confirmation(world, requirement):
    user = world[0]
    session = Client()
    session.force_login(user)
    api, *_ = login(user)
    path = items(requirement.project, requirement.id) + "wbs/"
    bad = session.post(path, {**payload(requirement), "confirmed": False}, content_type="application/json")
    assert bad.status_code == 400
    created = session.post(path, payload(requirement), content_type="application/json")
    assert created.status_code == 202, created.content
    replay = api.post(path, payload(requirement), content_type="application/json")
    assert replay.status_code == 202 and replay.json()["id"] == created.json()["id"]
    assert api.get(path).json()["results"][0]["status"] == "queued"
    assert not Issue.objects.filter(parent=requirement).exists()


def test_permission_and_scope_checked(world, requirement):
    user, outsider, _, project, _ = world
    api, *_ = login(user, scopes=["workitems:read"])
    path = items(project, requirement.id) + "wbs/"
    assert api.post(path, payload(requirement), content_type="application/json").status_code == 403
    ProjectMember.objects.filter(project=project, member=outsider).delete()
    client = Client()
    client.force_login(outsider)
    assert client.get(path).status_code in [403, 404]


def test_version_and_key_conflicts(world, requirement):
    user = world[0]
    start_run(user, requirement, payload(requirement))
    with pytest.raises(WbsConflict):
        start_run(user, requirement, {**payload(requirement), "expected_updated_at": "2000-01-01T00:00:00Z"})
    with pytest.raises(WbsConflict):
        start_run(user, requirement, payload(requirement, "another-123"))


def test_approval_creates_exact_children_once(world, requirement):
    row = ready(world[0], requirement)
    reviewed = review_run(world[0], row, decision(row))
    assert reviewed.status == "completed"
    child = Issue.objects.get(parent=requirement)
    assert child.created_by == world[0] and child.external_source == "plane-wbs"
    assert review_run(world[0], row, decision(row)).children == reviewed.children
    assert Issue.objects.filter(parent=requirement).count() == 1
    with pytest.raises(WbsConflict):
        review_run(world[0], row, decision(row, "reject"))


def test_changed_source_or_draft_cannot_be_approved(world, requirement):
    row = ready(world[0], requirement)
    with pytest.raises(WbsConflict):
        review_run(world[0], row, {**decision(row), "result_digest": "0" * 64})
    requirement.name = "Changed"
    requirement.save()
    with pytest.raises(WbsConflict):
        review_run(world[0], row, decision(row))
    assert not Issue.objects.filter(parent=requirement).exists()
    assert review_run(world[0], row, decision(row, "reject")).status == "rejected"


def test_execution_is_background_and_replay_does_not_regenerate(world, requirement):
    row = start_run(world[0], requirement, payload(requirement))
    with patch("plane.singularity.wbs_generation.generate", return_value=draft()) as model:
        assert execute(row.id, "hatchet-run-1")["status"] == "ready"
        assert execute(row.id, "hatchet-run-2")["status"] == "ready"
        assert model.call_count == 1
    assert not Issue.objects.filter(parent=requirement).exists()
    row.refresh_from_db()
    assert row.hatchet_run_id == "hatchet-run-1"


@pytest.mark.parametrize("case", ["coverage", "cycle", "duplicate", "source"])
def test_invalid_model_output_rejected(case):
    data = draft()
    snapshot = {"criteria": ["AC01"], "existing_children": []}
    if case == "coverage":
        data["coverage"] = []
    if case == "cycle":
        data["tasks"][0]["dependencies"] = ["T1"]
    if case == "duplicate":
        data["tasks"].append(copy.deepcopy(data["tasks"][0]))
    if case == "source":
        snapshot["existing_children"] = [{"name": "Implement login page"}]
    with pytest.raises(ValueError):
        validate_draft(data, snapshot)


def test_revoked_reviewer_cannot_approve(world, requirement):
    row = ready(world[0], requirement)
    ProjectMember.objects.filter(project=requirement.project, member=world[0]).update(is_active=False)
    from rest_framework.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied):
        review_run(world[0], row, decision(row))


@pytest.mark.parametrize("mode", ["initial", "update", "document_snapshot"])
def test_worker_warns_without_source_and_does_not_read_working_directory(
    world, requirement, tmp_path, monkeypatch, mode
):
    from plane.singularity.wbs_generation import SOURCE_WARNING
    from .test_wbs_update import result as change_draft

    request = payload(requirement)
    if mode != "initial":
        request["mode"] = "update"
    row = start_run(world[0], requirement, request)
    if mode == "document_snapshot":
        # A frozen PRD document must not be mistaken for implementation evidence.
        row.snapshot["source"] = {
            "kind": "documents",
            "repository_id": "prd-only",
            "documents": {"docs/prd.md": "AC01: Login page"},
        }
        row.save()
    model_draft = draft() if mode == "initial" else change_draft()
    key_file = tmp_path / "model-key"
    key_file.write_text("test-only-key", encoding="utf-8")
    unrelated = tmp_path / "unrelated-project"
    unrelated.mkdir()
    (unrelated / "login.py").write_text("UNRELATED_CODE_MUST_NOT_BE_READ", encoding="utf-8")
    monkeypatch.chdir(unrelated)
    monkeypatch.setenv("WBS_MODEL_KEY_FILE", str(key_file))
    real_open = io.open
    reads = []

    def guarded_open(file, *args, **kwargs):
        assert Path(file).resolve() == key_file.resolve(), f"Unexpected worker file access: {file}"
        reads.append(str(file))
        return real_open(file, *args, **kwargs)

    with (
        patch("plane.singularity.wbs_generation.requests.post") as post,
        patch("builtins.open", side_effect=guarded_open),
        patch("io.open", side_effect=guarded_open),
        patch("os.scandir", side_effect=AssertionError("Worker must not scan directories")),
        patch("subprocess.Popen", side_effect=AssertionError("Worker must not launch repository tools")),
    ):
        post.return_value.json.return_value = {
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(model_draft)}]}],
        }
        assert execute(row.id, "simulated-hatchet-run")["status"] == "ready"
    assert reads == [str(key_file)]
    post.assert_called_once()
    body = post.call_args.kwargs["json"]
    assert "tools" not in body
    assert "UNRELATED_CODE_MUST_NOT_BE_READ" not in json.dumps(body)
    assert json.loads(body["input"]) == row.snapshot
    row.refresh_from_db()
    assert row.result["summary"] == SOURCE_WARNING + "\n\n" + model_draft["summary"]
    assert row.result_digest == digest(row.result)
    assert not Issue.objects.filter(parent=requirement).exists()
    # Page and MCP read the same persisted warning; no repository gate was added.
    client = Client()
    client.force_login(world[0])
    response = client.get(items(requirement.project, requirement.id) + f"wbs/{row.id}/")
    assert response.status_code == 200
    assert response.json()["result"]["summary"] == row.result["summary"]
