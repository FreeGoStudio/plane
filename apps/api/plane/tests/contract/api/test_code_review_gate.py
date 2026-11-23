# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
# ruff: noqa: F811
from unittest.mock import patch
import pytest
from rest_framework.exceptions import PermissionDenied, ValidationError
from plane.db.models import State, Issue, ProjectMember
from plane.singularity.wbs import digest
from .test_code_review import review, associate  # noqa: F401
from .test_singularity import world, config  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True)


def ready(review):
    link = associate(review)
    run = link.current_run
    run.status = "completed"
    run.report = {"summary": "完整", "findings": []}
    run.report_digest = digest(run.report)
    run.save()
    return run


def accept(review, run, **overrides):
    from plane.singularity.code_review_decisions import decide

    return decide(
        review[0],
        run,
        {
            "decision": "accepted",
            "reason": "",
            "idempotency_key": "decision-one",
            "report_digest": run.report_digest,
            "input_digest": run.input_digest,
            "expected_decision_revision": 0,
            **overrides,
        },
        human_session=True,
    )


def complete_state(review):
    return State.objects.create(
        name="Done", group="completed", color="#00ff00", project=review[1].project, workspace=review[1].workspace
    )


def test_self_confirmation_unlocks_but_does_not_complete(review):
    run = ready(review)
    accept(review, run)
    review[1].refresh_from_db()
    assert review[1].state.group != "completed"
    review[1].state = complete_state(review)
    review[1].save()
    review[1].refresh_from_db()
    assert review[1].state.group == "completed"


def test_model_save_and_queryset_update_cannot_bypass_gate(review):
    from plane.singularity.code_review import ReviewConflict

    associate(review)
    state = complete_state(review)
    with pytest.raises(ReviewConflict):
        Issue.objects.filter(pk=review[1].pk).update(state=state)
    review[1].state = state
    with pytest.raises(ReviewConflict):
        review[1].save()
    with pytest.raises(ReviewConflict):
        Issue.objects.bulk_update([review[1]], ["state"])
    review[1].refresh_from_db()
    assert review[1].state.group != "completed"


def test_editing_state_group_cannot_bypass_gate(review):
    from plane.singularity.code_review import ReviewConflict

    associate(review)
    state = review[1].state
    state.group = "completed"
    with pytest.raises(ReviewConflict):
        state.save()
    with pytest.raises(ReviewConflict):
        State.objects.filter(pk=state.pk).update(group="completed")


def test_program_cannot_confirm_and_findings_require_reason(review):
    from plane.singularity.code_review_decisions import decide

    run = ready(review)
    with pytest.raises(PermissionDenied):
        decide(review[0], run, {}, human_session=False)
    run.report["findings"] = [{"message": "problem"}]
    run.report_digest = digest(run.report)
    run.save()
    with pytest.raises(ValidationError):
        accept(review, run)
    accept(review, run, reason="已核实可以接受")


def test_revoked_reviewer_and_remote_outage_block_completion(review):
    from plane.singularity.code_review_gate import check_completion
    from plane.singularity.code_review import ReviewConflict, ReviewUnavailable
    from plane.singularity.repository_transport import RepositoryError

    run = ready(review)
    accept(review, run)
    with patch("plane.singularity.code_review.remote_version", side_effect=RepositoryError("offline", 503)):
        with pytest.raises(ReviewUnavailable):
            check_completion(review[1])
    ProjectMember.objects.filter(project=review[1].project, member=review[0]).update(role=5)
    with pytest.raises(ReviewConflict):
        check_completion(review[1])


def test_completed_task_stays_completed_after_new_commit(review):
    from plane.singularity.code_review import capture
    from django.db import transaction

    run = ready(review)
    accept(review, run)
    review[1].state = complete_state(review)
    review[1].save()
    with transaction.atomic():
        capture(run.link, {**review[3], "source_sha": "d" * 40})
    review[1].refresh_from_db()
    assert review[1].state.group == "completed"


@pytest.mark.parametrize("status", ["partial", "failed", "cancelled", "running"])
def test_incomplete_run_cannot_be_accepted(review, status):
    from plane.singularity.code_review import ReviewConflict

    run = ready(review)
    run.status = status
    run.save()
    with pytest.raises(ReviewConflict):
        accept(review, run)


def test_null_state_resolves_completed_default_before_gate(review):
    from plane.singularity.code_review import ReviewConflict

    associate(review)
    state = complete_state(review)
    State.objects.filter(project=review[1].project).update(default=False)
    state.default = True
    state.save()
    review[1].state = None
    with pytest.raises(ReviewConflict):
        review[1].save()


def test_changed_model_configuration_cannot_be_accepted(review, monkeypatch):
    from plane.singularity.code_review import ReviewConflict

    run = ready(review)
    monkeypatch.setenv("CODE_REVIEW_MODEL", "changed-model")
    with pytest.raises(ReviewConflict):
        accept(review, run)


def test_second_mr_and_new_remote_commit_block_completed_state(review):
    from plane.singularity.code_review import add_link, revision, ReviewConflict

    run = ready(review)
    accept(review, run)
    add_link(
        review[0],
        review[1],
        {"repository_id": str(review[2].pk), "mr_iid": 8, "expected_revision": revision(review[1])},
    )
    review[1].state = complete_state(review)
    with pytest.raises(ReviewConflict):
        review[1].save()


def test_api_human_decision_and_delegated_denial(review):
    from django.test import Client
    from .test_singularity import login

    run = ready(review)
    issue = review[1]
    path = (
        f"/api/singularity/v1/workspaces/{issue.workspace.slug}/projects/{issue.project_id}/"
        f"work-items/{issue.pk}/code-review/runs/{run.pk}/decisions/"
    )
    body = {
        "decision": "accepted",
        "idempotency_key": "web-one",
        "expected_decision_revision": 0,
        "report_digest": run.report_digest,
        "input_digest": run.input_digest,
    }
    delegated, _, _, _ = login(review[0])
    assert delegated.post(path, body, content_type="application/json").status_code == 403
    client = Client()
    client.force_login(review[0])
    response = client.post(path, body, content_type="application/json")
    assert response.status_code == 201, response.content
