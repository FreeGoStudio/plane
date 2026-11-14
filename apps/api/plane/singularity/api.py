# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Narrow, delegated work-item API; authorization stays in Plane."""

import json
import uuid
from functools import partial
from types import SimpleNamespace
from urllib.parse import quote

import nh3
from markdown_it import MarkdownIt
from crum import impersonate
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from plane.api.serializers import IssueSerializer
from plane.app.permissions import ROLE, allow_permission
from plane.app.permissions.project import ProjectEntityPermission
from plane.bgtasks.issue_activities_task import issue_activity
from plane.bgtasks.webhook_task import model_activity
from plane.db.models import (
    DelegationAudit,
    DiscussionReceipt,
    Issue,
    Label,
    Project,
    ProjectMember,
    State,
    WorkspaceMember,
)
from .oauth import digest
from .authentication import DelegatedAuthentication
from plane.api.rate_limit import ApiKeyRateThrottle


class PersonalThrottle(SimpleRateThrottle):
    rate = "60/min"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": "singularity", "ident": str(request.user.pk)}


class WriteThrottle(SimpleRateThrottle):
    rate = "15/min"

    def get_cache_key(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        return self.cache_format % {
            "scope": "singularity_write",
            "ident": f"{request.user.pk}:{view.kwargs.get('project_id')}",
        }


class DelegatedAPI(APIView):
    authentication_classes = [DelegatedAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [ApiKeyRateThrottle]

    def require_scopes(self, request, *scopes):
        if not set(scopes) <= set(request.auth.scopes.split()):
            raise PermissionDenied("Insufficient delegation scope")

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        trace = uuid.uuid4()
        DelegationAudit.objects.create(
            trace_id=trace,
            grant=getattr(getattr(request, "auth", None), "grant", None),
            operation=f"{request.method}:{self.__class__.__name__}",
            resource=str(kwargs.get("pk") or kwargs.get("project_id") or ""),
            status=response.status_code,
        )
        response["X-Trace-ID"] = str(trace)
        response["Cache-Control"] = "no-store"
        return response


def visible_projects(user):
    workspaces = WorkspaceMember.objects.filter(member=user, is_active=True).values("workspace_id")
    memberships = ProjectMember.objects.filter(member=user, is_active=True).values("project_id")
    return Project.objects.filter(workspace_id__in=workspaces).filter(Q(pk__in=memberships) | Q(network=2))


def project_for(request, slug, project_id):
    return get_object_or_404(visible_projects(request.user), pk=project_id, workspace__slug=slug)


def can_write(request, slug, project_id, item=None):
    """Evaluate the same creator/member/admin decorator used by the native UI."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER], creator=item is not None, model=Issue)
    def probe(instance, req, **kwargs):
        return True

    return probe(None, request, slug=slug, project_id=project_id, pk=getattr(item, "pk", None)) is True


def readable_items(request, project):
    if not ProjectMember.objects.filter(project=project, member=request.user, is_active=True).exists():
        raise PermissionDenied("Project membership required")
    qs = Issue.issue_objects.filter(project=project)
    if (
        ProjectMember.objects.filter(project=project, member=request.user, role=5, is_active=True).exists()
        and not project.guest_view_all_features
    ):
        qs = qs.filter(created_by=request.user)
    return qs


def item_data(item):
    return {
        "id": str(item.pk),
        "title": item.name,
        "description_html": item.description_html,
        "updated_at": item.updated_at.isoformat(),
        "project_id": str(item.project_id),
        "work_item_identifier": f"{item.project.identifier}-{item.sequence_id}",
        "url": settings.WEB_URL.rstrip("/")
        + "/"
        + quote(item.project.workspace.slug, safe="")
        + "/browse/"
        + quote(f"{item.project.identifier}-{item.sequence_id}", safe="")
        + "/",
    }


ARCHIVE_FIELDS = {"title", "description_markdown", "expected_updated_at", "append", "work_item_type"}


def validate_archive_content(data):
    if not isinstance(data, dict) or set(data) - ARCHIVE_FIELDS:
        raise ValidationError("Invalid archive request")
    if "title" in data and (not isinstance(data["title"], str) or not 1 <= len(data["title"].strip()) <= 255):
        raise ValidationError("Title must be 1–255 characters")
    if "description_markdown" in data and (
        not isinstance(data["description_markdown"], str) or len(data["description_markdown"]) > 50000
    ):
        raise ValidationError("Description must be at most 50000 characters")
    if "append" in data and not isinstance(data["append"], bool):
        raise ValidationError("Append must be a boolean")
    for key in ("expected_updated_at", "work_item_type"):
        if key in data and (not isinstance(data[key], str) or len(data[key]) > 100):
            raise ValidationError("Invalid archive metadata")
    if not {"title", "description_markdown"} & set(data):
        raise ValidationError("No explicit content to save")


def prepare_archive(view, request, slug, project_id, pk=None):
    """Issue a server-owned decision bound to grant, project, target and payload hash."""
    view.require_scopes(request, "workitems:read", "workitems:write")
    project = project_for(request, slug, project_id)
    item = get_object_or_404(readable_items(request, project), pk=pk) if pk else None
    if not can_write(request, slug, project_id, item):
        raise PermissionDenied("Work item operation not allowed")
    validate_archive_content(request.data)
    if item and not request.data.get("expected_updated_at"):
        raise ValidationError("Updates require the previously read version")
    if not item and "title" not in request.data:
        raise ValidationError("Creation requires a title")
    decision_id = uuid.uuid4()
    payload = {**request.data, "decision_id": str(decision_id)}
    fingerprint = digest(json.dumps({"item": str(pk), "payload": payload}, sort_keys=True))
    DiscussionReceipt.objects.create(
        id=decision_id, grant=request.auth.grant, project=project, payload_digest=fingerprint
    )
    return Response(
        {
            "status": "prepared",
            "decision_id": str(decision_id),
            "project_id": str(project.pk),
            "content_digest": fingerprint,
        },
        status=202,
    )


class DiscussionPrepare(DelegatedAPI):
    def post(self, request, slug, project_id, pk=None):
        return prepare_archive(self, request, slug, project_id, pk)


class Me(DelegatedAPI):
    def get(self, request):
        return Response({"id": str(request.user.pk), "connection_id": str(request.auth.grant_id)})


class Projects(DelegatedAPI):
    def get(self, request):
        self.require_scopes(request, "projects:read")
        qs = visible_projects(request.user).select_related("workspace").order_by("id")
        if request.query_params.get("workspace"):
            qs = qs.filter(workspace__slug=request.query_params["workspace"])
        search = request.query_params.get("search", "")[:255]
        if search:
            qs = qs.filter(
                Q(name__icontains=search) | Q(identifier__iexact=search) | Q(id__in=[search] if _uuid(search) else [])
            )
        offset, limit = page(request)
        return Response(
            {
                "results": [
                    {"id": str(p.id), "name": p.name, "identifier": p.identifier, "workspace": p.workspace.slug}
                    for p in qs[offset : offset + limit]
                ],
                "next_offset": offset + limit if qs.count() > offset + limit else None,
            }
        )


def _uuid(value):
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError):
        return None


def page(request):
    try:
        offset, limit = int(request.query_params.get("offset", 0)), int(request.query_params.get("limit", 50))
    except ValueError:
        raise ValidationError("Invalid pagination")
    if offset < 0 or not 1 <= limit <= 100:
        raise ValidationError("Invalid pagination")
    return offset, limit


class Items(DelegatedAPI):
    def get(self, request, slug, project_id, pk=None):
        self.require_scopes(request, "workitems:read")
        project = project_for(request, slug, project_id)
        qs = readable_items(request, project).select_related("project")
        if pk:
            return Response(item_data(get_object_or_404(qs, pk=pk)))
        search = request.query_params.get("search", "")[:255]
        if search:
            qs = qs.filter(name__icontains=search)
        offset, limit = page(request)
        return Response(
            {
                "results": [item_data(item) for item in qs.order_by("id")[offset : offset + limit]],
                "next_offset": offset + limit if qs.count() > offset + limit else None,
            }
        )

    @transaction.atomic
    def post(self, request, slug, project_id, pk=None):
        self.require_scopes(request, "workitems:read", "workitems:write")
        project = project_for(request, slug, project_id)
        data = request.data
        if isinstance(data, dict) and "decision_id" not in data:
            return prepare_archive(self, request, slug, project_id, pk)
        allowed = ARCHIVE_FIELDS | {"decision_id"}
        if not isinstance(data, dict) or set(data) - allowed or not _uuid(data.get("decision_id")):
            raise ValidationError("Invalid archive request")
        item = (
            get_object_or_404(readable_items(request, project).select_for_update(of=("self",)), pk=pk) if pk else None
        )
        if not can_write(request, slug, project_id, item):
            raise PermissionDenied("Work item operation not allowed")
        payload_hash = digest(json.dumps({"item": str(pk), "payload": data}, sort_keys=True))
        receipt = DiscussionReceipt.objects.select_for_update().filter(pk=data["decision_id"]).first()
        if receipt is None:
            return Response({"error": "decision_not_prepared"}, status=409)
        if (
            receipt.grant_id != request.auth.grant_id
            or receipt.project_id != project.id
            or receipt.payload_digest != payload_hash
        ):
            return Response({"error": "decision_conflict"}, status=409)
        if receipt.issue_id:
            # A receipt must not reveal an item that became invisible after creation.
            get_object_or_404(readable_items(request, project), pk=receipt.issue_id)
            return Response({**receipt.result, "idempotent": True})
        if item and data.get("expected_updated_at") != item.updated_at.isoformat():
            return Response({"error": "version_conflict"}, status=409)
        fields = {}
        if "title" in data:
            if not isinstance(data["title"], str) or not 1 <= len(data["title"].strip()) <= 255:
                raise ValidationError("Title must be 1–255 characters")
            fields["name"] = data["title"].strip()
        if "description_markdown" in data:
            value = data["description_markdown"]
            if not isinstance(value, str) or len(value) > 50000:
                raise ValidationError("Description must be at most 50000 characters")
            rendered = nh3.clean(MarkdownIt("commonmark", {"html": False}).render(value))
            fields["description_html"] = (
                (item.description_html or "") + rendered if item and data.get("append", True) else rendered
            )
        if not fields or (not item and "name" not in fields):
            raise ValidationError("No explicit content to save")
        config = settings.SINGULARITY_PROJECT_CONFIG.get(str(project.pk), {})
        if not item:
            state = (
                State.objects.filter(project=project, pk=config["initial_state_id"]).first()
                if config.get("initial_state_id")
                else State.objects.filter(project=project, name="待整理").first()
            )
            if not state:
                return Response({"error": "initial_state_not_configured"}, status=409)
            fields["state"] = str(state.pk)
        if data.get("work_item_type"):
            if item:
                raise ValidationError("Type mapping is create-only")
            label_id = config.get("type_labels", {}).get(data["work_item_type"])
            if not label_id or not Label.objects.filter(pk=label_id, project=project).exists():
                raise ValidationError("Type label not configured")
            fields["labels"] = [label_id]
        before = json.dumps(IssueSerializer(item).data, cls=DjangoJSONEncoder) if item else None
        serializer = IssueSerializer(
            item,
            data=fields,
            partial=item is not None,
            context={
                "project_id": project.pk,
                "workspace_id": project.workspace_id,
                "default_assignee_id": None,
            },
        )
        serializer.is_valid(raise_exception=True)
        with impersonate(request.user):
            saved = serializer.save()
        created = item is None
        result = {"status": "created" if created else "updated", **item_data(saved)}
        # Match the native generateWorkItemLink browse route after persistence.
        receipt.issue, receipt.result = saved, result
        receipt.save(update_fields=["issue", "result"])
        transaction.on_commit(
            partial(
                issue_activity.delay,
                type="issue.activity.created" if created else "issue.activity.updated",
                requested_data=json.dumps(fields),
                actor_id=str(request.user.pk),
                issue_id=str(saved.pk),
                project_id=str(project.pk),
                current_instance=before,
                epoch=int(timezone.now().timestamp()),
                notification=True,
                origin=settings.SINGULARITY_ISSUER,
            )
        )
        transaction.on_commit(
            partial(
                model_activity.delay,
                model_name="issue",
                model_id=str(saved.pk),
                requested_data=fields,
                current_instance=before,
                actor_id=str(request.user.pk),
                slug=slug,
                origin=settings.SINGULARITY_ISSUER,
            )
        )
        return Response(result, status=201 if created else 200)


class Capabilities(DelegatedAPI):
    def get(self, request, slug, project_id, pk=None):
        self.require_scopes(request, "projects:read", "capabilities:read")
        if pk:
            self.require_scopes(request, "workitems:read")
        project = project_for(request, slug, project_id)
        item = get_object_or_404(readable_items(request, project), pk=pk) if pk else None
        scopes = set(request.auth.scopes.split())
        native_write = ProjectEntityPermission().has_permission(
            SimpleNamespace(user=request.user, method="POST"),
            SimpleNamespace(workspace_slug=slug, project_id=project_id),
        )
        write_scope = "workitems:write" in scopes
        return Response(
            {
                "can_create": write_scope and native_write,
                "can_update": write_scope and native_write if item else None,
                "can_delete": (
                    "workitems:delete" in scopes
                    and native_write
                    and (
                        item.created_by_id == request.user.pk
                        or ProjectMember.objects.filter(
                            project_id=project_id,
                            member=request.user,
                            role=20,
                            is_active=True,
                        ).exists()
                    )
                )
                if item
                else None,
                "authoritative": False,
            }
        )
