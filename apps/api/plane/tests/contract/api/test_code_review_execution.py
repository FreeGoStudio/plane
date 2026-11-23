# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
# ruff: noqa: F811
import copy
from datetime import timedelta
from unittest.mock import patch
import pytest
from django.utils import timezone
from .test_code_review import review, associate  # noqa: F401
from .test_singularity import world, config  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def raw_report():
    return {
        "status": "completed",
        "comments": [],
        "manifest": {
            "schema_version": "ocr.run-manifest/v1",
            "operation": "review",
            "terminal_state": "complete",
            "input": {"mode": "range", "resolved_base": "c" * 40, "resolved_head": "a" * 40},
            "coverage": {
                "selected": [{"path": "src/a.py", "item_id": "1"}],
                "completed": [{"path": "src/a.py", "item_id": "1"}],
                "reused": [],
                "failed": [],
                "waived": [],
                "excluded": [],
            },
        },
    }


@pytest.mark.parametrize("case", ["complete", "missing", "partial", "budget", "wrong_sha", "unknown_schema", "exit"])
def test_coverage_not_exit_code_determines_completion(case):
    from plane.singularity.code_review_runner import normalize_report

    value = copy.deepcopy(raw_report())
    paths = ["src/a.py"]
    if case == "missing":
        paths.append("src/missing.py")
    if case == "partial":
        value["manifest"]["coverage"]["completed"] = []
    if case == "budget":
        value["summary"] = {"budget_exceeded": True}
    if case == "wrong_sha":
        value["manifest"]["input"]["resolved_head"] = "b" * 40
    if case == "unknown_schema":
        value["manifest"]["schema_version"] = "unknown"
    status, report = normalize_report(value, paths, "c" * 40, "a" * 40, 1 if case == "exit" else 0)
    assert (status == "completed") == (case == "complete")
    assert report["coverage"]["diff_files"] == paths


def test_duplicate_dispatch_executes_once(review):
    from plane.singularity.code_review_execution import execute

    row = associate(review).current_run
    with patch(
        "plane.singularity.code_review_execution.run_ocr",
        return_value=("completed", raw_report(), {"summary": "完成", "findings": [], "coverage": {}}),
    ) as runner:
        execute(row.pk, "hatchet-1")
        execute(row.pk, "hatchet-2")
        assert runner.call_count == 1
    row.refresh_from_db()
    assert row.attempts == 1 and row.status == "completed" and row.report_digest


def test_transient_attempts_bounded_and_expired_lease_recovers(review):
    from plane.singularity.code_review_execution import execute
    from plane.singularity.code_review_runner import ExecutionFailure

    row = associate(review).current_run
    with patch("plane.singularity.code_review_execution.run_ocr", side_effect=ExecutionFailure("network", True)):
        for index in range(5):
            execute(row.pk, str(index))
    row.refresh_from_db()
    assert row.attempts == 3 and row.status == "failed"


def test_old_execution_token_cannot_overwrite_new_owner(review):
    from plane.singularity.code_review_execution import execute
    from plane.db.models import CodeReviewRun
    import uuid

    row = associate(review).current_run

    def steal_lease(run):
        CodeReviewRun.objects.filter(pk=run.pk).update(
            execution_token=uuid.uuid4(), lease_until=timezone.now() + timedelta(minutes=31)
        )
        return "completed", raw_report(), {"summary": "late"}

    with patch("plane.singularity.code_review_execution.run_ocr", side_effect=steal_lease):
        execute(row.pk, "old")
    row.refresh_from_db()
    assert row.status == "running" and row.report == {}


def test_lifecycle_and_target_changes_never_revive_confirmation(review):
    from plane.singularity.code_review import capture
    from django.db import transaction

    link = associate(review)
    first = link.current_run_id
    version = copy.deepcopy(review[3])
    with transaction.atomic():
        version["draft"] = True
        capture(link, version)
        assert link.current_run_id is None
        version["draft"] = False
        capture(link, version)
        assert link.current_run_id != first


def test_authenticated_events_are_durable_and_idempotent(review, monkeypatch):
    from django.test import Client
    from plane.db.models import CodeReviewEvent

    monkeypatch.setenv("CODE_REVIEW_WEBHOOK_SECRET", "isolated-test-secret")
    url = f"/api/singularity/v1/code-review/events/{review[2].pk}/"
    client = Client()
    payload = {"object_kind": "merge_request", "project": {"id": 22}, "object_attributes": {"iid": 7}}
    assert client.post(url, payload, content_type="application/json").status_code == 403
    for _ in range(2):
        response = client.post(
            url,
            payload,
            content_type="application/json",
            HTTP_X_GITLAB_TOKEN="isolated-test-secret",
            HTTP_X_GITLAB_EVENT="Merge Request Hook",
            HTTP_X_GITLAB_EVENT_UUID="event-one",
        )
        assert response.status_code == 202, response.content
    assert CodeReviewEvent.objects.filter(event_key="event-one").count() == 1


def test_manual_rerun_supersedes_same_version_idempotently(review):
    from plane.singularity.code_review import rerun, revision

    link = associate(review)
    old_id = link.current_run_id
    data = {"expected_revision": revision(link.issue), "idempotency_key": "rerun-one"}
    new = rerun(review[0], link, data)
    assert rerun(review[0], link, data).pk == new.pk
    link.refresh_from_db()
    assert link.current_run_id == new.pk != old_id
