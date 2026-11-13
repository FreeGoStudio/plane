# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Session-authorized repository configuration and reads, never shared credentials."""

from collections.abc import Mapping
from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied, MethodNotAllowed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from plane.db.models import (
    RepositoryInstance,
    ProjectRepository,
    RepositoryCredential,
    RepositorySelection,
    RepositoryAccessAudit,
    ProjectMember,
)
from plane.license.models import InstanceAdmin
from .api import visible_projects, PersonalThrottle, WriteThrottle
from .repository_provider import RepositoryProvider
from .repository_transport import RepositoryError, validate_instance
from .vault import VaultError, seal, unseal, require_owner, selected_credential


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, Mapping) or set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["Unknown fields"]})
        return super().to_internal_value(data)


class InstanceInput(StrictSerializer):
    name = serializers.CharField(max_length=160)
    provider = serializers.ChoiceField(choices=["gitlab", "github"])
    api_url = serializers.URLField()
    web_url = serializers.URLField()
    allowed_networks = serializers.ListField(child=serializers.CharField(), default=list)
    allow_http = serializers.BooleanField(default=False)
    company_primary = serializers.BooleanField(default=False)


class CredentialInput(StrictSerializer):
    instance_id = serializers.UUIDField(required=False)
    label = serializers.CharField(max_length=160)
    token = serializers.CharField(max_length=8192, trim_whitespace=False, write_only=True)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)


class AccessInput(StrictSerializer):
    credential_id = serializers.UUIDField(required=False, allow_null=True)
    anonymous = serializers.BooleanField(default=False)

    def validate(self, data):
        if data["anonymous"] == bool(data.get("credential_id")):
            raise serializers.ValidationError("Choose your credential or explicit anonymous access")
        return data


class RepositoryInput(AccessInput):
    instance_id = serializers.UUIDField()
    path = serializers.CharField(max_length=512)
    purpose = serializers.ChoiceField(choices=["development", "reference", "documentation"])
    default_branch = serializers.CharField(max_length=255, required=False, allow_blank=True)


class RepositoryUpdate(StrictSerializer):
    purpose = serializers.ChoiceField(choices=["development", "reference", "documentation"], required=False)
    default_branch = serializers.CharField(max_length=255, required=False, allow_blank=True)
    enabled = serializers.BooleanField(required=False)


def validated(serializer, data):
    instance = serializer(data=data)
    instance.is_valid(raise_exception=True)
    return instance.validated_data


def credential_data(row):
    return {
        "id": str(row.pk),
        "instance_id": str(row.instance_id),
        "label": row.label,
        "expires_at": row.expires_at,
        "revoked_at": row.revoked_at,
        "validation_status": row.validation_status,
        "validated_at": row.validated_at,
        "external_actor_id": row.external_actor_id,
        "external_actor_label": row.external_actor_label,
    }


def chosen(user, instance, data):
    if data["anonymous"]:
        return None, None
    credential = get_object_or_404(
        RepositoryCredential.objects.select_related("instance"),
        pk=data.get("credential_id"),
        owner=user,
        instance=instance,
    )
    require_owner(credential, user)
    return credential, unseal(credential)


