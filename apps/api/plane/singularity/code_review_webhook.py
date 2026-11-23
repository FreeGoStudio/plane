# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Authenticated durable MR/push wakeups; no webhook body becomes review evidence."""

import re
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from plane.db.models import CodeReviewEvent, ProjectRepository
from .requirement_review_api import internal_secret
from .wbs import digest


class CodeReviewWebhook(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, repository_id):
        internal_secret(request, "CODE_REVIEW_WEBHOOK_SECRET", "X-Gitlab-Token")
        repository = get_object_or_404(
            ProjectRepository, pk=repository_id, enabled=True, purpose="development", instance__provider="gitlab"
        )
        data = request.data
        kind = data.get("object_kind")
        expected_header = {"merge_request": "Merge Request Hook", "push": "Push Hook"}.get(kind)
        project = data.get("project") or {}
        project_id = data.get("project_id") if kind == "push" else project.get("id")
        key = request.headers.get("X-Gitlab-Event-UUID", "")
        if (
            not expected_header
            or request.headers.get("X-Gitlab-Event") != expected_header
            or str(project_id) != repository.external_id
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", key)
        ):
            raise ValidationError("Unexpected GitLab event")
        # Store only the digest and routing data, never arbitrary event bodies.
        payload = {
            "digest": digest(data),
            "mr_iid": (data.get("object_attributes") or {}).get("iid"),
            "ref": str(data.get("ref", ""))[:512],
        }
        with transaction.atomic():
            row, created = CodeReviewEvent.objects.get_or_create(
                repository=repository, event_key=key, defaults={"kind": kind, "payload": payload}
            )
            if row.payload != payload:
                raise ValidationError("Conflicting event identifier")
        return Response({"recorded": True, "duplicate": not created}, status=202)
