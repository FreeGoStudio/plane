# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Authorized review queries, durable push intake and exact-version adoption grants."""

import hmac
import os
import re
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.middleware.csrf import get_token
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from plane.db.models import (
    ProjectRepository,
    RequirementReviewConfig,
    RequirementReviewRun,
    RequirementReviewEvent,
    RequirementAdoption,
)
from .wbs import WbsAPI, require_member
from .requirement_review import configure, retry_run, adopt, current_input, provider_for, target_head, version_adoption


def config_data(row):
    return {
        "revision": row.revision,
        "repository_id": str(row.repository_id),
        "draft_branch": row.draft_branch,
        "adopted_branch": row.adopted_branch,
        "paths": row.paths,
        "latest_sha": row.latest_sha,
        "adopted_sha": row.adopted_sha,
        "error": row.error,
        "enabled": row.enabled,
    }


def run_data(row):
    adoption = version_adoption(row)
    return {
        "id": str(row.pk),
        "source_sha": row.source_sha,
        "adoption_status": adoption.status if adoption else None,
        "merge_request": row.merge_request,
        "status": row.status,
        "result": row.result,
        "result_digest": row.result_digest,
        "error": row.error,
        "attempts": row.attempts,
        "hatchet_run_id": row.hatchet_run_id,
        "input_digest": row.input_digest,
        "rules": row.snapshot["rules"],
        "created_at": row.created_at,
        "retry_of": str(row.retry_of_id) if row.retry_of_id else None,
    }


def adoption_data(row):
    return {
        "id": str(row.pk),
        "run_id": str(row.run_id),
        "source_sha": row.source_sha,
        "target_sha": row.target_sha,
        "merged_sha": row.merged_sha,
        "merge_request": row.run.merge_request,
        "kind": row.kind,
        "reason": row.reason,
        "actor_id": str(row.actor_id),
        "status": row.status,
        "error": row.error,
        "created_at": row.created_at,
        "completed_at": row.completed_at,
    }


class RequirementReviewAPI(WbsAPI):
    """Browser and MCP share the same read/write permissions and version checks."""

    def get(self, request, slug, project_id, pk, run_id=None, action=None):
        issue = self.context(request, slug, project_id, pk)
        config = RequirementReviewConfig.objects.filter(issue=issue).first()
        if run_id:
            return Response(run_data(get_object_or_404(RequirementReviewRun, pk=run_id, config__issue=issue)))
        try:
            offset = int(request.query_params.get("offset", "0"))
            if offset < 0 or offset > 100000:
                raise ValueError
        except ValueError:
            raise ValidationError("Invalid offset") from None
        rows = RequirementReviewRun.objects.filter(config=config).order_by("-created_at")
        if request.query_params.get("source_sha"):
            rows = rows.filter(source_sha=request.query_params["source_sha"])
        batch = list(rows[offset : offset + 21])
        target_sha = ""
        target_error = ""
        if config:
            try:
                target_sha = target_head(config, provider_for(config))
            except Exception as error:
                target_error = getattr(error, "code", type(error).__name__)
        return Response(
            {
                "config": config_data(config) if config else None,
                "target_sha": target_sha,
                "target_error": target_error,
                "csrf_token": get_token(request),
                "results": [run_data(x) for x in batch[:20]],
                "next_offset": offset + 20 if len(batch) > 20 else None,
                "adoptions": [
                    adoption_data(x)
                    for x in RequirementAdoption.objects.filter(config=config).order_by("-created_at")[
                        offset : offset + 20
                    ]
                ],
            }
        )

    def post(self, request, slug, project_id, pk, run_id=None, action=None):
        issue = self.context(request, slug, project_id, pk, True)
        if action == "configure":
            return Response(config_data(configure(request.user, issue, request.data)), status=200)
        row = get_object_or_404(RequirementReviewRun, pk=run_id, config__issue=issue)
        if action == "retry":
            if set(request.data) != {"idempotency_key"}:
                raise ValidationError("Provide idempotency_key")
            return Response(run_data(retry_run(request.user, row, request.data["idempotency_key"])), status=202)
        if action == "adopt":
            return Response(
                adoption_data(adopt(request.user, row, request.data, human_session=request.auth is None)), status=202
            )
        raise ValidationError("Unknown operation")


