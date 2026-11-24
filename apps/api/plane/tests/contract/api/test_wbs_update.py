# ruff: noqa: F811
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import copy
from unittest.mock import patch

import pytest
from plane.db.models import Issue, State, IssueActivity, IssueRelation, RequirementAdoption, RequirementReviewRun
from plane.singularity.wbs import start_run, review_run, digest, WbsConflict
from plane.singularity.wbs_generation import execute, validate_draft
from plane.singularity.wbs_update import source_for, snapshot_for, ensure_current
from .test_wbs import world, config, requirement, payload, draft, decision  # noqa: F401
from .test_requirement_review import review  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def test_directory_input_reads_only_primary_prd(review):
    cfg, provider = review
    cfg.paths = ["docs"]
    cfg.save()
    provider.directory.return_value = {
        "commit_sha": "a" * 40,
        "entries": [{"type": "blob", "path": p} for p in ["docs/prd.md", "docs/history.md"]],
        "next_page": None,
    }
    source = source_for(cfg.issue)
    assert list(source["documents"]) == ["docs/prd.md"]
    assert source["paths"] == ["docs/prd.md"]
    provider.directory.assert_not_called()
    provider.file.assert_called_once_with(cfg.repository, "a" * 40, "docs/prd.md")


@pytest.mark.parametrize("paths", [["docs/android.md"], ["docs/prd.md", "other/prd.md"]])
def test_missing_or_ambiguous_primary_is_not_guessed(review, paths):
    cfg, provider = review
    cfg.paths = paths
    cfg.save()
    with pytest.raises(WbsConflict, match="prd.md"):
        source_for(cfg.issue)
    provider.file.assert_not_called()


def test_missing_primary_content_does_not_fallback(review):
    cfg, provider = review
    provider.file.return_value["content"] = "  "
    with pytest.raises(WbsConflict, match="prd.md"):
        source_for(cfg.issue)
    provider.directory.assert_not_called()


def test_missing_primary_file_reports_selected_path(review):
    from plane.singularity.repository_transport import RepositoryError

    cfg, provider = review
    provider.file.side_effect = RepositoryError("upstream_resource_invisible", 404)
    with pytest.raises(WbsConflict, match="docs/prd.md"):
        source_for(cfg.issue)
    provider.directory.assert_not_called()


def test_primary_read_retains_version_guard(review):
    from rest_framework.exceptions import ValidationError

    cfg, provider = review
    provider.file.return_value["commit_sha"] = "b" * 40
    with pytest.raises(ValidationError, match="different commit"):
        source_for(cfg.issue)


def test_existing_primary_diff_contains_real_change(world, review):
    cfg, provider = review
    old = start(world[0], cfg.issue)
    provider.file.return_value["content"] = "# Login\nAC01: Changed login page"
    snapshot = snapshot_for(cfg.issue, old)
    assert "-AC01: Login page" in snapshot["source_diff"]
    assert "+AC01: Changed login page" in snapshot["source_diff"]


def test_first_analysis_has_no_full_document_diff(world, review):
    cfg, _ = review
    row = start(world[0], cfg.issue)
    assert row.snapshot["source_diff"] == ""


def test_legacy_baseline_does_not_repeat_full_document(world, review):
    cfg, _ = review
    previous = start(world[0], cfg.issue)
    previous.snapshot.pop("source")
    assert snapshot_for(cfg.issue, previous)["source_diff"] == ""


def test_changed_input_scope_does_not_include_old_scope_in_diff(world, review):
    cfg, _ = review
    previous = start(world[0], cfg.issue)
    previous.snapshot["source"]["paths"] = ["other/prd.md"]
    previous.snapshot["source"]["documents"] = {"other/prd.md": "AC99: Build backend"}
    assert snapshot_for(cfg.issue, previous)["source_diff"] == ""


def test_legacy_run_still_uses_original_document_input(world, review):
    cfg, _ = review
    row = start(world[0], cfg.issue)
    row.snapshot["source"].pop("input_policy", None)
    row.save()
    ensure_current(row)


