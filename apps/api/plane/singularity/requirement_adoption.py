# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Isolated Git writer: fast-forward, compare-and-swap and recoverable adoption."""

import base64
import os
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote
from django.db import transaction
from django.utils import timezone
from plane.db.models import RequirementAdoption, RequirementReviewConfig
from .requirement_review import current_input, provider_for, authority, target_head
from .wbs import require_member


def move_branch(row):
    """Fetch trusted refs, verify ancestry and CAS the exact pre-authorized update."""
    config = current_input(row.run)
    require_member(row.actor, config.issue.project, True)
    repo = authority(config)
    provider = provider_for(config)
    metadata = provider.metadata(repo.external_id)
    head = target_head(config, provider)
    if head == row.source_sha:
        return  # Recover an acknowledged-or-lost successful CAS.
    if head != row.target_sha:
        raise ValueError("target_changed")
    if config.revision != row.config_revision:
        raise ValueError("configuration_changed")
    token = Path(os.environ["DOCUMENT_ADOPTION_TOKEN_FILE"]).read_text(encoding="utf-8-sig").strip()
    url = repo.instance.web_url.rstrip("/") + "/" + quote(metadata["path"], safe="/") + ".git"
    header = "Authorization: Basic " + base64.b64encode(("oauth2:" + token).encode()).decode()
    env = {
        **os.environ,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraHeader",
        "GIT_CONFIG_VALUE_0": header,
    }
    if repo.instance.ca_file:
        env.update(GIT_CONFIG_COUNT="2", GIT_CONFIG_KEY_1="http.sslCAInfo", GIT_CONFIG_VALUE_1=repo.instance.ca_file)
    with tempfile.TemporaryDirectory(prefix="requirement-adopt-") as work:

        def git(*args, error_code="git_operation_failed"):
            result = subprocess.run(
                ["git", "-C", work, "-c", "protocol.file.allow=never", *args], env=env, capture_output=True, timeout=90
            )
            if result.returncode:
                raise ValueError(error_code)  # Never expose remote diagnostics or credentials.
            return result.stdout.decode().strip()

        git("init", "--bare")
        git("remote", "add", "origin", url)
        unborn = set(row.target_sha) == {"0"}
        git(
            "fetch",
            "--no-tags",
            "origin",
            f"refs/heads/{config.draft_branch}:refs/heads/draft",
            "refs/heads/main:refs/heads/main" if unborn else f"refs/heads/{config.adopted_branch}:refs/heads/adopted",
        )
        git("merge-base", "--is-ancestor", row.source_sha, "refs/heads/draft", error_code="source_no_longer_reachable")
        git(
            "merge-base",
            "--is-ancestor",
            row.run.snapshot["baseline_sha"] if unborn else row.target_sha,
            row.source_sha,
            error_code="non_fast_forward",
        )
        # The server hook independently checks this exact grant, actor and current membership.
        git(
            "push",
            "origin",
            f"{row.source_sha}:refs/heads/{config.adopted_branch}",
            f"--force-with-lease=refs/heads/{config.adopted_branch}:{'' if unborn else row.target_sha}",
        )
    _, _, head, _ = provider.resolve(repo, config.adopted_branch)
    if head != row.source_sha:
        raise ValueError("target_verification_failed")


def process_one():
    """Hold a DB advisory lock per operation; recover running writes after process death."""
    from django.db import connection

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
            move_branch(row)
        except Exception as error:
            # A failed push might have succeeded remotely: leave the same grant recoverable.
            row.error = str(error) if type(error) is ValueError else type(error).__name__
            if row.error in (
                "target_changed",
                "configuration_changed",
                "source_no_longer_reachable",
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
            config.adopted_sha = row.source_sha
            config.save(update_fields=["adopted_sha", "updated_at"])
            row.status, row.error, row.completed_at = "completed", "", timezone.now()
            row.save(update_fields=["status", "error", "completed_at"])
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [key])
