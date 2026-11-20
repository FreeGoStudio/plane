# ruff: noqa: F811
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Document pushes, immutable review conclusions and explicit human overrides."""

from datetime import timedelta
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
from plane.singularity.requirement_review import configure, capture, adopt, retry_run, poll_one, WbsConflict
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
    provider.resolve.return_value = ({}, "", "a" * 40, None)
    provider.file.return_value = {"commit_sha": "a" * 40, "content": "# Login\nAC01: Login page"}
    with patch("plane.singularity.requirement_review.provider_for", return_value=provider):
        yield row, provider


def result(verdict="passed"):
    return {"verdict": verdict, "summary": "Reviewed", "findings": []}


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


def test_consecutive_commits_keep_both_results(review):
    first = ready(review)
    review[1].resolve.return_value = ({}, "", "b" * 40, None)
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
    provider.resolve.side_effect = lambda repo, ref: ({}, "", ref if len(ref) == 40 else "b" * 40, None)
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


def test_adoption_writer_checks_ancestry_and_uses_exact_lease(review, world, monkeypatch, tmp_path):
    from plane.singularity.requirement_adoption import move_branch

    row = ready(review)
    grant = adopt(world[0], row, {"target_sha": "b" * 40, "idempotency_key": "adopt-writer"})
    token = tmp_path / "token"
    token.write_text("test-private-token")
    monkeypatch.setenv("DOCUMENT_ADOPTION_TOKEN_FILE", str(token))
    review[1].metadata.return_value = {"path": "team/docs"}
    with (
        patch("plane.singularity.requirement_adoption.provider_for", return_value=review[1]),
        patch("plane.singularity.requirement_adoption.target_head", return_value="b" * 40),
        patch("plane.singularity.requirement_adoption.subprocess.run") as process,
    ):
        process.return_value = Mock(returncode=0, stdout=b"")
        move_branch(grant)
        commands = [call.args[0] for call in process.call_args_list]
        assert any("merge-base" in cmd and "--is-ancestor" in cmd for cmd in commands)
        push = next(cmd for cmd in commands if "push" in cmd)
        assert "--force-with-lease=refs/heads/POS-1:" + "b" * 40 in push
        assert "a" * 40 + ":refs/heads/POS-1" in push
        assert "test-private-token" not in str(commands)


def test_adoption_recovers_lost_push_response_without_second_write(review, world):
    from plane.singularity.requirement_adoption import move_branch

    row = ready(review)
    grant = adopt(world[0], row, {"target_sha": "b" * 40, "idempotency_key": "adopt-recovery"})
    with (
        patch("plane.singularity.requirement_adoption.provider_for", return_value=review[1]),
        patch("plane.singularity.requirement_adoption.target_head", return_value=row.source_sha),
        patch("plane.singularity.requirement_adoption.subprocess.run") as process,
    ):
        move_branch(grant)
        process.assert_not_called()
