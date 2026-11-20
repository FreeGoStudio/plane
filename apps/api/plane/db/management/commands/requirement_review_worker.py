# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Run durable document reviews on Hatchet with periodic push reconciliation."""

import logging
import threading
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import close_old_connections, transaction
from django.db.models import Q
from django.utils import timezone
from hatchet_sdk import Hatchet
from pydantic import BaseModel
from plane.db.models import RequirementReviewRun
from plane.singularity.requirement_review import poll_one
from plane.singularity.requirement_review_generation import execute

logger = logging.getLogger(__name__)


class RunInput(BaseModel):
    run_id: str


def dispatch_pending(task):
    """Persist dispatch intent before calling Hatchet, recovering uncertain acknowledgements."""
    RequirementReviewRun.objects.filter(status="running", attempts__gte=3, lease_until__lt=timezone.now()).update(
        status="failed", error="execution_lease_expired", lease_until=None
    )
    with transaction.atomic():
        row = (
            RequirementReviewRun.objects.select_for_update(skip_locked=True)
            .filter(status__in=["queued", "running"], attempts__lt=3)
            .exclude(merge_request={})
            .filter(Q(dispatch_at__isnull=True) | Q(dispatch_at__lt=timezone.now() - timedelta(minutes=6)))
            .filter(Q(lease_until__isnull=True) | Q(lease_until__lt=timezone.now()))
            .order_by("created_at")
            .first()
        )
        if not row:
            return
        row.dispatch_at = timezone.now()
        row.save(update_fields=["dispatch_at"])
    try:
        ref = task.run(RunInput(run_id=str(row.id)), wait_for_result=False)
        RequirementReviewRun.objects.filter(pk=row.pk, status="queued").update(hatchet_run_id=str(ref.workflow_run_id))
    except Exception:
        RequirementReviewRun.objects.filter(pk=row.pk, status="queued").update(error="dispatch_unavailable")


class Command(BaseCommand):
    help = "Execute requirement document reviews through Hatchet"

    def handle(self, *args, **options):
        hatchet = Hatchet()

        @hatchet.task(
            name="plane-requirement-document-review",
            input_validator=RunInput,
            execution_timeout=timedelta(minutes=3),
            schedule_timeout=timedelta(minutes=5),
            retries=2,
            backoff_factor=2,
            backoff_max_seconds=30,
        )
        def review(input, ctx):
            close_old_connections()
            try:
                return execute(input.run_id, ctx.workflow_run_id)
            finally:
                close_old_connections()

        stop = threading.Event()

        def loop():
            while not stop.wait(5):
                try:
                    close_old_connections()
                    poll_one()
                    dispatch_pending(review)
                except Exception:
                    logger.warning("Document review reconciliation failed; retrying")
                finally:
                    close_old_connections()

        threading.Thread(target=loop, daemon=True).start()
        try:
            hatchet.worker("plane-requirement-review-worker", slots=2, workflows=[review]).start()
        finally:
            stop.set()
