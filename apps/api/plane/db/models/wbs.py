# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Plane owns immutable WBS inputs, review decisions and child mappings."""

import uuid
from django.conf import settings
from django.db import models


class WbsRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="wbs_requests")
    request_key = models.CharField(max_length=128)
    input_digest = models.CharField(max_length=64)
    snapshot = models.JSONField()
    status = models.CharField(max_length=24, default="queued")
    hatchet_run_id = models.CharField(max_length=64, blank=True)
    dispatch_at = models.DateTimeField(null=True)
    lease_until = models.DateTimeField(null=True)
    execution_token = models.UUIDField(null=True)
    attempts = models.PositiveIntegerField(default=0)
    result = models.JSONField(default=dict)
    result_digest = models.CharField(max_length=64, blank=True)
    error = models.CharField(max_length=500, blank=True)
    decision = models.CharField(max_length=16, blank=True)
    decision_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="wbs_reviews"
    )
    reviewed_at = models.DateTimeField(null=True)
    children = models.JSONField(default=dict)
    execution = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["issue", "requested_by", "request_key"], name="wbs_request_once")
        ]
        indexes = [models.Index(fields=["status", "dispatch_at"], name="wbs_dispatch_idx")]