def internal_secret(request, name, header):
    expected = os.environ.get(name, "")
    if not expected or not hmac.compare_digest(expected, request.headers.get(header, "")):
        raise PermissionDenied("Invalid service authentication")


class RequirementPushWebhook(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, repository_id):
        """Persist authenticated events before acknowledging; polling reads authoritative HEAD."""
        internal_secret(request, "DOCUMENT_REVIEW_WEBHOOK_SECRET", "X-Gitlab-Token")
        repo = get_object_or_404(ProjectRepository, pk=repository_id, enabled=True, purpose="documentation")
        data = request.data
        if (
            request.headers.get("X-Gitlab-Event") != "Push Hook"
            or data.get("object_kind") != "push"
            or str(data.get("project_id")) != repo.external_id
        ):
            raise ValidationError("Unexpected push event")
        ref, after = data.get("ref", ""), data.get("after", "")
        if not ref.startswith("refs/heads/") or not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", after):
            raise ValidationError("Invalid ref or commit")
        event_key = request.headers.get("X-Gitlab-Event-UUID", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", event_key):
            raise ValidationError("Event identifier required")
        with transaction.atomic():
            event, created = RequirementReviewEvent.objects.get_or_create(
                repository=repo, event_key=event_key, defaults={"branch": ref[11:], "source_sha": after}
            )
            if event.branch != ref[11:] or event.source_sha != after:
                raise ValidationError("Conflicting event identifier")
            RequirementReviewConfig.objects.filter(repository=repo, draft_branch=ref[11:], enabled=True).update(
                poll_after=None
            )
        return Response({"recorded": True, "duplicate": not created}, status=202)


class RequirementAdoptionGate(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        """Trusted GitLab hook checks every protected ref against a durable grant."""
        internal_secret(request, "DOCUMENT_REVIEW_GATE_SECRET", "X-Review-Gate-Token")
        data = request.data
        if set(data) not in (
            {"repository_id", "ref", "old_sha", "new_sha", "actor"},
            {"repository_id", "ref", "old_sha", "new_sha", "actor", "merge_source"},
        ):
            raise ValidationError("Invalid gate request")
        config = RequirementReviewConfig.objects.filter(
            repository_id=data["repository_id"], adopted_branch=str(data["ref"]).removeprefix("refs/heads/")
        ).first()
        if not config:
            return Response({"allowed": True, "reason": "unmanaged_branch"})
        from .document_executor import actor_matches

        legacy_actor = str(config.repository_id) in os.environ.get("DOCUMENT_REVIEW_GATED_REPOSITORIES", "").split(
            ","
        ) and data["actor"] == os.environ.get("DOCUMENT_REVIEW_EXECUTOR_GL_ID")
        if not config.enabled or not (legacy_actor or actor_matches(config.repository_id, data["actor"])):
            return Response({"allowed": False, "reason": "use_requirement_adoption"}, status=403)
        if data["old_sha"] == "0" * len(data["old_sha"]) and not config.adopted_sha:
            initial = RequirementReviewRun.objects.filter(config=config, snapshot__baseline_sha=data["new_sha"]).first()
            if initial:
                current_input(initial)
                return Response({"allowed": True, "reason": "initialize_requirement_baseline"})
        # merge_source is computed by the authenticated GitLab hook, only when
        # the merge has the exact old parent and the reviewed source's full tree.
        source = data.get("merge_source") or data["new_sha"]
        rows = RequirementAdoption.objects.filter(
            config=config,
            status="running",
            source_sha=source,
            target_sha=data["old_sha"],
            config_revision=config.revision,
        )
        row = rows.select_related("actor", "run", "config__issue__project").first()
        if not row:
            return Response({"allowed": False, "reason": "no_exact_adoption_grant"}, status=403)
        require_member(row.actor, config.issue.project, True)
        current_input(row.run)
        if not row.run.merge_request:
            return Response({"allowed": False, "reason": "merge_request_required"}, status=403)
        if provider_for(config).resolve(config.repository, config.draft_branch)[2] != source:
            return Response({"allowed": False, "reason": "source_changed"}, status=403)
        return Response({"allowed": True, "adoption_id": str(row.pk), "kind": row.kind, "checked_at": timezone.now()})
