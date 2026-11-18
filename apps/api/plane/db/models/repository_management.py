# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class RepositoryProvisioning(models.Model):
    project = models.OneToOneField("db.Project", primary_key=True, on_delete=models.CASCADE)
    operation_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    instance = models.ForeignKey("db.RepositoryInstance", null=True, on_delete=models.PROTECT)
    group_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=24, default="pending")
    slots = models.JSONField(default=dict)
    error_code = models.CharField(max_length=100, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)


class RepositoryMemberGrant(models.Model):
    repository = models.ForeignKey("db.ProjectRepository", on_delete=models.PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    external_user_id = models.CharField(max_length=255, blank=True)
    access_override = models.PositiveSmallIntegerField(null=True)
    desired_access = models.PositiveSmallIntegerField(default=0)
    applied_access = models.PositiveSmallIntegerField(null=True)
    effective_access = models.PositiveSmallIntegerField(default=0)
    direct_access = models.PositiveSmallIntegerField(null=True)
    adopt_requested = models.BooleanField(default=False)
    managed = models.BooleanField(default=False)
    create_requested = models.BooleanField(default=False)
    status = models.CharField(max_length=32, default="pending")
    error_code = models.CharField(max_length=100, blank=True)
    revision = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["repository", "user"], name="unique_repository_member_grant")]


class RepositoryManagementEvent(models.Model):
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    operation = models.CharField(max_length=64)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
