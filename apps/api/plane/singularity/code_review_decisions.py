# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Append-only human decisions, bound to one current report."""

from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError
from plane.db.models import CodeReviewDecision
from . import code_review as reviews
from .wbs import require_member


@transaction.atomic
def decide(user, run, data, human_session=False):
    if not human_session:
        raise PermissionDenied("A logged-in human session is required")
    require_member(user, run.link.issue.project, True)
    reviews.lock_issue(run.link.issue_id)
    run.refresh_from_db()
    link = run.link
    link.refresh_from_db()
    key = reviews.request_key(data)
    previous = CodeReviewDecision.objects.filter(run=run, request_key=key).first()
    if previous:
        if previous.actor_id != user.pk or previous.kind != data.get("decision"):
            raise reviews.ReviewConflict("Decision key already used")
        return previous
    count = CodeReviewDecision.objects.filter(run=run).count()
    if data.get("expected_decision_revision") != count:
        raise reviews.ReviewConflict("Decision changed; refresh")
    kind = data.get("decision")
    reason = str(data.get("reason", "")).strip()
    if kind not in ("accepted", "returned") or len(reason) > 5000:
        raise ValidationError("Invalid decision or reason")
    if (
        not link.active
        or link.current_run_id != run.pk
        or not reviews.eligible(link.version)
        or data.get("report_digest") != run.report_digest
        or data.get("input_digest") != run.input_digest
    ):
        raise reviews.ReviewConflict("Report is no longer current")
    if reviews.remote_version(link) != link.version:
        raise reviews.ReviewConflict("MR changed; wait for a current report")
    if kind == "accepted":
        if run.snapshot["settings"] != reviews.review_settings():
            raise reviews.ReviewConflict("Review configuration changed")
        if run.status != "completed" or not run.report_digest:
            raise reviews.ReviewConflict("Only a complete report can be accepted")
        if run.report.get("findings") and not reason:
            raise ValidationError("Accepting findings requires a reason")
    decision = CodeReviewDecision.objects.create(
        run=run,
        actor=user,
        kind=kind,
        reason=reason,
        report_digest=run.report_digest,
        input_digest=run.input_digest,
        revision=count + 1,
        request_key=key,
    )
    reviews.audit(link, "decision", user, run_id=str(run.pk), decision_id=str(decision.pk), decision=kind)
    return decision
