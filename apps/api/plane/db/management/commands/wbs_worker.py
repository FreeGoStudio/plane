# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Run the Hatchet WBS worker and recover persisted Plane dispatch intents."""

import logging
import threading
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import close_old_connections, transaction
from django.db.models import Q
from django.utils import timezone
from hatchet_sdk import Hatchet
from pydantic import BaseModel
from plane.db.models import WbsRun
from plane.singularity.wbs_generation import execute

logger = logging.getLogger(__name__)


class RunInput(BaseModel):
    run_id: str


def dispatch_pending(task):
    """Lease an outbox intent before sending; response loss permits safe replay."""
    cutoff = timezone.now() - timedelta(minutes=6)
    with transaction.atomic():
        row = (
            WbsRun.objects.select_for_update(skip_locked=True)
            .filter(status__in=["queued", "running", "failed"], attempts__lt=3)
            .filter(Q(dispatch_at__isnull=True) | Q(dispatch_at__lt=cutoff))
            .filter(Q(lease_until__isnull=True) | Q(lease_until__lt=timezone.now()))
            .order_by("created_at")
            .first()
        )
        if not row:
            return
        row.dispatch_at = timezone.now()
        row.save(update_fields=["dispatch_at", "updated_at"])
    try:
        ref = task.run(RunInput(run_id=str(row.id)), wait_for_result=False)
        WbsRun.objects.filter(pk=row.id, status="queued").update(hatchet_run_id=str(ref.workflow_run_id), error="")
    except Exception:
        WbsRun.objects.filter(pk=row.id, status="queued").update(error="Dispatch unavailable; automatic retry pending")
        logger.warning("WBS dispatch unavailable for %s", row.id)


class Command(BaseCommand):
    help = "Execute Plane WBS requests through the private Hatchet control plane"

    def handle(self, *args, **options):
        hatchet = Hatchet()

        @hatchet.task(
            name="plane-wbs-generate",
            input_validator=RunInput,
            execution_timeout=timedelta(minutes=3),
            schedule_timeout=timedelta(minutes=5),
            retries=2,
            backoff_factor=2,
            backoff_max_seconds=30,
        )
        def generate(input, ctx):
            close_old_connections()
            try:
                return execute(input.run_id, ctx.workflow_run_id)
            finally:
                close_old_connections()

        stop = threading.Event()

        def dispatch():
            while not stop.wait(5):
                try:
                    close_old_connections()
                    dispatch_pending(generate)
                except Exception:
                    logger.warning("WBS dispatch check failed; retrying")
                finally:
                    close_old_connections()

        thread = threading.Thread(target=dispatch, daemon=True)
        thread.start()
        try:
            hatchet.worker("plane-wbs-worker", slots=2, workflows=[generate]).start()
        finally:
            stop.set()
