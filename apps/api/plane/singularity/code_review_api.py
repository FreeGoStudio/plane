# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Project-scoped code review API, shared by browser and delegated callers."""

from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from plane.db.models import CodeReviewLink, CodeReviewRun, ProjectRepository
from .wbs import WbsAPI
from .code_review import add_link, remove_link, revision, rerun
from .code_review_provider import list_merge_requests
from .repository_transport import RepositoryError


def run_data(row):
    return {
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


def link_data(row):
    return {
        key: getattr(row, key)
        for key in ("id", "repository_id", "mr_iid", "active", "generation", "version", "current_run_id", "error")
    }


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
            return Response({**run_data(row), "raw_report": row.raw_report})
        try:
            offset = int(request.query_params.get("offset", 0))
            if not 0 <= offset <= 100000:
                raise ValueError()
        except ValueError:
            raise ValidationError("Invalid offset") from None
        rows = list(runs[offset : offset + 21])
        return Response(
            {
                "revision": revision(issue),
                "csrf_token": get_token(request),
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
        raise ValidationError("Unknown code review operation")
