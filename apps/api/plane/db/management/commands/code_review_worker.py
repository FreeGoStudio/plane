# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Independent Native OCR worker using the existing Hatchet control plane."""

import logging
import threading
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import close_old_connections, transaction
from django.db.models import Q
from django.utils import timezone
from hatchet_sdk import Hatchet
from pydantic import BaseModel
from plane.db.models import CodeReviewRun, CodeReviewLink, CodeReviewEvent
from plane.singularity.code_review import capture, lock_issue, remote_version
from plane.singularity.code_review_execution import execute

logger = logging.getLogger(__name__)


class RunInput(BaseModel):
    run_id: str


def reconcile():
    # Events are wakeups; GitLab's current state, never the event body, is authoritative.
    for event in CodeReviewEvent.objects.filter(issue__isnull=True, processed_at__isnull=True)[:100]:
        CodeReviewLink.objects.filter(repository=event.repository, active=True).update(poll_after=None)
        event.processed_at = timezone.now()
        event.save(update_fields=["processed_at"])
    ids = list(
        CodeReviewLink.objects.filter(active=True)
        .filter(Q(poll_after__isnull=True) | Q(poll_after__lte=timezone.now()))
        .values_list("pk", flat=True)
    )
    for pk in ids:
        try:
            with transaction.atomic():
                link = CodeReviewLink.objects.select_related("repository__instance", "issue").get(pk=pk)
                lock_issue(link.issue_id)
                link.refresh_from_db()
                if link.active:
                    capture(link, remote_version(link))
        except Exception as exc:
            CodeReviewLink.objects.filter(pk=pk).update(
                error=getattr(exc, "code", "remote_verification_failed"),
                poll_after=timezone.now() + timedelta(minutes=1),
            )


def dispatch_pending(task):
    CodeReviewRun.objects.filter(status="running", attempts__gte=3, lease_until__lt=timezone.now()).update(
        status="failed", error="execution_lease_expired", lease_until=None, finished_at=timezone.now()
    )
    with transaction.atomic():
        row = (
            CodeReviewRun.objects.select_for_update(skip_locked=True)
            .filter(status__in=["queued", "running"], attempts__lt=3)
            .filter(Q(lease_until__isnull=True) | Q(lease_until__lt=timezone.now()))
            .filter(Q(dispatch_at__isnull=True) | Q(dispatch_at__lt=timezone.now() - timedelta(minutes=2)))
            .order_by("created_at")
            .first()
        )
        if not row:
            return
        row.dispatch_at = timezone.now()
        row.save(update_fields=["dispatch_at"])
    try:
        ref = task.run(RunInput(run_id=str(row.pk)), wait_for_result=False)
        CodeReviewRun.objects.filter(pk=row.pk, status="queued").update(hatchet_run_id=str(ref.workflow_run_id))
    except Exception:
        CodeReviewRun.objects.filter(pk=row.pk, status="queued").update(error="dispatch_unavailable")


class Command(BaseCommand):
    help = "Run Native OCR reviews through Hatchet"

    def handle(self, *args, **options):
        hatchet = Hatchet()

        @hatchet.task(
            name="plane-code-review",
            input_validator=RunInput,
            execution_timeout=timedelta(minutes=31),
            schedule_timeout=timedelta(minutes=5),
            retries=0,
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
                    reconcile()
                    dispatch_pending(review)
                except Exception:
                    logger.warning("Code review reconciliation unavailable; retrying")
                finally:
                    close_old_connections()

        threading.Thread(target=loop, daemon=True).start()
        try:
            hatchet.worker("plane-code-review-worker", slots=2, workflows=[review]).start()
        finally:
            stop.set()