class RepositoryAPI(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [PersonalThrottle, WriteThrottle]
    repository = None
    credential = None

    def initial(self, request, *args, **kwargs):
        if not settings.SINGULARITY_REPOSITORIES_ENABLED:
            raise Http404
        super().initial(request, *args, **kwargs)
        if not request.user.is_active or request.user.is_bot:
            raise PermissionDenied("Active human account required")

    def handle_exception(self, error):
        if isinstance(error, RepositoryError):
            return Response({"error": error.code}, status=error.status)
        if isinstance(error, VaultError):
            return Response({"error": str(error)}, status=403)
        if isinstance(error, IntegrityError):
            return Response({"error": "configuration_conflict"}, status=409)
        return super().handle_exception(error)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        actor = request.user if getattr(request.user, "is_authenticated", False) else None
        audit = RepositoryAccessAudit.objects.create(
            owner=actor,
            repository=self.repository,
            credential=self.credential,
            external_actor_id=self.credential.external_actor_id if self.credential else "",
            operation=f"{request.method}:{self.__class__.__name__}",
            result=str(response.status_code),
        )
        response["X-Trace-ID"] = str(audit.trace_id)
        response["Cache-Control"] = "no-store"
        return response

    def project(self, request, slug, project_id, admin=False):
        project = get_object_or_404(visible_projects(request.user), pk=project_id, workspace__slug=slug)
        if (
            admin
            and not ProjectMember.objects.filter(project=project, member=request.user, role=20, is_active=True).exists()
        ):
            raise PermissionDenied("Project administrator required")
        return project


class RepositoryInstances(RepositoryAPI):
    def get(self, request):
        return Response(
            list(
                RepositoryInstance.objects.filter(enabled=True).values(
                    "id", "name", "provider", "web_url", "company_primary"
                )
            )
        )

    def post(self, request):
        if not InstanceAdmin.objects.filter(user=request.user, role__gte=15).exists():
            raise PermissionDenied("Platform administrator required")
        data = validated(InstanceInput, request.data)
        data["api_url"] = data["api_url"].rstrip("/")
        data["web_url"] = data["web_url"].rstrip("/")
        instance = RepositoryInstance(**data)
        validate_instance(instance)
        instance.save()
        return Response({"id": str(instance.pk)}, status=201)


class RepositoryCredentials(RepositoryAPI):
    def get(self, request, pk=None):
        rows = RepositoryCredential.objects.filter(owner=request.user).order_by("-created_at")
        return Response(
            credential_data(get_object_or_404(rows, pk=pk)) if pk else [credential_data(row) for row in rows]
        )

    @transaction.atomic
    def post(self, request, pk=None):
        data = validated(CredentialInput, request.data)
        if pk:
            row = get_object_or_404(RepositoryCredential.objects.select_for_update(), pk=pk, owner=request.user)
            if row.revoked_at or (data.get("instance_id") and data["instance_id"] != row.instance_id):
                raise serializers.ValidationError("Revoked credentials and credential instances cannot be changed")
        else:
            instance = get_object_or_404(RepositoryInstance, pk=data.get("instance_id"), enabled=True)
            row = RepositoryCredential(owner=request.user, instance=instance)
        row.label, row.expires_at = data["label"], data.get("expires_at")
        if row.expires_at and row.expires_at <= timezone.now():
            raise serializers.ValidationError("Expiry must be in the future")
        seal(row, data["token"])
        # /user only proves actor identity; repository permissions are checked per read.
        row.external_actor_id, row.external_actor_label = RepositoryProvider(row.instance, data["token"]).actor()
        row.validated_at, row.validation_status = timezone.now(), "identity_verified"
        row.save()
        self.credential = row
        return Response(credential_data(row), status=200 if pk else 201)

    def delete(self, request, pk=None):
        if pk is None:
            raise MethodNotAllowed("DELETE")
        row = get_object_or_404(RepositoryCredential, owner=request.user, pk=pk)
        row.revoked_at, row.encrypted_material, row.validation_status = timezone.now(), "", "revoked"
        row.save(update_fields=["revoked_at", "encrypted_material", "validation_status", "updated_at"])
        self.credential = row
        return Response(status=204)


class ProjectRepositories(RepositoryAPI):
    def get(self, request, slug, project_id, pk=None):
        project = self.project(request, slug, project_id)
        rows = ProjectRepository.objects.filter(project=project).select_related("instance")
        selections = {
            row.repository_id: row
            for row in RepositorySelection.objects.filter(owner=request.user, repository__project=project)
        }
        result = []
        for row in rows:
            selection = selections.get(row.pk)
            result.append(
                {
                    "id": str(row.pk),
                    "instance_id": str(row.instance_id),
                    "instance_name": row.instance.name,
                    "path": row.path,
                    "external_id": row.external_id,
                    "purpose": row.purpose,
                    "default_branch": row.default_branch,
                    "enabled": row.enabled,
                    "credential_id": str(selection.credential_id) if selection and selection.credential_id else None,
                    "anonymous": bool(selection and selection.anonymous),
                }
            )
        return Response(result)

    @transaction.atomic
    def post(self, request, slug, project_id, pk=None):
        if pk is not None:
            raise MethodNotAllowed("POST")
        project = self.project(request, slug, project_id, admin=True)
        data = validated(RepositoryInput, request.data)
        instance = get_object_or_404(RepositoryInstance, pk=data["instance_id"], enabled=True)
        self.credential, token = chosen(request.user, instance, data)
        metadata = RepositoryProvider(instance, token).metadata(data["path"], by_id=False)
        row = ProjectRepository.objects.create(project=project, instance=instance, **metadata, purpose=data["purpose"])
        if "default_branch" in data:
            row.default_branch = data["default_branch"]
            row.save(update_fields=["default_branch"])
        RepositorySelection.objects.create(
            owner=request.user, repository=row, credential=self.credential, anonymous=data["anonymous"]
        )
        self.repository = row
        return Response({"id": str(row.pk), **metadata}, status=201)

    def patch(self, request, slug, project_id, pk=None):
        if pk is None:
            raise MethodNotAllowed("PATCH")
        project = self.project(request, slug, project_id, admin=True)
        row = get_object_or_404(ProjectRepository, project=project, pk=pk)
        data = validated(RepositoryUpdate, request.data)
        for field, value in data.items():
            setattr(row, field, value)
        row.save()
        self.repository = row
        return Response({"id": str(row.pk), "enabled": row.enabled})


class RepositoryAccess(RepositoryAPI):
    def row(self, request, slug, project_id, pk):
        project = self.project(request, slug, project_id)
        self.repository = get_object_or_404(
            ProjectRepository.objects.select_related("instance"), project=project, pk=pk, enabled=True
        )
        return self.repository

    def post(self, request, slug, project_id, pk, operation=None):
        if operation is not None:
            raise MethodNotAllowed("POST")
        row = self.row(request, slug, project_id, pk)
        data = validated(AccessInput, request.data)
        self.credential, _ = chosen(request.user, row.instance, data)
        RepositorySelection.objects.update_or_create(
            owner=request.user, repository=row, defaults={"credential": self.credential, "anonymous": data["anonymous"]}
        )
        return Response({"configured": True})

    def get(self, request, slug, project_id, pk, operation=None):
        if operation not in ("tree", "file"):
            raise MethodNotAllowed("GET")
        row = self.row(request, slug, project_id, pk)
        self.credential, token = selected_credential(request.user, row)
        provider = RepositoryProvider(row.instance, token)
        ref, path = request.query_params.get("ref", ""), request.query_params.get("path", "")
        if operation == "tree":
            try:
                page = int(request.query_params.get("page", "1"))
            except ValueError:
                raise serializers.ValidationError("Invalid page") from None
            result = provider.directory(row, ref, path, page)
        else:
            result = provider.file(row, ref, path)
        return Response(result)
