# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Personal grants, hashed OAuth credentials and atomic discussion receipts."""

import uuid
from django.conf import settings
from django.db import models


class Delegation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    client_id = models.CharField(max_length=200)
    scopes = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True)


class DelegationCode(models.Model):
    digest = models.CharField(max_length=64, primary_key=True)
    grant = models.ForeignKey(Delegation, on_delete=models.CASCADE)
    redirect_uri = models.TextField()
    challenge = models.CharField(max_length=128)
    expires_at = models.DateTimeField()


class DelegationToken(models.Model):
    digest = models.CharField(max_length=64, primary_key=True)
    refresh_digest = models.CharField(max_length=64, unique=True)
    grant = models.ForeignKey(Delegation, on_delete=models.CASCADE)
    audience = models.CharField(max_length=20)
    scopes = models.TextField()
    expires_at = models.DateTimeField()
    refresh_expires_at = models.DateTimeField()
    revoked = models.BooleanField(default=False)


class DiscussionReceipt(models.Model):
    id = models.UUIDField(primary_key=True)
    grant = models.ForeignKey(Delegation, on_delete=models.CASCADE)
    project = models.ForeignKey("db.Project", on_delete=models.CASCADE)
    payload_digest = models.CharField(max_length=64)
    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, null=True)
    result = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class DelegationAudit(models.Model):
    trace_id = models.UUIDField(default=uuid.uuid4)
    grant = models.ForeignKey(Delegation, null=True, on_delete=models.SET_NULL)
    operation = models.CharField(max_length=100)
    resource = models.CharField(max_length=100, blank=True)
    status = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
