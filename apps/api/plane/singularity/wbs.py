# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Shared session/MCP WBS commands. Hatchet receives only a persisted run ID."""

import hashlib
import json
import re
import os
from pathlib import Path

import nh3
from crum import impersonate
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.html import strip_tags
from markdown_it import MarkdownIt
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from plane.api.serializers import IssueSerializer
from plane.db.models import Issue, ProjectMember, WbsRun, WorkspaceMember
from .api import project_for, readable_items
from .authentication import DelegatedAuthentication


class WbsConflict(APIException):
    status_code = 409
    default_detail = "WBS version conflict"


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def require_member(user, project, write=False):
    """Recheck live membership for each command and background execution."""
    if not user.is_active or user.is_bot:
        raise PermissionDenied("Active human account required")
    if not WorkspaceMember.objects.filter(workspace=project.workspace, member=user, is_active=True).exists():
        raise PermissionDenied("Workspace membership required")
    if not ProjectMember.objects.filter(
        project=project, member=user, is_active=True, role__gte=15 if write else 5
    ).exists():
        raise PermissionDenied("Project member role required")


def source_snapshot(issue):
    text = strip_tags(issue.description_html or "").strip()
    criteria = list(dict.fromkeys(re.findall(r"\bAC[-_]?\d+\b", text, re.I))) or ["REQ-1"]
    children = list(Issue.issue_objects.filter(parent=issue).order_by("id").values("id", "name", "description_html"))
    return {
        "name": issue.name,
        "description_html": issue.description_html,
        "updated_at": issue.updated_at.isoformat(),
        "criteria": criteria,
        "existing_children": [{**child, "id": str(child["id"])} for child in children],
    }


def run_data(row):
    from .wbs_update import readiness

    return {
        "id": str(row.id),
        "issue_id": str(row.issue_id),
        "status": row.status,
        "hatchet_run_id": row.hatchet_run_id,
        "input_digest": row.input_digest,
        "source_version": row.snapshot["updated_at"],
        "result": row.result,
        "result_digest": row.result_digest,
        "error": row.error,
        "decision": row.decision,
        "decision_reason": row.decision_reason,
        "children": row.children,
        "execution": row.execution,
        "requested_by": str(row.requested_by_id),
        "reviewed_by": str(row.reviewed_by_id) if row.reviewed_by_id else None,
        "created_at": row.created_at,
        "reviewed_at": row.reviewed_at,
        "workflow": row.snapshot.get("workflow", 1),
        "source": row.snapshot.get("source"),
        "source_diff": row.snapshot.get("source_diff", ""),
        "scenario": row.snapshot.get("scenario"),
        "previous_run_id": row.snapshot.get("previous_run_id"),
        "existing_children": row.snapshot.get("existing_children", []),
        "readiness": readiness(row),
    }


@transaction.atomic
def start_run(user, issue, data):
    """Freeze the version explicitly submitted by a human; persist before dispatch."""
    require_member(user, issue.project, True)
    if (
        set(data) - {"expected_updated_at", "idempotency_key", "confirmed", "mode"}
        or not {"expected_updated_at", "idempotency_key", "confirmed"} <= set(data)
        or data.get("confirmed") is not True
        or data.get("mode", "update") not in ["update", "regenerate"]
    ):
        raise ValidationError("Confirm the saved requirement version before requesting a draft")
    key = data["idempotency_key"]
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", key):
        raise ValidationError("Invalid idempotency key")
    issue = Issue.issue_objects.select_for_update(of=("self",)).get(pk=issue.pk)
    old = WbsRun.objects.filter(issue=issue, requested_by=user, request_key=key).first()
    if old:
        if data.get("mode", "update") != old.snapshot.get("request_mode", "update"):
            raise WbsConflict("Idempotency key already used for another version")
        if data["expected_updated_at"] != old.snapshot["updated_at"]:
            raise WbsConflict("Idempotency key already used for another version")
        return old
    try:
        version = parse_datetime(data["expected_updated_at"])
    except (TypeError, ValueError):
        version = None
    if version != issue.updated_at:
        raise WbsConflict("Requirement changed; reload and confirm the current version")
    from plane.db.models import RequirementReviewConfig

    has_documents = RequirementReviewConfig.objects.filter(issue=issue).exists()
    if issue.parent_id or (not has_documents and not strip_tags(issue.description_html or "").strip()):
        raise ValidationError("A root requirement with a description is required")
    snapshot = source_snapshot(issue)
    skill_dir = os.environ.get("WBS_SKILL_DIR")
    if skill_dir:
        root = Path(skill_dir)
        files = {str(p.relative_to(root)): p.read_text(encoding="utf-8") for p in root.rglob("*.md")}
        if "SKILL.md" not in files or sum(len(x) for x in files.values()) > 150000:
            raise ValidationError("WBS skill is unavailable or exceeds the input limit")
        snapshot["skill_files"] = files
    if (
        data.get("mode") in ["update", "regenerate"]
        or has_documents
        or WbsRun.objects.filter(issue=issue, snapshot__workflow=2).exists()
    ):
        from .wbs_update import start_update

        return start_update(user, issue, data, snapshot.get("skill_files"))
    active = WbsRun.objects.filter(issue=issue, status__in=["queued", "running", "ready"]).first()
    if active:
        raise WbsConflict("An active draft already exists; review it before starting another")
    return WbsRun.objects.create(
        issue=issue, requested_by=user, request_key=key, snapshot=snapshot, input_digest=digest(snapshot)
    )


