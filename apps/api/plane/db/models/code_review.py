# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Immutable review evidence and task-scoped MR associations."""

import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q


class CodeReviewLink(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    issue = models.ForeignKey("db.Issue", on_delete=models.PROTECT)
    repository = models.ForeignKey("db.ProjectRepository", on_delete=models.PROTECT)
    mr_iid = models.PositiveIntegerField()
    active = models.BooleanField(default=True)
    generation = models.PositiveIntegerField(default=0)
    version = models.JSONField(default=dict)
    current_run = models.ForeignKey("db.CodeReviewRun", null=True, on_delete=models.PROTECT, related_name="+")
    poll_after = models.DateTimeField(null=True)
    error = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "repository", "mr_iid"], condition=Q(active=True), name="code_review_active_link_once"
            )
        ]
        indexes = [models.Index(fields=["active", "poll_after"], name="code_review_poll_idx")]


class CodeReviewRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    link = models.ForeignKey(CodeReviewLink, on_delete=models.PROTECT)
    generation = models.PositiveIntegerField()
    request_key = models.CharField(max_length=128)
    snapshot = models.JSONField()
    input_digest = models.CharField(max_length=64)
    source_sha = models.CharField(max_length=64)
    target_sha = models.CharField(max_length=64)
    merge_base = models.CharField(max_length=64)
    status = models.CharField(max_length=24, default="queued")
    raw_report = models.JSONField(default=dict)
    report = models.JSONField(default=dict)
    report_digest = models.CharField(max_length=64, blank=True)
    error = models.CharField(max_length=100, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    dispatch_at = models.DateTimeField(null=True)
    lease_until = models.DateTimeField(null=True)
    execution_token = models.UUIDField(null=True)
    hatchet_run_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["link", "request_key"], name="code_review_request_once")]
        indexes = [models.Index(fields=["status", "dispatch_at"], name="code_review_dispatch_idx")]


class CodeReviewEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    issue = models.ForeignKey("db.Issue", null=True, on_delete=models.PROTECT)
    repository = models.ForeignKey("db.ProjectRepository", on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    event_key = models.CharField(max_length=128)
    kind = models.CharField(max_length=32)
    payload = models.JSONField(default=dict)
    processed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["repository", "event_key"], name="code_review_event_once")]


class CodeReviewDecision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(CodeReviewRun, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(max_length=16)
    reason = models.TextField(blank=True)
    report_digest = models.CharField(max_length=64)
    input_digest = models.CharField(max_length=64)
    revision = models.PositiveIntegerField()
    request_key = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "revision"], name="code_review_decision_revision"),
            models.UniqueConstraint(fields=["run", "request_key"], name="code_review_decision_once"),
        ]
