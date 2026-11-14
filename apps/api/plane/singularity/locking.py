# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from functools import wraps
from django.db import transaction
from django.utils.dateparse import parse_datetime
from rest_framework.response import Response
from plane.db.models import Issue


def lock_work_item(function):
    """Lock before reading, including native edits that can race delegated updates."""

    @wraps(function)
    def wrapped(self, request, *args, **kwargs):
        with transaction.atomic():
            issue = (
                Issue.objects.select_for_update(of=("self",))
                .filter(pk=kwargs.get("pk"), project_id=kwargs.get("project_id"), workspace__slug=kwargs.get("slug"))
                .first()
            )
            version = request.headers.get("If-Match")
            if version and issue:
                try:
                    expected = parse_datetime(version.strip('"'))
                except ValueError:
                    expected = None
                if expected is None:
                    return Response({"error": "If-Match must contain the read updated_at timestamp"}, status=400)
                if expected != issue.updated_at:
                    return Response(
                        {"error": "version_conflict", "updated_at": issue.updated_at.isoformat()}, status=409
                    )
            return function(self, request, *args, **kwargs)

    return wrapped