@transaction.atomic
def review_run(user, row, data):
    """Create all children atomically from the exact approved draft, at most once."""
    require_member(user, row.issue.project, True)
    issue = Issue.issue_objects.select_for_update(of=("self",)).get(pk=row.issue_id)
    row = WbsRun.objects.select_for_update().get(pk=row.pk)
    if set(data) - {
        "decision",
        "result_digest",
        "reason",
        "choices",
        "source_confirmed",
        "replacement_tasks",
    } or data.get("decision") not in ["approve", "reject"]:
        raise ValidationError("Explicit approve or reject required")
    if not data.get("result_digest") or data["result_digest"] != row.result_digest:
        raise WbsConflict("Draft version changed")
    if row.decision:
        if row.decision != data["decision"]:
            raise WbsConflict("This draft already has a different decision")
        if row.snapshot.get("workflow") == 2 and data.get("choices", {}) != row.execution.get("choices", {}):
            raise WbsConflict("This draft was approved with different task actions")
        if row.snapshot.get("workflow") == 2 and data.get("replacement_tasks", {}) != row.execution.get(
            "replacement_tasks", {}
        ):
            raise WbsConflict("This draft was approved with different replacement task content")
        return row
    if row.status != "ready":
        raise WbsConflict("Draft is not ready for review")
    if data["decision"] == "reject" and not str(data.get("reason", "")).strip():
        raise ValidationError("A rejection reason is required")
    if row.snapshot.get("workflow") == 2:
        from .wbs_update import review_update

        return review_update(user, row, data)
    if data["decision"] == "approve":
        from plane.db.models import RequirementReviewConfig

        if (
            RequirementReviewConfig.objects.filter(issue=issue).exists()
            or WbsRun.objects.filter(issue=issue, snapshot__workflow=2).exists()
        ):
            raise WbsConflict("Use Update WBS to analyze the current PRD before approval")
        if source_snapshot(issue) != {key: value for key, value in row.snapshot.items() if key != "skill_files"}:
            raise WbsConflict("Requirement or child tasks changed; reject this draft and regenerate")
        existing = {x["name"].strip().casefold() for x in row.snapshot["existing_children"]}
        for task in row.result["tasks"]:
            if task["title"].strip().casefold() in existing:
                raise WbsConflict("Draft duplicates an existing child task")
            markdown = (
                f"{task['scope']}\n\n## 产出\n{task['deliverable']}"
                f"\n\n## 验收标准\n{task['acceptance']}\n\n来源验收项：{', '.join(task['criteria'])}"
                f"\n\n依赖：{', '.join(task['dependencies']) or '无'}"
                f"\n\nWBS：{row.id} / {task['id']}\n\n责任角色：{task['role']}"
            )
            serializer = IssueSerializer(
                data={
                    "name": task["title"],
                    "description_html": nh3.clean(MarkdownIt().render(markdown)),
                    "parent": str(issue.id),
                    "external_source": "plane-wbs",
                    "external_id": f"{row.id}:{task['id']}",
                },
                context={
                    "project_id": issue.project_id,
                    "workspace_id": issue.workspace_id,
                    "default_assignee_id": None,
                },
            )
            serializer.is_valid(raise_exception=True)
            with impersonate(user):
                child = serializer.save()
            row.children[task["id"]] = str(child.id)
            existing.add(task["title"].strip().casefold())
        row.status = "completed"
    else:
        row.status = "rejected"
    row.decision, row.decision_reason = data["decision"], str(data.get("reason", ""))[:5000]
    row.reviewed_by, row.reviewed_at = user, timezone.now()
    row.save()
    return row


class WbsAPI(APIView):
    authentication_classes = [SessionAuthentication, DelegatedAuthentication]
    permission_classes = [IsAuthenticated]

    def context(self, request, slug, project_id, pk, write=False):
        project = project_for(request, slug, project_id)
        require_member(request.user, project, write)
        if request.auth is not None:
            scope = "workitems:write" if write else "workitems:read"
            if scope not in request.auth.scopes.split():
                raise PermissionDenied("Insufficient delegation scope")
        return get_object_or_404(readable_items(request, project), pk=pk)

    def get(self, request, slug, project_id, pk, run_id=None):
        issue = self.context(request, slug, project_id, pk)
        rows = WbsRun.objects.filter(issue=issue).order_by("-created_at")
        return Response(
            run_data(get_object_or_404(rows, pk=run_id))
            if run_id
            else {
                "results": [run_data(r) for r in rows[:20]],
                "source_version": issue.updated_at.isoformat(),
                "csrf_token": get_token(request),
                "can_start": not issue.parent_id,
            }
        )

    def post(self, request, slug, project_id, pk, run_id=None):
        issue = self.context(request, slug, project_id, pk, True)
        row = (
            review_run(request.user, get_object_or_404(WbsRun, pk=run_id, issue=issue), request.data)
            if run_id
            else start_run(request.user, issue, request.data)
        )
        return Response(run_data(row), status=200 if run_id else 202)
