# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from plane.db.models import ProjectRepository, RepositoryProvisioning, RepositoryMemberGrant, RepositoryRegistration
from .repository_api import RepositoryAPI, StrictSerializer, validated
from .repository_transport import RepositoryError
from .repository_management import (
    ROLE_ACCESS,
    active_members,
    external_user,
    event,
    management_instance,
    request_provisioning,
    serialized_project_operation,
)


class RepositoryManagement(RepositoryAPI):
    def get(self, request, slug, project_id):
        project = self.project(request, slug, project_id)
        row = RepositoryProvisioning.objects.filter(project=project).first()
        return Response(
            {
                "enabled": settings.SINGULARITY_REPOSITORY_PROVISIONING_ENABLED,
                "status": row.status if row else "not_started",
                "error_code": row.error_code if row else "",
                "operation_id": str(row.operation_id) if row else None,
                "attempts": row.attempts if row else 0,
                "updated_at": row.updated_at if row else None,
            }
        )

    @serialized_project_operation
    def post(self, request, slug, project_id):
        project = self.project(request, slug, project_id, admin=True)
        validated(StrictSerializer, request.data)
        row = request_provisioning(project, request.user)
        return Response({"status": row.status, "operation_id": str(row.operation_id)}, status=202)


class GrantInput(StrictSerializer):
    access_override = serializers.ChoiceField(choices=[0, 20, 30, 40], allow_null=True)
    expected_revision = serializers.IntegerField(min_value=0)
    adopt_existing = serializers.BooleanField(default=False)
    expected_direct_access = serializers.IntegerField(required=False)


class RepositoryMembers(RepositoryAPI):
    def get(self, request, slug, project_id, pk, user_id=None):
        project = self.project(request, slug, project_id, admin=True)
        repository = get_object_or_404(ProjectRepository, project=project, pk=pk)
        grants = {
            row.user_id: row
            for row in RepositoryMemberGrant.objects.filter(repository=repository).select_related("user")
        }
        members = {m.member_id: m for m in active_members(project)}
        results = []
        for user_id in set(members) | set(grants):
            member, grant = members.get(user_id), grants.get(user_id)
            user = member.member if member else grant.user
            results.append(
                {
                    "user_id": str(user_id),
                    "display_name": user.display_name or user.first_name or user.email,
                    "plane_role": member.role if member else None,
                    "external_user_id": grant.external_user_id if grant else external_user(user, repository.instance),
                    "access_override": grant.access_override if grant else None,
                    "default_access": ROLE_ACCESS.get(member.role, 0) if member else 0,
                    "applied_access": grant.applied_access if grant else None,
                    "effective_access": grant.effective_access if grant else None,
                    "direct_access": grant.direct_access if grant else None,
                    "managed": grant.managed if grant else False,
                    "status": grant.status if grant else "pending",
                    "error_code": grant.error_code if grant else "",
                    "revision": grant.revision if grant else 0,
                }
            )
        return Response({"results": sorted(results, key=lambda row: row["display_name"])})

    @serialized_project_operation
    @transaction.atomic
    def patch(self, request, slug, project_id, pk, user_id):
        project = self.project(request, slug, project_id, admin=True)
        repository = get_object_or_404(ProjectRepository, project=project, pk=pk, enabled=True)
        instance, _ = management_instance()
        if repository.instance_id != instance.pk or repository.purpose == "reference":
            raise RepositoryError("repository_outside_managed_instance", 409)
        data = validated(GrantInput, request.data)
        row = (
            RepositoryRegistration.objects.filter(repository=repository).first()
            or RepositoryProvisioning.objects.filter(project=project).first()
        )
        if row is None:
            raise RepositoryError("initialize_repositories_first", 409)
        member = active_members(project).filter(member_id=user_id).first()
        old = RepositoryMemberGrant.objects.filter(repository=repository, user_id=user_id).first()
        if not member and (not old or data["access_override"] != 0):
            raise RepositoryError("active_project_member_required", 400)
        grant, _ = RepositoryMemberGrant.objects.get_or_create(repository=repository, user_id=user_id)
        if grant.revision != data["expected_revision"]:
            raise RepositoryError("repository_member_revision_conflict", 409)
        if data["adopt_existing"]:
            if grant.direct_access is None or data.get("expected_direct_access") != grant.direct_access:
                raise RepositoryError("repository_member_revision_conflict", 409)
            grant.adopt_requested = True
        grant.access_override = data["access_override"]
        grant.revision += 1
        grant.status, grant.error_code = "pending", ""
        grant.save()
        row.next_attempt_at = timezone.now()
        row.save(update_fields=["next_attempt_at"])
        event(
            project,
            "repository_member_access_requested",
            {
                "repository_id": str(repository.pk),
                "user_id": str(user_id),
                "access_override": grant.access_override,
                "revision": grant.revision,
                "adopt_existing": data["adopt_existing"],
            },
            request.user,
        )
        return Response({"status": "pending", "revision": grant.revision}, status=202)
