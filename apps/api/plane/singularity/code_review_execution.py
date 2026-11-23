# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Leased, fenced execution; the database owns the total attempt budget."""

import uuid
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from plane.db.models import CodeReviewRun
from .wbs import digest
from .code_review_runner import run_ocr, ExecutionFailure
from .repository_transport import RepositoryError


def execute(run_id, hatchet_run_id):
    with transaction.atomic():
        row = CodeReviewRun.objects.select_for_update().select_related("link__repository__instance").get(pk=run_id)
        if row.status not in ("queued", "running") or (row.lease_until and row.lease_until > timezone.now()):
            return {"run_id": str(row.pk), "status": row.status}
        if row.attempts >= 3:
            row.status, row.error = "failed", "attempts_exhausted"
            row.save(update_fields=["status", "error"])
            return {"run_id": str(row.pk), "status": row.status}
        row.attempts += 1
        row.status, row.execution_token = "running", uuid.uuid4()
        row.lease_until = timezone.now() + timedelta(minutes=31)
        row.hatchet_run_id = str(hatchet_run_id)
        row.save()
    status, raw, report, error = "failed", {}, {}, ""
    try:
        status, raw, report = run_ocr(row)
    except (ExecutionFailure, RepositoryError) as exc:
        transient = exc.transient if isinstance(exc, ExecutionFailure) else exc.status in (429, 502, 503, 504)
        status = "queued" if transient and row.attempts < 3 else "failed"
        error = exc.code
    except Exception:
        error = "review_execution_failed"
    CodeReviewRun.objects.filter(pk=row.pk, execution_token=row.execution_token, status="running").update(
        status=status,
        raw_report=raw,
        report=report,
        report_digest=digest(report) if report else "",
        error=error,
        lease_until=None,
        dispatch_at=None if status == "queued" else row.dispatch_at,
        finished_at=None if status == "queued" else timezone.now(),
    )
    return {"run_id": str(row.pk), "status": status}
