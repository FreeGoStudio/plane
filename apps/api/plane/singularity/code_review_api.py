# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Project-scoped code review API, shared by browser and delegated callers."""

from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from plane.db.models import CodeReviewLink, CodeReviewRun, ProjectRepository
from .wbs import WbsAPI
from .code_review import add_link, remove_link, revision, rerun
from .code_review_provider import list_merge_requests
from .repository_transport import RepositoryError
from .code_review_decisions import decide
from .code_review_gate import accepted_decision
from .wbs import require_member
from plane.db.models import CodeReviewDecision, CodeReviewEvent
from .review_report import compare_findings


def decision_data(row):
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "run_id",
            "actor_id",
            "kind",
            "reason",
            "report_digest",
            "input_digest",
            "revision",
            "created_at",
        )
    }


def run_data(row):
    """Project fixed-revision source links and exact finding comparisons for authorized readers."""
    value = {
        key: getattr(row, key)
        for key in (
            "id",
            "generation",
            "source_sha",
            "target_sha",
            "merge_base",
            "snapshot",
            "status",
            "report",
            "report_digest",
            "input_digest",
            "error",
            "attempts",
            "created_at",
            "finished_at",
            "link_id",
        )
    }
    previous = (
        CodeReviewRun.objects.filter(link_id=row.link_id, created_at__lt=row.created_at, status="completed")
        .order_by("-created_at")
        .first()
    )
    repo = row.link.repository
    value["source_url"] = repo.instance.web_url.rstrip("/") + "/" + repo.path + "/-/blob/" + row.source_sha
    value["comparison"] = (
        {
            "previous_run_id": str(previous.pk),
            "previous_source_sha": previous.source_sha,
            "same_source": previous.source_sha == row.source_sha,
            "findings": compare_findings(row.report.get("findings", []), previous.report.get("findings", [])),
        }
        if previous and row.status == "completed"
        else None
    )
    return value


def link_data(row):
    value = {
        key: getattr(row, key)
        for key in ("id", "repository_id", "mr_iid", "active", "generation", "version", "current_run_id", "error")
    }
    value["accepted"] = bool(row.active and accepted_decision(row))
    return value


class CodeReviewAPI(WbsAPI):
    def handle_exception(self, exc):
        if isinstance(exc, RepositoryError):
            return Response({"error": exc.code}, status=exc.status)
        return super().handle_exception(exc)

    def get(self, request, slug, project_id, pk, run_id=None, link_id=None, action=None):
        issue = self.context(request, slug, project_id, pk)
        if action == "merge-requests":
            repo = get_object_or_404(
                ProjectRepository,
                pk=request.query_params.get("repository_id"),
                project=issue.project,
                purpose="development",
                enabled=True,
                instance__provider="gitlab",
            )
            try:
                page = int(request.query_params.get("page", 1))
                if not 1 <= page <= 10000:
                    raise ValueError()
            except ValueError:
                raise ValidationError("Invalid page") from None
            return Response({"results": list_merge_requests(repo, page)})
        runs = CodeReviewRun.objects.filter(link__issue=issue).order_by("-created_at")
        if run_id:
            row = get_object_or_404(runs, pk=run_id)
            return Response(
                {
                    **run_data(row),
                    "raw_report": row.raw_report,
                    "decisions": [
                        decision_data(d) for d in CodeReviewDecision.objects.filter(run=row).order_by("revision")
                    ],
                }
            )
        try:
            offset = int(request.query_params.get("offset", 0))
            if not 0 <= offset <= 100000:
                raise ValueError()
        except ValueError:
            raise ValidationError("Invalid offset") from None
        rows = list(runs[offset : offset + 21])
        links = list(
            CodeReviewLink.objects.filter(issue=issue)
            .select_related("current_run", "issue__project")
            .order_by("created_at")
        )
        try:
            require_member(request.user, issue.project, True)
            can_edit = True
        except PermissionDenied:
            can_edit = False
        return Response(
            {
                "revision": revision(issue),
                "csrf_token": get_token(request),
                "can_edit": can_edit,
                "events": list(
                    CodeReviewEvent.objects.filter(issue=issue)
                    .order_by("-created_at")
                    .values("id", "kind", "actor_id", "payload", "created_at")[:50]
                ),
                "evidence_inconsistent": issue.state.group == "completed"
                and any(link.active and not accepted_decision(link) for link in links),
                "current_runs": [run_data(link.current_run) for link in links if link.active and link.current_run],
                "decisions": [
                    decision_data(d)
                    for d in CodeReviewDecision.objects.filter(
                        run_id__in=[link.current_run_id for link in links]
                    ).order_by("created_at")
                ],
                "links": [link_data(row) for row in CodeReviewLink.objects.filter(issue=issue).order_by("created_at")],
                "runs": [run_data(row) for row in rows[:20]],
                "next_offset": offset + 20 if len(rows) > 20 else None,
            }
        )

    def post(self, request, slug, project_id, pk, run_id=None, link_id=None, action=None):
        issue = self.context(request, slug, project_id, pk, True)
        if action == "links":
            return Response(link_data(add_link(request.user, issue, request.data)), status=201)
        if action == "remove":
            link = get_object_or_404(CodeReviewLink, pk=link_id, issue=issue)
            return Response(link_data(remove_link(request.user, link, request.data)))
        if action == "rerun":
            link = get_object_or_404(CodeReviewLink, pk=link_id, issue=issue)
            return Response(run_data(rerun(request.user, link, request.data)), status=202)
        if action == "decisions":
            row = get_object_or_404(CodeReviewRun, pk=run_id, link__issue=issue)
            session = (
                isinstance(request.successful_authenticator, SessionAuthentication)
                and not request.headers.get("Authorization")
                and not request.headers.get("X-Api-Key")
            )
            return Response(decision_data(decide(request.user, row, request.data, human_session=session)), status=201)
        raise ValidationError("Unknown code review operation")
