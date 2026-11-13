# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Durable company provisioning intent, isolated from repository permissions."""

from django.conf import settings
from django.db import models
from django.utils import timezone


class CompanyAccount(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, primary_key=True, on_delete=models.CASCADE)
    instance_url = models.URLField()
    external_id = models.PositiveBigIntegerField(null=True, unique=True)
    proposed_external_id = models.PositiveBigIntegerField(null=True, unique=True)
    managed = models.BooleanField(default=False)
    create_requested = models.BooleanField(default=False)
    status = models.CharField(max_length=24, default="pending")
    error_code = models.CharField(max_length=80, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
