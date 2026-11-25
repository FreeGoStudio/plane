# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Durable document review inputs and explicit adoption decisions."""

import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class DocumentRepositoryExecutor(models.Model):
    """Platform-owned project credential; never a user's selected reader credential."""

    repository = models.OneToOneField("db.ProjectRepository", primary_key=True, on_delete=models.CASCADE)
    status = models.CharField(max_length=24, default="pending")
    error_code = models.CharField(max_length=100, blank=True)
    token_id = models.PositiveBigIntegerField(null=True)
    actor_id = models.CharField(max_length=64, blank=True)
    expires_at = models.DateField(null=True)
    key_version = models.CharField(max_length=32, blank=True)
    encrypted_material = models.TextField(blank=True)
    issuance_name = models.CharField(max_length=100, blank=True)
    retired_tokens = models.JSONField(default=list)
    next_check_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)


class RequirementReviewConfig(models.Model):
    issue = models.OneToOneField("db.Issue", primary_key=True, on_delete=models.CASCADE)
    repository = models.ForeignKey("db.ProjectRepository", on_delete=models.PROTECT)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    binding_revision = models.PositiveIntegerField()
    draft_branch = models.CharField(max_length=255)
    adopted_branch = models.CharField(max_length=255)
    paths = models.JSONField()
    revision = models.PositiveIntegerField(default=1)
    enabled = models.BooleanField(default=True)
    latest_sha = models.CharField(max_length=64, blank=True)
    adopted_sha = models.CharField(max_length=64, blank=True)
    error = models.CharField(max_length=100, blank=True)
    poll_after = models.DateTimeField(null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["repository", "adopted_branch"], name="review_target_once")]


class RequirementReviewRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    config = models.ForeignKey(RequirementReviewConfig, on_delete=models.CASCADE)
    source_sha = models.CharField(max_length=64)
    input_digest = models.CharField(max_length=64)
    snapshot = models.JSONField()
    merge_request = models.JSONField(default=dict)
    status = models.CharField(max_length=24, default="queued")
    result = models.JSONField(default=dict)
    result_digest = models.CharField(max_length=64, blank=True)
    error = models.CharField(max_length=100, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    preparation_attempts = models.PositiveIntegerField(default=0)
    dispatch_at = models.DateTimeField(null=True)
    lease_until = models.DateTimeField(null=True)
    execution_token = models.UUIDField(null=True)
    hatchet_run_id = models.CharField(max_length=64, blank=True)
    retry_of = models.ForeignKey("self", null=True, on_delete=models.PROTECT)
    request_key = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["config", "request_key"], name="review_request_once")]
        indexes = [models.Index(fields=["status", "dispatch_at"], name="review_dispatch_idx")]


class RequirementAdoption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    config = models.ForeignKey(RequirementReviewConfig, on_delete=models.PROTECT)
    run = models.ForeignKey(RequirementReviewRun, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    source_sha = models.CharField(max_length=64)
    target_sha = models.CharField(max_length=64)
    merged_sha = models.CharField(max_length=64, blank=True)
    config_revision = models.PositiveIntegerField()
    kind = models.CharField(max_length=20)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=24, default="pending")
    error = models.CharField(max_length=100, blank=True)
    request_key = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["config", "request_key"], name="adoption_request_once")]


class RequirementReviewEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    repository = models.ForeignKey("db.ProjectRepository", on_delete=models.CASCADE)
    event_key = models.CharField(max_length=128)
    branch = models.CharField(max_length=255)
    source_sha = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["repository", "event_key"], name="review_event_once")]
