# ruff: noqa: F811
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Document pushes, immutable review conclusions and explicit human overrides."""

from datetime import timedelta
import base64
from unittest.mock import Mock, patch
import pytest
from django.test import Client
from django.utils import timezone
from rest_framework.exceptions import ValidationError, PermissionDenied
from plane.db.models import (
    Issue,
    RepositoryInstance,
    ProjectRepository,
    ProjectRepositoryBinding,
    RequirementReviewRun,
    RequirementAdoption,
    RequirementReviewEvent,
    ProjectMember,
)
from plane.singularity.requirement_review import (
    configure,
    capture as capture_snapshot,
    adopt,
    retry_run,
    poll_one,
    WbsConflict,
)
from plane.singularity.requirement_review_generation import execute, validate_result
from plane.db.management.commands.requirement_review_worker import dispatch_pending
from .test_singularity import world, config  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def review(world, monkeypatch):
    user, _, workspace, project, _ = world
    issue = Issue.objects.create(
        name="Login", description_html="<p>AC01: Login page</p>", project=project, workspace=workspace
    )
    instance = RepositoryInstance.objects.create(
        name="GitLab", provider="gitlab", api_url="https://git.example/api/v4", web_url="https://git.example"
    )
    repo = ProjectRepository.objects.create(
        project=project, instance=instance, external_id="22", path="team/docs", purpose="documentation"
    )
    ProjectRepositoryBinding.objects.create(project=project, documentation_repository=repo, revision=1)
    monkeypatch.setenv("DOCUMENT_REVIEW_GATED_REPOSITORIES", str(repo.pk))
    row = configure(
        user,
        issue,
        {"draft_branch": "draft/POS-1", "adopted_branch": "POS-1", "paths": ["docs/prd.md"], "expected_revision": 0},
    )
    provider = Mock()
    provider.resolve.return_value = ({}, "", "a" * 40)
    provider.file.return_value = {"commit_sha": "a" * 40, "content": "# Login\nAC01: Login page"}
    with (
        patch("plane.singularity.requirement_review.provider_for", return_value=provider),
        patch("plane.singularity.requirement_review_api.provider_for", return_value=provider),
        patch("plane.singularity.requirement_merge_request.provider_for", return_value=provider),
    ):
        yield row, provider


def capture(config, source_sha=None):
    """Existing review tests start after the independently tested MR preparation."""
    row = capture_snapshot(config, source_sha)
    row.merge_request = {"iid": 7, "web_url": "https://git.example/team/docs/-/merge_requests/7"}
    row.save(update_fields=["merge_request"])
    return row


def result(verdict="passed"):
    return {"verdict": verdict, "summary": "Reviewed", "findings": []}


def test_readable_titles_preserve_legacy_results_and_evidence_validation():
    from plane.singularity.requirement_review_generation import GeneratedReviewResult

    value = {
        "verdict": "changes_requested",
        "summary": "需修改",
        "findings": [
            {
                "id": "F1",
                "severity": "blocking",
                "path": "prd.md",
                "line": 1,
                "evidence": "| AC-004 | 冻结候选 |",
                "reason": "缺少采用检查。",
                "suggestion": "补充采用检查。",
            }
        ],
    }
    snapshot = {"documents": {"prd.md": "| AC-004 | 冻结候选 |"}}
    assert validate_result(value, snapshot) == value
    value["findings"][0]["title"] = "缺少固定 PRD 采用检查"
    assert validate_result(value, snapshot) == value
    schema = GeneratedReviewResult.model_json_schema()
    assert "title" in schema["$defs"]["GeneratedFinding"]["required"]
    value["findings"][0]["evidence"] = "改写后的证据"
    with pytest.raises(ValueError, match="invented_evidence"):
        validate_result(value, snapshot)


def ready(review):
    row = capture(review[0])
    with patch("plane.singularity.requirement_review_generation.generate", return_value=result()):
        execute(row.pk, "hatchet-1")
    row.refresh_from_db()
    return row


def test_push_snapshot_deduplicates_and_replays_without_model(review):
    row = capture(review[0])
    assert capture(review[0]).pk == row.pk
    with patch("plane.singularity.requirement_review_generation.generate", return_value=result()) as generate:
        assert execute(row.pk, "hatchet-1")["status"] == "completed"
        assert execute(row.pk, "hatchet-2")["status"] == "completed"
        assert generate.call_count == 1
    assert RequirementReviewRun.objects.count() == 1


@pytest.mark.parametrize("explicit_sha", [False, True])
def test_capture_with_real_repository_provider_contract(review, explicit_sha):
    """Mock only transport so provider return-shape changes cannot hide in fixtures."""
    from plane.singularity.repository_provider import RepositoryProvider

    config, _ = review
    commit, baseline = "a" * 40, "b" * 40
    content = "# Login\nAC01: Login page"

    def get(path, params=None):
        if path == "/projects/22":
            return {"id": 22, "path_with_namespace": "team/docs", "default_branch": "main"}
        if "/repository/commits/" in path:
            return {"id": baseline if path.endswith("/POS-1") else commit}
        if path.endswith("/repository/tree"):
            assert params["ref"] == commit
            return [{"name": "prd.md", "type": "blob", "mode": "100644"}]
        if path.endswith("/repository/files/docs%2Fprd.md"):
            assert params["ref"] == commit
            return {
                "commit_id": commit,
                "blob_id": "c" * 40,
                "size": len(content),
                "encoding": "base64",
                "content": base64.b64encode(content.encode()).decode(),
            }
        raise AssertionError(path)

    provider = RepositoryProvider(config.repository.instance)
    with (
        patch.object(provider.http, "get", side_effect=get),
        patch("plane.singularity.requirement_review.provider_for", return_value=provider),
    ):
        row = capture_snapshot(config, commit if explicit_sha else None)
        assert capture_snapshot(config, commit).pk == row.pk
    assert row.source_sha == commit
    assert row.snapshot["baseline_sha"] == baseline
    assert row.snapshot["documents"] == {"docs/prd.md": content}
    assert row.status == "queued"


@pytest.mark.parametrize(
    "message,expected",
    [
        ("not enough values to unpack (expected 4, got 3)", "ValueError: unpack expected 4, got 3"),
        ("https://user:private-token@git.example?token=secret", "ValueError"),
    ],
)
def test_capture_failure_has_safe_location_and_recovers(review, message, expected):
    config, provider = review
    provider.resolve.side_effect = ValueError(message)
    poll_one()
    config.refresh_from_db()
    assert config.error.startswith(expected + " at requirement_review.py:")
    assert len(config.error) <= 100
    assert "private-token" not in config.error and "secret" not in config.error
    assert not RequirementReviewRun.objects.exists()
    provider.resolve.side_effect = None
    config.poll_after = None
    config.save(update_fields=["poll_after"])
    poll_one()
    config.refresh_from_db()
    assert config.error == ""
    assert RequirementReviewRun.objects.count() == 1


def test_consecutive_commits_keep_both_results(review):
    first = ready(review)
    review[1].resolve.return_value = ({}, "", "b" * 40)
    review[1].file.return_value = {"commit_sha": "b" * 40, "content": "# New"}
    second = capture(review[0])
    assert first.pk != second.pk
    assert second.snapshot["documents"] != first.snapshot["documents"]


def test_missing_input_and_oversized_documents_are_not_passed(review):
    review[1].file.return_value["content"] = "x" * 300001
    with pytest.raises(ValidationError):
        capture(review[0])
    assert not RequirementReviewRun.objects.exists()


@pytest.mark.parametrize("case", ["path", "line", "evidence", "verdict", "duplicate"])
def test_model_cannot_invent_evidence_or_hide_blockers(case):
    finding = {
        "id": "F1",
        "severity": "blocking",
        "path": "prd.md",
        "line": 1,
        "evidence": "Actual",
        "reason": "Conflict",
        "suggestion": "Clarify",
    }
    value = {"verdict": "changes_requested", "summary": "Needs work", "findings": [finding]}
    if case == "path":
        finding["path"] = "invented.md"
    if case == "line":
        finding["line"] = 50
    if case == "evidence":
        finding["evidence"] = "invented"
    if case == "verdict":
        value["verdict"] = "passed"
    if case == "duplicate":
        value["findings"].append(dict(finding))
    with pytest.raises(ValueError):
        validate_result(value, {"documents": {"prd.md": "Actual"}})


def test_review_failure_retries_bounded_and_manual_retry_keeps_original(review):
    row = capture(review[0])
    with patch("plane.singularity.requirement_review_generation.generate", side_effect=RuntimeError("private content")):
        for _ in range(3):
            with pytest.raises(RuntimeError):
                execute(row.pk, "hatchet")
    row.refresh_from_db()
    assert row.status == "failed" and "private content" not in row.error
    retried = retry_run(review[0].owner, row, "retry-12345")
    assert retried.retry_of_id == row.pk and retried.attempts == 0
    assert retry_run(review[0].owner, row, "retry-12345").pk == retried.pk


def test_execution_lease_blocks_duplicate_worker(review):
    row = capture(review[0])
    row.lease_until = timezone.now() + timedelta(minutes=1)
    row.save()
    with pytest.raises(RuntimeError):
        execute(row.pk, "duplicate")


def test_completed_review_can_be_reassessed_without_rewriting_history(review, world):
    from plane.singularity.requirement_review import rereview_run, current_input

    row = ready(review)
    original = row.result.copy()
    new = rereview_run(world[0], row, "reassess-fixed-version")
    assert new.source_sha == row.source_sha and new.retry_of_id == row.pk
    assert new.snapshot["report_policy"] == "documents-report-v2"
    assert new.snapshot["documents"] == row.snapshot["documents"]
    assert rereview_run(world[0], row, "reassess-fixed-version").pk == new.pk
    row.refresh_from_db()
    assert row.result == original and row.status == "completed"
    with pytest.raises(WbsConflict, match="supersedes"):
        current_input(row)
    current_input(new)
    from plane.singularity.requirement_review_api import run_data

    assert run_data(row)["superseded"] is True
    assert run_data(new)["superseded"] is False
    assert run_data(new)["source_url"].endswith("/-/blob/" + row.source_sha)


def test_reassessment_cannot_change_adopted_version(review, world):
    from plane.singularity.requirement_review import rereview_run

    row = ready(review)
    adopt(world[0], row, {"target_sha": "b" * 40, "idempotency_key": "adopt-before-rereview"})
    with pytest.raises(WbsConflict, match="adopted or adopting"):
        rereview_run(world[0], row, "reassess-after-adoption")


def test_adoption_requires_pass_or_explicit_human_override(review, world):
    row = ready(review)
    row.result = {**result(), "verdict": "changes_requested"}
    row.save()
    data = {"target_sha": "b" * 40, "idempotency_key": "adopt-12345"}
    with pytest.raises(WbsConflict):
        adopt(world[0], row, data)
    override = {**data, "override": True, "confirmed": True, "reason": "Accepted business exception"}
    with pytest.raises(ValidationError):
        adopt(world[0], row, override)
    with pytest.raises(ValidationError):
        adopt(world[0], row, {**override, "reason": ""}, True)
    adoption = adopt(world[1], row, override, True)
    assert adoption.kind == "override" and adoption.actor == world[1]
    assert adopt(world[1], row, override, True).pk == adoption.pk
    row.refresh_from_db()
    assert row.result["verdict"] == "changes_requested"


@pytest.mark.parametrize("status", ["pending", "running", "completed"])
def test_same_version_reuses_adoption_with_new_key_and_actor(review, world, status):
    row = ready(review)
    first = adopt(world[0], row, {"target_sha": "b" * 40, "idempotency_key": "first-request"})
    first.status = status
    first.merged_sha = "c" * 40 if status == "completed" else ""
    first.save()
    repeated = adopt(world[1], row, {"target_sha": "c" * 40, "idempotency_key": "second-request"})
    assert repeated.pk == first.pk
    assert repeated.actor_id == world[0].pk
    assert RequirementAdoption.objects.count() == 1


def test_failed_adoption_can_retry_but_completed_version_cannot(review, world):
    row = ready(review)
    first = adopt(world[0], row, {"target_sha": "b" * 40, "idempotency_key": "first-request"})
    first.status = "failed"
    first.save()
    retry = adopt(world[0], row, {"target_sha": "b" * 40, "idempotency_key": "retry-request"})
    assert retry.pk != first.pk
    retry.status = "completed"
    retry.save()
    # A new review of the same document SHA is still the same adopted version.
    row.pk = None
    row.request_key = "another-review"
    row.save()
    assert adopt(world[0], row, {"target_sha": "c" * 40, "idempotency_key": "third-request"}).pk == retry.pk
    assert RequirementAdoption.objects.count() == 2


@pytest.mark.parametrize("status", ["pending", "running", "completed", "failed"])
def test_review_response_includes_version_adoption_status(review, world, status):
    from plane.singularity.requirement_review_api import run_data

    row = ready(review)
    first = adopt(world[0], row, {"target_sha": "b" * 40, "idempotency_key": "first-request"})
    first.status = status
    first.save()
    assert run_data(row)["adoption_status"] == (None if status == "failed" else status)


def test_concurrent_adoption_requests_create_one_operation(review, world):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from django.db import close_old_connections

    row = ready(review)
    barrier = Barrier(2)

    def request(key):
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            return adopt(world[0], row, {"target_sha": "b" * 40, "idempotency_key": key}).pk
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(request, ["concurrent-first", "concurrent-second"]))
    assert results[0] == results[1]
    assert RequirementAdoption.objects.count() == 1


def test_adoption_status_survives_history_pagination_and_new_version_is_available(review, world):
    row = ready(review)
    first = adopt(world[0], row, {"target_sha": "b" * 40, "idempotency_key": "first-request"})
    first.status = "completed"
    first.save()
    for index in range(21):
        RequirementAdoption.objects.create(
            config=row.config,
            run=row,
            actor=world[0],
            source_sha="d" * 40,
            target_sha="b" * 40,
            config_revision=1,
            kind="ai_passed",
            status="failed",
            request_key=f"historical-failure-{index}",
        )
    client = Client()
    client.force_login(world[0])
    url = (
        f"/api/singularity/v1/workspaces/{world[2].slug}/projects/{world[3].pk}/"
        f"work-items/{row.config_id}/requirement-review/"
    )
    response = client.get(url)
    assert response.status_code == 200
    assert str(first.pk) not in {item["id"] for item in response.json()["adoptions"]}
    assert response.json()["results"][0]["adoption_status"] == "completed"
    row.pk = None
    row.source_sha = "e" * 40
    row.request_key = "new-source-review"
    row.save()
    new = adopt(world[0], row, {"target_sha": "c" * 40, "idempotency_key": "new-source-adoption"})
    assert new.pk != first.pk and new.status == "pending"


def test_changed_basis_binding_and_removed_member_cannot_adopt(review, world):
    row = ready(review)
    row.config.issue.description_html = "Changed rules"
    row.config.issue.save()
    with pytest.raises(WbsConflict):
        adopt(world[0], row, {"target_sha": "b" * 40, "idempotency_key": "adopt-12345"})
    ProjectMember.objects.filter(project=row.config.issue.project, member=world[1]).delete()
    with pytest.raises(PermissionDenied):
        adopt(world[1], row, {"target_sha": "b" * 40, "idempotency_key": "adopt-12345"})
    assert not RequirementAdoption.objects.exists()


def test_webhook_authentication_deduplication_and_wakeup(review, monkeypatch):
    config, _ = review
    monkeypatch.setenv("DOCUMENT_REVIEW_WEBHOOK_SECRET", "test-hook")
    client = Client()
    url = f"/api/singularity/v1/requirement-review/push/{config.repository_id}/"
    payload = {"object_kind": "push", "project_id": 22, "ref": "refs/heads/draft/POS-1", "after": "a" * 40}
    assert client.post(url, payload, content_type="application/json").status_code == 403
    headers = {
        "HTTP_X_GITLAB_TOKEN": "test-hook",
        "HTTP_X_GITLAB_EVENT": "Push Hook",
        "HTTP_X_GITLAB_EVENT_UUID": "event-123",
    }
    assert client.post(url, payload, content_type="application/json", **headers).status_code == 202
    assert client.post(url, payload, content_type="application/json", **headers).json()["duplicate"]
    assert RequirementReviewEvent.objects.count() == 1


def test_dispatch_failure_persists_and_recovers(review):
    row = capture(review[0])
    task = Mock()
    task.run.side_effect = RuntimeError()
    dispatch_pending(task)
    row.refresh_from_db()
    assert row.error == "dispatch_unavailable"
    row.dispatch_at = timezone.now() - timedelta(minutes=7)
    row.save()
    task.run.side_effect = None
    task.run.return_value.workflow_run_id = "hatchet-run"
    dispatch_pending(task)
    row.refresh_from_db()
    assert row.hatchet_run_id == "hatchet-run"


def test_gate_requires_exact_running_grant_and_executor(review, world, monkeypatch):
    row = ready(review)
    grant = adopt(world[0], row, {"target_sha": "b" * 40, "idempotency_key": "adopt-12345"})
    monkeypatch.setenv("DOCUMENT_REVIEW_GATE_SECRET", "test-gate")
    monkeypatch.setenv("DOCUMENT_REVIEW_EXECUTOR_GL_ID", "user-99")
    payload = {
        "repository_id": str(row.config.repository_id),
        "ref": "refs/heads/POS-1",
        "old_sha": "b" * 40,
        "new_sha": "a" * 40,
        "actor": "user-99",
    }
    client = Client()
    url = "/api/singularity/v1/requirement-review/adoption-gate/"
    headers = {"HTTP_X_REVIEW_GATE_TOKEN": "test-gate"}
    assert client.post(url, payload, content_type="application/json", **headers).status_code == 403
    grant.status = "running"
    grant.save()
    assert client.post(url, payload, content_type="application/json", **headers).json()["allowed"]
    assert (
        client.post(url, {**payload, "new_sha": "c" * 40}, content_type="application/json", **headers).status_code
        == 403
    )
    assert (
        client.post(url, {**payload, "actor": "user-1"}, content_type="application/json", **headers).status_code == 403
    )


def test_rapid_pushes_are_reviewed_at_each_event_commit(review):
    config, provider = review
    for sha in ("a" * 40, "b" * 40):
        RequirementReviewEvent.objects.create(
            repository=config.repository, event_key=sha, branch=config.draft_branch, source_sha=sha
        )
    provider.resolve.side_effect = lambda repo, ref: ({}, "", ref if len(ref) == 40 else "b" * 40)
    provider.file.side_effect = lambda repo, sha, path: {"commit_sha": sha, "content": "# " + sha}
    poll_one()
    assert set(RequirementReviewRun.objects.values_list("source_sha", flat=True)) == {"a" * 40, "b" * 40}
    assert not RequirementReviewEvent.objects.filter(processed_at__isnull=True).exists()


def test_opening_editor_does_not_invalidate_review_but_business_changes_do(review):
    from plane.singularity.requirement_review import current_input

    row = ready(review)
    issue = row.config.issue
    issue.description_html = '<div><p class="editor-paragraph-block" data-id="new-id">AC01: Login page</p></div>'
    issue.save()
    assert current_input(row).pk == row.config_id
    assert capture(review[0]).pk == row.pk
    issue.description_html = "<p>AC01: Different page</p>"
    issue.save()
    with pytest.raises(WbsConflict):
        current_input(row)


def test_expired_last_execution_is_failed_and_can_be_retried(review):
    row = capture(review[0])
    row.status, row.attempts = "running", 3
    row.lease_until = timezone.now() - timedelta(minutes=1)
    row.save()
    dispatch_pending(Mock())
    row.refresh_from_db()
    assert row.status == "failed" and row.error == "execution_lease_expired"
    assert retry_run(review[0].owner, row, "retry-expired").status == "queued"


def mr_value(review, state="opened", source="a" * 40, merged=None):
    config = review[0]
    return {
        "iid": 7,
        "state": state,
        "sha": source,
        "merge_commit_sha": merged,
        "source_project_id": 22,
        "target_project_id": 22,
        "source_branch": config.draft_branch,
        "target_branch": config.adopted_branch,
    }


def test_adoption_merges_remote_mr_with_exact_sha_and_retains_draft(review, world):
    from plane.singularity.requirement_adoption import move_branch

    row = ready(review)
    grant = adopt(world[0], row, {"target_sha": "b" * 40, "idempotency_key": "adopt-writer"})
    http = Mock()
    http.get.side_effect = [mr_value(review), mr_value(review, "merged", merged="c" * 40)]
    with (
        patch("plane.singularity.requirement_adoption.ensure_merge_request", return_value=(http, "/mr/7")),
        patch("plane.singularity.requirement_adoption.provider_for", return_value=review[1]),
        patch("plane.singularity.requirement_adoption.target_head", side_effect=["b" * 40, "c" * 40]),
    ):
        assert move_branch(grant) == "c" * 40
        http.request.assert_called_once_with(
            "PUT", "/mr/7/merge", body={"sha": "a" * 40, "squash": "false", "should_remove_source_branch": "false"}
        )


def test_adoption_recovers_lost_merge_response_without_second_write(review, world):
    from plane.singularity.requirement_adoption import move_branch

    row = ready(review)
    grant = adopt(world[0], row, {"target_sha": "b" * 40, "idempotency_key": "adopt-recovery"})
    http = Mock()
    http.get.return_value = mr_value(review, "merged", merged="c" * 40)
    with (
        patch("plane.singularity.requirement_adoption.ensure_merge_request", return_value=(http, "/mr/7")),
        patch("plane.singularity.requirement_adoption.provider_for", return_value=review[1]),
        patch("plane.singularity.requirement_adoption.target_head", return_value="c" * 40),
    ):
        assert move_branch(grant) == "c" * 40
        http.request.assert_not_called()


@pytest.mark.parametrize("changed", ["source", "target", "closed", "repository"])
def test_stale_or_changed_mr_cannot_merge(review, world, changed):
    from plane.singularity.requirement_adoption import move_branch

    row = ready(review)
    grant = adopt(world[0], row, {"target_sha": "b" * 40, "idempotency_key": "adopt-stale"})
    http = Mock()
    mr = mr_value(review)
    if changed == "source":
        mr["sha"] = "d" * 40
    if changed == "closed":
        mr["state"] = "closed"
    if changed == "repository":
        mr["source_project_id"] = 23
    http.get.return_value = mr
    with (
        patch("plane.singularity.requirement_adoption.ensure_merge_request", return_value=(http, "/mr/7")),
        patch("plane.singularity.requirement_adoption.provider_for", return_value=review[1]),
        patch(
            "plane.singularity.requirement_adoption.target_head",
            return_value=("d" if changed == "target" else "b") * 40,
        ),
    ):
        with pytest.raises(ValueError):
            move_branch(grant)
        http.request.assert_not_called()


def test_review_waits_for_remote_merge_request(review):
    row = capture_snapshot(review[0])
    task = Mock()
    dispatch_pending(task)
    task.run.assert_not_called()
    row.merge_request = {"iid": 7}
    row.save()
    dispatch_pending(task)
    task.run.assert_called_once()


def test_merge_request_creation_reuses_remote_pair_after_lost_response(review):
    from plane.singularity.requirement_merge_request import ensure_merge_request

    row = capture_snapshot(review[0])
    http = Mock()
    http.get.return_value = [{**mr_value(review), "web_url": "https://git.example/mr/7"}]
    with patch("plane.singularity.requirement_merge_request.transport", return_value=http):
        _, path = ensure_merge_request(row)
        assert path.endswith("/merge_requests/7")
        http.request.assert_not_called()
        row.refresh_from_db()
        assert row.merge_request["iid"] == 7


def test_new_mr_is_created_before_review_and_keeps_both_branches(review):
    from plane.singularity.requirement_merge_request import ensure_merge_request

    row = capture_snapshot(review[0])
    http = Mock()
    http.get.return_value = []
    http.request.return_value = {"iid": 8, "web_url": "https://git.example/mr/8"}
    with patch("plane.singularity.requirement_merge_request.transport", return_value=http):
        ensure_merge_request(row)
    args = http.request.call_args
    assert args.args == ("POST", "/projects/22/merge_requests")
    assert args.kwargs["body"]["source_branch"] == "draft/POS-1"
    assert args.kwargs["body"]["target_branch"] == "POS-1"
    assert args.kwargs["body"]["remove_source_branch"] == "false"


def test_first_baseline_cannot_include_unreviewed_documents(review):
    config, provider = review
    provider.resolve.side_effect = lambda repo, ref: ({}, "", "a" * 40)
    provider.file.side_effect = lambda repo, sha, path: {
        "commit_sha": sha,
        "content": '{"base_sha":"' + "b" * 40 + '"}' if path.startswith(".singularity/") else "# Login",
    }
    provider.http.get.return_value = {"id": "c" * 40}
    with patch("plane.singularity.requirement_review.target_head", return_value="0" * 40):
        with pytest.raises(ValidationError):
            capture_snapshot(config)
    assert not RequirementReviewRun.objects.exists()


@pytest.mark.parametrize("verdict,expected", [("passed", "success"), ("changes_requested", "failed")])
def test_remote_status_uses_exact_reviewed_commit(review, verdict, expected):
    from plane.singularity.requirement_merge_request import report_one

    row = ready(review)
    row.result = result(verdict)
    row.save()
    http = Mock()
    with patch("plane.singularity.requirement_merge_request.transport", return_value=http):
        report_one()
        report_one()
    http.request.assert_called_once()
    assert http.request.call_args.args[1] == "/projects/22/statuses/" + row.source_sha
    assert http.request.call_args.kwargs["body"]["state"] == expected


def test_merge_gate_accepts_only_verified_merge_source_and_exact_old_target(review, world, monkeypatch):
    row = ready(review)
    grant = adopt(world[0], row, {"target_sha": "b" * 40, "idempotency_key": "adopt-merge-gate"})
    grant.status = "running"
    grant.save()
    monkeypatch.setenv("DOCUMENT_REVIEW_GATE_SECRET", "test-gate")
    monkeypatch.setenv("DOCUMENT_REVIEW_EXECUTOR_GL_ID", "user-99")
    payload = {
        "repository_id": str(row.config.repository_id),
        "ref": "refs/heads/POS-1",
        "old_sha": "b" * 40,
        "new_sha": "c" * 40,
        "merge_source": "a" * 40,
        "actor": "user-99",
    }
    client = Client()
    url = "/api/singularity/v1/requirement-review/adoption-gate/"
    headers = {"HTTP_X_REVIEW_GATE_TOKEN": "test-gate"}
    assert client.post(url, payload, content_type="application/json", **headers).status_code == 200
    for change in ({"merge_source": None}, {"old_sha": "d" * 40}, {"merge_source": "d" * 40}):
        assert client.post(url, {**payload, **change}, content_type="application/json", **headers).status_code == 403
    review[1].resolve.return_value = ({}, "", "d" * 40)
    with patch("plane.singularity.requirement_review_api.provider_for", return_value=review[1]):
        assert client.post(url, payload, content_type="application/json", **headers).status_code == 403