def start(user, issue, key="update-123"):
    return start_run(user, issue, {**payload(issue, key), "mode": "update"})


def result(child=None, action="create"):
    return {
        "summary": "Update login",
        "questions": [],
        "coverage": draft()["coverage"],
        "changes": [
            {
                "id": "T1",
                "target_id": str(child.id) if child else None,
                "action": action,
                "basis": "AC01 changed",
                "impact": "Implementation not verified",
                "task": draft()["tasks"][0] if action not in ["keep", "cancel"] else None,
            }
        ],
    }


def test_model_schema_dependencies_are_ids_not_external_prose():
    from plane.singularity.wbs_generation import ChangeDraft

    item = ChangeDraft.model_json_schema()["$defs"]["Task"]["properties"]["dependencies"]["items"]
    assert item["pattern"] == r"^[A-Za-z0-9_-]+$"


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("id", "OTHER", "task ID mismatch"),
        ("dependencies", ["EXT-01"], "unknown task dependency"),
        ("criteria", ["AC02"], "acceptance mapping mismatch"),
    ],
)
def test_reference_error_identifies_relation_without_echoing_content(field, value, reason):
    data = result()
    data["changes"][0]["task"][field] = value
    with pytest.raises(ValueError, match=reason):
        validate_draft(data, {"workflow": 2, "criteria": ["AC01"], "existing_children": []})


def test_external_dependency_stays_in_scope_not_task_edges():
    data = result()
    data["changes"][0]["task"]["scope"] += "; EXT-01 backend contract pending; use test adapter"
    parsed = validate_draft(data, {"workflow": 2, "criteria": ["AC01"], "existing_children": []})
    assert "EXT-01" in parsed["changes"][0]["task"]["scope"]
    assert parsed["changes"][0]["task"]["dependencies"] == []


def ready(user, issue, child=None, action="create"):
    row = start(user, issue)
    row.result = result(child, action)
    row.result_digest = digest(row.result)
    row.status = "ready"
    row.save()
    return row


def approve(user, row, choices=None):
    return review_run(user, row, {**decision(row), "source_confirmed": True, "choices": choices or {}})


def child_for(issue, group="unstarted"):
    state, _ = State.objects.get_or_create(project=issue.project, workspace=issue.workspace, name=group, group=group)
    return Issue.objects.create(
        parent=issue,
        project=issue.project,
        workspace=issue.workspace,
        name="Existing",
        description_html="<p>Old acceptance</p>",
        state=state,
    )


def test_first_update_needs_exact_body_confirmation_and_is_idempotent(world, requirement):
    row = ready(world[0], requirement)
    with pytest.raises(WbsConflict):
        review_run(world[0], row, decision(row))
    done = approve(world[0], row)
    assert done.status == "completed"
    assert approve(world[0], row).children == done.children
    assert Issue.objects.filter(parent=requirement).count() == 1


def test_changed_prd_supersedes_ready_draft_without_creating_children(world, requirement):
    old = ready(world[0], requirement)
    requirement.description_html = "<p>AC01: Changed login</p>"
    requirement.save()
    new = start(world[0], requirement, "update-456")
    old.refresh_from_db()
    assert old.status == "superseded"
    assert new.snapshot["previous_run_id"] == str(old.pk)
    with pytest.raises(WbsConflict):
        approve(world[0], old)
    assert not Issue.objects.filter(parent=requirement).exists()


def test_pending_worker_cannot_restore_superseded_run(world, requirement):
    old = start(world[0], requirement)

    def model(_):
        requirement.name = "New requirement"
        requirement.save()
        start(world[0], requirement, "update-456")
        return result()

    with patch("plane.singularity.wbs_generation.generate", side_effect=model):
        with pytest.raises(RuntimeError):
            execute(old.pk, "worker-1")
    old.refresh_from_db()
    assert old.status == "superseded"


