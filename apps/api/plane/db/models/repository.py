# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Repository configuration and owner-scoped secrets, separate from login accounts."""

import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q


class RepositoryInstance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    provider = models.CharField(max_length=10, choices=[("gitlab", "GitLab"), ("github", "GitHub")])
    api_url = models.URLField(unique=True)
    web_url = models.URLField()
    allowed_networks = models.JSONField(default=list)
    ca_file = models.TextField(blank=True)
    allow_http = models.BooleanField(default=False)
    company_primary = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company_primary"], condition=Q(company_primary=True), name="one_primary_repository_instance"
            )
        ]


class ProjectRepository(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE)
    instance = models.ForeignKey(RepositoryInstance, on_delete=models.PROTECT)
    external_id = models.CharField(max_length=255)
    path = models.CharField(max_length=512)
    purpose = models.CharField(
        max_length=16,
        choices=[("development", "Development"), ("reference", "Reference"), ("documentation", "Documentation")],
    )
    default_branch = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["project", "instance", "external_id"], name="unique_project_repository")
        ]


class RepositoryIdentity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    instance = models.ForeignKey(RepositoryInstance, on_delete=models.PROTECT)
    external_id = models.CharField(max_length=255)
    method = models.CharField(max_length=32)
    platform_managed = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "instance"], name="unique_repository_identity"),
            models.UniqueConstraint(fields=["instance", "external_id"], name="unique_instance_identity"),
        ]


class RepositoryCredential(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    instance = models.ForeignKey(RepositoryInstance, on_delete=models.PROTECT)
    label = models.CharField(max_length=160)
    kind = models.CharField(max_length=16, default="https_token")
    key_version = models.CharField(max_length=32)
    encrypted_material = models.TextField()
    expires_at = models.DateTimeField(null=True)
    revoked_at = models.DateTimeField(null=True)
    validated_at = models.DateTimeField(null=True)
    validation_status = models.CharField(max_length=32, default="unverified")
    external_actor_id = models.CharField(max_length=255, blank=True)
    external_actor_label = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class RepositorySelection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    repository = models.ForeignKey(ProjectRepository, on_delete=models.CASCADE)
    credential = models.ForeignKey(RepositoryCredential, null=True, on_delete=models.CASCADE)
    anonymous = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["owner", "repository"], name="unique_repository_selection"),
            models.CheckConstraint(
                condition=Q(anonymous=True, credential__isnull=True) | Q(anonymous=False, credential__isnull=False),
                name="explicit_repository_authentication",
            ),
        ]


class RepositoryAccessAudit(models.Model):
    trace_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    repository = models.ForeignKey(ProjectRepository, null=True, on_delete=models.SET_NULL)
    credential = models.ForeignKey(RepositoryCredential, null=True, on_delete=models.SET_NULL)
    external_actor_id = models.CharField(max_length=255, blank=True)
    operation = models.CharField(max_length=40)
    result = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)
