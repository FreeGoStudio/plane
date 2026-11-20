# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Isolated GitLab MR executor: exact source checks and recoverable remote merges."""

from django.db import transaction
from django.utils import timezone
from plane.db.models import RequirementAdoption, RequirementReviewConfig
from .requirement_review import current_input, provider_for, target_head
from .requirement_merge_request import ensure_merge_request, check_merge_request, prepare_one, report_one
from .wbs import require_member


def move_branch(row):
    """Merge the reviewed source on GitLab; the hook enforces the exact target and content."""
    config = current_input(row.run)
    require_member(row.actor, config.issue.project, True)
    if config.revision != row.config_revision:
        raise ValueError("configuration_changed")
    http, path = ensure_merge_request(row.run)
    mr = http.get(path)
    check_merge_request(config, mr, row.source_sha)
    provider = provider_for(config)
    head = target_head(config, provider)
    if mr["state"] == "merged":
        merged = mr.get("merge_commit_sha") or row.source_sha
        if head != merged:
            raise ValueError("target_changed")
        return merged  # Recover a lost merge response using actual MR evidence.
    if mr["state"] != "opened":
        raise ValueError("merge_request_closed")
    if head != row.target_sha:
        raise ValueError("target_changed")
    if provider.resolve(config.repository, config.draft_branch)[2] != row.source_sha:
        raise ValueError("source_changed")
    # The remote SHA precondition rejects a push arriving after the above read.
    # The server hook independently verifies target SHA and merged tree content.
    http.request(
        "PUT",
        path + "/merge",
        body={
            "sha": row.source_sha,
            "squash": "false",
            "should_remove_source_branch": "false",
        },
    )
    mr = http.get(path)
    check_merge_request(config, mr, row.source_sha)
    if mr["state"] != "merged":
        raise ValueError("merge_pending")
    merged = mr.get("merge_commit_sha") or row.source_sha
    if target_head(config, provider) != merged:
        raise ValueError("target_verification_failed")
    return merged


def process_one():
    """Hold a DB advisory lock per operation; recover running writes after process death."""
    from django.db import connection

    prepare_one()
    # Status publication must not prevent a previously authorized merge recovering.
    try:
        report_one()
    except Exception:
        pass  # Reconcile on the next loop; the exact grant remains the merge gate.
    row = RequirementAdoption.objects.filter(status__in=["pending", "running"]).order_by("created_at").first()
    if not row:
        return
    key = int.from_bytes(row.pk.bytes[:8], "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [key])
        if not cursor.fetchone()[0]:
            return
    try:
        row.refresh_from_db()
        if row.status not in ("pending", "running"):
            return
        row.status = "running"
        row.save(update_fields=["status"])
        try:
            merged = move_branch(row)
        except Exception as error:
            # A failed push might have succeeded remotely: leave the same grant recoverable.
            row.error = str(error) if type(error) is ValueError else type(error).__name__
            if row.error in (
                "target_changed",
                "configuration_changed",
                "source_changed",
                "merge_request_changed",
                "merge_request_closed",
                "non_fast_forward",
                "WbsConflict",
                "PermissionDenied",
            ):
                row.status = "failed"
            row.save(update_fields=["status", "error"])
            return
        with transaction.atomic():
            config = RequirementReviewConfig.objects.select_for_update().get(pk=row.config_id)
            if config.revision != row.config_revision:
                raise RuntimeError("Configuration changed during adoption")
            config.adopted_sha = merged
            row.merged_sha = merged
            config.save(update_fields=["adopted_sha", "updated_at"])
            row.status, row.error, row.completed_at = "completed", "", timezone.now()
            row.save(update_fields=["status", "error", "completed_at", "merged_sha"])
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [key])
