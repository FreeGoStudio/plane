# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Route only Issue/State completion writes through the shared review validator."""

from django.db import models


class ReviewQuerySetMixin:
    def update(self, **kwargs):
        label = self.model._meta.label_lower
        guarded = (label == "db.issue" and ("state" in kwargs or "state_id" in kwargs)) or (
            label == "db.state" and "group" in kwargs
        )
        if guarded:
            from plane.singularity.code_review_gate import guarded_update

            return guarded_update(self, kwargs)
        return super().update(**kwargs)


class ReviewQuerySet(ReviewQuerySetMixin, models.QuerySet):
    pass


class ReviewAllManager(models.Manager.from_queryset(ReviewQuerySet)):
    pass
