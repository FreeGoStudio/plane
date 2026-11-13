# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from functools import wraps
from django.db import transaction
from plane.db.models import Issue


def lock_work_item(function):
    """Lock before reading, including native edits that can race delegated updates."""

    @wraps(function)
    def wrapped(self, request, *args, **kwargs):
        with transaction.atomic():
            Issue.objects.select_for_update(of=("self",)).filter(
                pk=kwargs.get("pk"), project_id=kwargs.get("project_id"), workspace__slug=kwargs.get("slug")
            ).first()
            return function(self, request, *args, **kwargs)

    return wrapped