def test_unstarted_task_updated_in_place_preserves_identity(world, requirement):
    child = child_for(requirement)
    row = ready(world[0], requirement, child, "update")
    approve(world[0], row)
    child.refresh_from_db()
    assert child.name == "Implement login page"
    assert child.state.group == "unstarted"
    assert Issue.objects.filter(parent=requirement).count() == 1
    assert IssueActivity.objects.filter(issue=child).exists()


@pytest.mark.parametrize("choice", ["update", "append", "cancel"])
def test_started_task_requires_explicit_choice(world, requirement, choice):
    child = child_for(requirement, "started")
    State.objects.create(
        project=requirement.project, workspace=requirement.workspace, name="Cancelled", group="cancelled"
    )
    row = ready(world[0], requirement, child, "update")
    with pytest.raises(WbsConflict):
        approve(world[0], row)
    approve(world[0], row, {"T1": choice})
    child.refresh_from_db()
    assert Issue.objects.filter(parent=requirement).count() == (2 if choice == "append" else 1)
    assert child.name == ("Implement login page" if choice == "update" else "Existing")
    assert child.state.group == ("cancelled" if choice == "cancel" else "started")
    if choice == "append":
        assert IssueRelation.objects.filter(related_issue=child, relation_type="relates_to").exists()


def test_completed_task_only_allows_append(world, requirement):
    child = child_for(requirement, "completed")
    row = ready(world[0], requirement, child, "append")
    with pytest.raises(WbsConflict):
        approve(world[0], row, {"T1": "update"})
    approve(world[0], row, {"T1": "append"})
    child.refresh_from_db()
    assert child.state.group == "completed" and child.name == "Existing"


def test_returned_to_backlog_still_requires_choice(world, requirement):
    child = child_for(requirement)
    old = State.objects.create(
        project=requirement.project, workspace=requirement.workspace, name="Started", group="started"
    )
    IssueActivity.objects.create(
        issue=child,
        project=child.project,
        workspace=child.workspace,
        actor=world[0],
        field="state",
        old_identifier=old.pk,
        new_identifier=child.state_id,
    )
    row = ready(world[0], requirement, child, "update")
    with pytest.raises(WbsConflict):
        approve(world[0], row)


def test_task_state_changed_after_analysis_blocks_all_writes(world, requirement):
    child = child_for(requirement)
    row = ready(world[0], requirement, child, "update")
    child.name = "Manual edit"
    child.save()
    with pytest.raises(WbsConflict):
        approve(world[0], row)
    row.refresh_from_db()
    assert not row.decision


def test_bound_prd_requires_matching_completed_adoption(world, review):
    cfg, provider = review
    row = ready(world[0], cfg.issue)
    assert row.snapshot["source"]["documents"]["docs/prd.md"].startswith("# Login")
    with pytest.raises(WbsConflict):
        approve(world[0], row)
    rr = RequirementReviewRun.objects.create(
        config=cfg,
        source_sha="a" * 40,
        input_digest="x" * 64,
        snapshot={
            "documents": {**row.snapshot["source"]["documents"], "docs/history.md": "Not WBS input"},
            "basis": row.snapshot["source"]["basis"],
        },
        request_key="review-123",
    )
    RequirementAdoption.objects.create(
        config=cfg,
        run=rr,
        actor=world[0],
        source_sha="a" * 40,
        target_sha="b" * 40,
        merged_sha="a" * 40,
        config_revision=cfg.revision,
        kind="override",
        reason="Human confirmed",
        status="completed",
        request_key="adopt-123",
    )
    cfg.adopted_sha = "a" * 40
    cfg.save()
    assert approve(world[0], row).status == "completed"


def test_new_document_commit_invalidates_draft(world, review):
    cfg, provider = review
    row = ready(world[0], cfg.issue)
    provider.resolve.return_value = ({}, "", "b" * 40, None)
    provider.file.return_value = {"commit_sha": "b" * 40, "content": "AC01: Another version"}
    with pytest.raises(WbsConflict):
        approve(world[0], row)


