# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Shared completion checks; callers keep the issue lock until the state write commits."""

from django.db import transaction, models
from rest_framework.exceptions import PermissionDenied
from plane.db.models import Issue, State, CodeReviewLink, CodeReviewDecision
from . import code_review as reviews
from .wbs import require_member
from .repository_transport import RepositoryError


def accepted_decision(link):
    run = link.current_run
    if not run or run.status != "completed" or not reviews.eligible(link.version) or link.error:
        return None
    decision = CodeReviewDecision.objects.filter(run=run).order_by("-revision").first()
    if (
        not decision
        or decision.kind != "accepted"
        or decision.report_digest != run.report_digest
        or decision.input_digest != run.input_digest
    ):
        return None
    try:
        require_member(decision.actor, link.issue.project, True)
    except PermissionDenied:
        return None
    return decision


@transaction.atomic
def check_completion(issue):
    reviews.lock_issue(issue.pk)
    links = CodeReviewLink.objects.filter(issue=issue, active=True).select_related(
        "current_run", "repository__instance", "issue__project"
    )
    for link in links:
        try:
            current = reviews.remote_version(link)
        except RepositoryError:
            raise reviews.ReviewUnavailable(
                {"issue_id": str(issue.pk), "link_id": str(link.pk), "reason": "remote_verification_unavailable"}
            ) from None
        if current != link.version:
            raise reviews.ReviewConflict(
                {"issue_id": str(issue.pk), "link_id": str(link.pk), "reason": "mr_version_changed"}
            )
        if not accepted_decision(link) or link.current_run.snapshot["settings"] != reviews.review_settings():
            raise reviews.ReviewConflict(
                {"issue_id": str(issue.pk), "link_id": str(link.pk), "reason": "current_report_not_accepted"}
            )


def guard_issue_save(issue, kwargs):
    if issue._state.adding or (
        kwargs.get("update_fields") is not None and not {"state", "state_id"}.intersection(kwargs["update_fields"])
    ):
        return
    # Serialize assignments with concurrent changes to the target State group.
    if issue.state_id:
        State.all_state_objects.select_for_update().get(pk=issue.state_id)
    old = reviews.lock_issue(issue.pk)
    if (
        old.state_id != issue.state_id
        and issue.state_id
        and State.objects.filter(pk=issue.state_id, group="completed").exists()
    ):
        check_completion(old)


def guard_state_save(state, kwargs):
    if state._state.adding or (kwargs.get("update_fields") is not None and "group" not in kwargs["update_fields"]):
        return
    old = State.all_state_objects.select_for_update().get(pk=state.pk)
    if old.group != "completed" and state.group == "completed":
        for issue in Issue.all_objects.filter(state=state).order_by("pk"):
            check_completion(issue)


@transaction.atomic
def guarded_update(queryset, kwargs):
    """Evaluate SQL expressions (including bulk_update CASE) under row locks."""
    kind = queryset.model._meta.label_lower
    field = "group" if kind == "db.state" else "state_id"
    key = next((k for k in kwargs if k in (("group",) if kind == "db.state" else ("state", "state_id"))), None)
    if not key:
        return models.QuerySet.update(queryset, **kwargs)
    ids = list(queryset.order_by("pk").values_list("pk", flat=True))
    scoped = queryset.filter(pk__in=ids)
    value = kwargs[key]
    expression = (
        value
        if hasattr(value, "resolve_expression")
        else models.Value(
            getattr(value, "pk", value), output_field=models.CharField() if kind == "db.state" else models.UUIDField()
        )
    )
    targets = list(scoped.annotate(review_target_value=expression).values_list("pk", field, "review_target_value"))
    target_ids = [new for _, _, new in targets if new] if kind == "db.issue" else []
    if kind == "db.state":
        target_ids = ids
    locked_states = list(State.all_state_objects.filter(pk__in=target_ids).order_by("pk").select_for_update())
    # Match model saves: State locks first, then Issue locks. Re-evaluate SQL
    # expressions after acquiring locks, because another writer may have won.
    list(scoped.order_by("pk").select_for_update().values_list("pk", flat=True))
    targets = list(scoped.annotate(review_target_value=expression).values_list("pk", field, "review_target_value"))
    if kind == "db.issue" and any(new and new not in target_ids for _, _, new in targets):
        raise reviews.ReviewConflict("Concurrent state change; retry")
    completed_states = {s.pk for s in locked_states if s.group == "completed"}
    for pk, old, new in targets:
        if old == new:
            continue
        if kind == "db.issue" and new in completed_states:
            check_completion(Issue.all_objects.get(pk=pk))
        elif kind == "db.state" and new == "completed":
            for issue in Issue.all_objects.filter(state_id=pk).order_by("pk"):
                check_completion(issue)
    return models.QuerySet.update(scoped, **kwargs)
