# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Task-locked code review commands. Remote observations never complete tasks."""

import os
import re
import uuid
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from plane.db.models import Issue, ProjectRepository, CodeReviewLink, CodeReviewRun, CodeReviewEvent
from .wbs import require_member, digest
from .code_review_provider import remote_version


class ReviewConflict(APIException):
    status_code = 409
    default_detail = "Code review evidence changed"


class ReviewUnavailable(APIException):
    status_code = 503
    default_detail = "Code review remote verification unavailable; retry"


def revision(issue):
    return CodeReviewEvent.objects.filter(issue=issue).count()


def audit(link, kind, actor=None, **payload):
    return CodeReviewEvent.objects.create(
        issue=link.issue,
        repository=link.repository,
        actor=actor,
        event_key=str(uuid.uuid4()),
        kind=kind,
        payload={"link_id": str(link.pk), **payload},
        processed_at=timezone.now(),
    )


def lock_issue(issue_id):
    return Issue.objects.select_for_update().get(pk=issue_id)


def expect_revision(issue, data):
    if data.get("expected_revision") != revision(issue):
        raise ReviewConflict("Association set changed; refresh")


def review_settings():
    return {
        "tool_version": os.environ.get("CODE_REVIEW_OCR_VERSION", "1.14.1"),
        "model": os.environ.get("CODE_REVIEW_MODEL", os.environ.get("DOCUMENT_REVIEW_MODEL", "gpt-6.1-sol")),
        "protocol": "openai-responses",
        "language": "zh-CN",
        "rules": "plane-ocr-v1",
        "effort": "medium",
        "excluded": [".opencodereview/**"],
    }


def eligible(version):
    return version.get("state") in ("opened", "merged") and not version.get("draft")


def capture(link, version):
    """Caller owns the issue lock; transitions bump generation even when SHAs repeat."""
    settings = review_settings()
    previous = link.version
    changed = previous != version
    if changed:
        link.generation += 1
        link.version = version
        link.current_run = None
        audit(link, "version_changed", previous=previous, version=version)
    if eligible(version) and (not link.current_run_id or link.current_run.snapshot["settings"] != settings):
        if not changed:
            link.generation += 1
        snapshot = {
            "repository_id": str(link.repository_id),
            "mr_iid": link.mr_iid,
            "generation": link.generation,
            "version": version,
            "settings": settings,
        }
        row, _ = CodeReviewRun.objects.get_or_create(
            link=link,
            request_key="auto:" + digest(snapshot),
            defaults=dict(
                generation=link.generation,
                snapshot=snapshot,
                input_digest=digest(snapshot),
                source_sha=version["source_sha"],
                target_sha=version["target_sha"],
                merge_base=version["merge_base"],
            ),
        )
        link.current_run = row
    link.error = ""
    link.poll_after = timezone.now() + timedelta(minutes=1)
    link.save()
    return link.current_run


@transaction.atomic
def add_link(user, issue, data):
    require_member(user, issue.project, True)
    issue = lock_issue(issue.pk)
    expect_revision(issue, data)
    repo = ProjectRepository.objects.filter(
        pk=data.get("repository_id"),
        project=issue.project,
        enabled=True,
        purpose="development",
        instance__enabled=True,
        instance__provider="gitlab",
    ).first()
    iid = data.get("mr_iid")
    if not repo or type(iid) is not int or iid < 1:
        raise ValidationError("Select a development repository and positive MR iid")
    if CodeReviewLink.objects.filter(issue=issue, repository=repo, mr_iid=iid, active=True).exists():
        raise ReviewConflict("MR already linked")
    link = CodeReviewLink(issue=issue, repository=repo, mr_iid=iid, created_by=user)
    version = remote_version(link)
    link.save()
    audit(link, "linked", user)
    capture(link, version)
    return link


@transaction.atomic
def remove_link(user, link, data):
    require_member(user, link.issue.project, True)
    issue = lock_issue(link.issue_id)
    expect_revision(issue, data)
    link.refresh_from_db()
    reason = str(data.get("reason", "")).strip()
    if not reason or len(reason) > 5000:
        raise ValidationError("A correction/removal reason is required (max 5000 characters)")
    if not link.active:
        raise ReviewConflict("Association already removed")
    link.active = False
    link.save(update_fields=["active"])
    audit(link, "unlinked", user, reason=reason)
    return link


def request_key(data):
    key = data.get("idempotency_key", "")
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", key):
        raise ValidationError("An idempotency_key is required")
    return key


@transaction.atomic
def rerun(user, link, data):
    require_member(user, link.issue.project, True)
    issue = lock_issue(link.issue_id)
    key = "manual:" + request_key(data)
    previous = CodeReviewRun.objects.filter(link=link, request_key=key).first()
    if previous:
        return previous
    expect_revision(issue, data)
    link.refresh_from_db()
    if not link.active:
        raise ReviewConflict("Association removed")
    version = remote_version(link)
    if not eligible(version):
        raise ReviewConflict("Draft or closed MR cannot be reviewed for completion")
    link.generation += 1
    link.version = version
    snapshot = {
        "repository_id": str(link.repository_id),
        "mr_iid": link.mr_iid,
        "generation": link.generation,
        "version": version,
        "settings": review_settings(),
    }
    row = CodeReviewRun.objects.create(
        link=link,
        request_key=key,
        generation=link.generation,
        snapshot=snapshot,
        input_digest=digest(snapshot),
        source_sha=version["source_sha"],
        target_sha=version["target_sha"],
        merge_base=version["merge_base"],
    )
    link.current_run = row
    link.error = ""
    link.save()
    audit(link, "rerun", user, run_id=str(row.pk))
    return row