def test_model_must_account_for_every_existing_child(world, requirement):
    child_for(requirement)
    row = start(world[0], requirement)
    with pytest.raises(ValueError):
        validate_draft(result(), row.snapshot)


def test_zero_change_preserves_children(world, requirement):
    child = child_for(requirement)
    row = ready(world[0], requirement, child, "keep")
    row.result["coverage"][0].update(disposition="existing", task_ids=[])
    row.result_digest = digest(row.result)
    row.save()
    approve(world[0], row)
    child.refresh_from_db()
    assert child.name == "Existing" and Issue.objects.filter(parent=requirement).count() == 1


def test_failure_during_second_change_rolls_back_first(world, requirement):
    first, second = child_for(requirement), child_for(requirement)
    row = ready(world[0], requirement, first, "update")
    other = copy.deepcopy(row.result["changes"][0])
    other.update(id="T2", target_id=str(second.pk))
    other["task"]["id"] = "T2"
    row.result["changes"].append(other)
    row.result["coverage"][0]["task_ids"].append("T2")
    row.result_digest = digest(row.result)
    row.save()
    from plane.api.serializers import IssueSerializer

    original = IssueSerializer.save
    count = 0

    def save(serializer, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("simulated write failure")
        return original(serializer, **kwargs)

    with patch.object(IssueSerializer, "save", save), pytest.raises(RuntimeError):
        approve(world[0], row)
    first.refresh_from_db()
    row.refresh_from_db()
    assert first.name == "Existing" and not row.decision
    assert not IssueActivity.objects.filter(issue=first, field="wbs").exists()


def test_bound_document_read_failure_never_uses_body(world, review):
    cfg, provider = review
    provider.file.side_effect = RuntimeError("repository unavailable")
    with pytest.raises(RuntimeError):
        start(world[0], cfg.issue)


def test_legacy_approval_cannot_bypass_bound_document_gate(world, review):
    cfg, _ = review
    # A historical draft produced before document binding must not bypass the gate.
    from plane.db.models import WbsRun
    from plane.singularity.wbs import source_snapshot

    snapshot = source_snapshot(cfg.issue)
    row = WbsRun.objects.create(
        issue=cfg.issue,
        requested_by=world[0],
        request_key="old-12345",
        snapshot=snapshot,
        input_digest=digest(snapshot),
        result=draft(),
        result_digest=digest(draft()),
        status="ready",
    )
    with pytest.raises(WbsConflict):
        review_run(world[0], row, decision(row))


def test_document_source_does_not_require_plane_body(world, review):
    cfg, _ = review
    cfg.issue.description_html = ""
    cfg.issue.save()
    assert start(world[0], cfg.issue).snapshot["source"]["kind"] == "documents"


def test_adoption_of_previous_body_does_not_confirm_changed_requirement(world, review):
    cfg, _ = review
    row = ready(world[0], cfg.issue)
    rr = RequirementReviewRun.objects.create(
        config=cfg,
        source_sha="a" * 40,
        input_digest="x" * 64,
        snapshot={"documents": row.snapshot["source"]["documents"], "basis": row.snapshot["source"]["basis"]},
        request_key="review-123",
    )
    RequirementAdoption.objects.create(
        config=cfg,
        run=rr,
        actor=world[0],
        source_sha="a" * 40,
        target_sha="b" * 40,
        merged_sha="a" * 40,
        config_revision=cfg.revision,
        kind="override",
        reason="Human confirmed",
        status="completed",
        request_key="adopt-123",
    )
    cfg.adopted_sha = "a" * 40
    cfg.save()
    cfg.issue.name = "Changed requirement scope"
    cfg.issue.save()
    fresh = start(world[0], cfg.issue, "fresh-123")
    fresh.result, fresh.status = result(), "ready"
    fresh.result_digest = digest(fresh.result)
    fresh.save()
    with pytest.raises(WbsConflict):
        approve(world[0], fresh)


def test_wbs_cancel_preserves_started_history_for_next_analysis(world, requirement):
    child = child_for(requirement, "started")
    State.objects.create(
        project=requirement.project, workspace=requirement.workspace, name="Cancelled", group="cancelled"
    )
    row = ready(world[0], requirement, child, "update")
    approve(world[0], row, {"T1": "cancel"})
    next_run = start(world[0], requirement, "next-1234")
    assert next_run.snapshot["existing_children"][0]["stage"] == "started"


def test_empty_model_target_rejected(world, requirement):
    row = start(world[0], requirement)
    bad = result()
    bad["changes"][0].update(target_id="", action="update")
    with pytest.raises(ValueError):
        validate_draft(bad, row.snapshot)


@pytest.mark.parametrize("choice", ["update", "append"])
def test_human_can_replace_proposed_cancellation_with_explicit_task(world, requirement, choice):
    child = child_for(requirement, "started")
    row = ready(world[0], requirement, child, "cancel")
    row.result["coverage"][0].update(disposition="existing", task_ids=[])
    row.result_digest = digest(row.result)
    row.save()
    data = {
        **decision(row),
        "source_confirmed": True,
        "choices": {"T1": choice},
        "replacement_tasks": {"T1": draft()["tasks"][0]},
    }
    assert review_run(world[0], row, data).status == "completed"
    child.refresh_from_db()
    assert Issue.objects.filter(parent=requirement).count() == (2 if choice == "append" else 1)
    assert child.state.group == "started"
    assert review_run(world[0], row, data).status == "completed"
    data["replacement_tasks"]["T1"]["scope"] = "different"
    with pytest.raises(WbsConflict):
        review_run(world[0], row, data)


def test_gap_cannot_be_satisfied_by_cancellation_only(world, requirement):
    child = child_for(requirement)
    row = start(world[0], requirement)
    with pytest.raises(ValueError):
        validate_draft(result(child, "cancel"), row.snapshot)


def test_update_api_exposes_same_source_and_requires_confirmation(world, requirement):
    from django.test import Client
    from .test_singularity import login, items

    session = Client()
    session.force_login(world[0])
    api, *_ = login(world[0])
    path = items(requirement.project, requirement.id) + "wbs/"
    response = session.post(path, {**payload(requirement), "mode": "update"}, content_type="application/json")
    assert response.status_code == 202
    from plane.db.models import WbsRun

    row = WbsRun.objects.get(pk=response.json()["id"])
    row.result, row.status = result(), "ready"
    row.result_digest = digest(row.result)
    row.save()
    view = api.get(path + str(row.pk) + "/").json()
    assert view["source"]["kind"] == "body" and view["readiness"]["body_confirmation_required"]
    denied = api.post(path + str(row.pk) + "/", decision(row), content_type="application/json")
    assert denied.status_code == 409 and not Issue.objects.filter(parent=requirement).exists()
    accepted = session.post(
        path + str(row.pk) + "/", {**decision(row), "source_confirmed": True}, content_type="application/json"
    )
    assert accepted.status_code == 200
    row.refresh_from_db()
    assert row.input_digest == digest(row.snapshot)


def test_mixed_task_stages_apply_individually_without_touching_completed_work(world, requirement):
    pending = child_for(requirement)
    started = child_for(requirement, "started")
    completed = child_for(requirement, "completed")
    completed_version = completed.updated_at
    row = ready(world[0], requirement, pending, "update")
    second = result(started, "update")["changes"][0]
    second["id"] = second["task"]["id"] = "T2"
    third = result(completed, "keep")["changes"][0]
    third["id"] = "T3"
    row.result["changes"] += [second, third]
    row.result["coverage"][0]["task_ids"].append("T2")
    row.result_digest = digest(row.result)
    row.save()
    approve(world[0], row, {"T2": "append"})
    pending.refresh_from_db()
    started.refresh_from_db()
    completed.refresh_from_db()
    assert pending.name == "Implement login page" and started.name == "Existing"
    assert completed.updated_at == completed_version
    assert Issue.objects.filter(parent=requirement).count() == 4
