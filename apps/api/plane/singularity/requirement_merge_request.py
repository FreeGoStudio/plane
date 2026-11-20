# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Repository-scoped GitLab MR writes, isolated from the model worker."""

import os
from datetime import timedelta
from pathlib import Path
from django.db.models import Q
from django.utils import timezone

from .repository_provider import component
from .repository_transport import RepositoryTransport
from .requirement_review import current_input, provider_for, target_head


def transport(config):
    """Use only the dedicated executor credential, never a reader or admin token."""
    token = Path(os.environ["DOCUMENT_ADOPTION_TOKEN_FILE"]).read_text(encoding="utf-8-sig").strip()
    return RepositoryTransport(config.repository.instance, token)


def ensure_merge_request(run):
    """Reuse the exact branch pair, recovering a lost create response without duplicates."""
    config = current_input(run)
    http = transport(config)
    root = "/projects/" + component(config.repository.external_id)
    if run.merge_request:
        return http, root + "/merge_requests/" + str(run.merge_request["iid"])
    provider = provider_for(config)
    head = target_head(config, provider)
    if set(head) == {"0"}:
        # Legacy configurations may predate the target branch. The server hook
        # permits only this recorded initial baseline, never unreviewed documents.
        http.request(
            "POST",
            root + "/repository/branches",
            body={
                "branch": config.adopted_branch,
                "ref": run.snapshot["baseline_sha"],
            },
            success_statuses=(201,),
        )
    values = http.get(
        root + "/merge_requests",
        {
            "state": "opened",
            "source_branch": config.draft_branch,
            "target_branch": config.adopted_branch,
            "per_page": 100,
        },
    )
    matches = [
        x
        for x in values
        if str(x.get("source_project_id")) == config.repository.external_id
        and str(x.get("target_project_id")) == config.repository.external_id
    ]
    if len(matches) > 1:
        raise ValueError("ambiguous_merge_request")
    mr = (
        matches[0]
        if matches
        else http.request(
            "POST",
            root + "/merge_requests",
            body={
                "source_branch": config.draft_branch,
                "target_branch": config.adopted_branch,
                "title": f"{config.adopted_branch}: review requirement documents",
                "description": (
                    "Requirement checks are bound to exact commits in Plane. "
                    "Merge through the checked requirement workflow."
                ),
                "remove_source_branch": "false",
                "squash": "false",
            },
            success_statuses=(201,),
        )
    )
    run.merge_request = {"iid": mr["iid"], "web_url": mr["web_url"]}
    run.save(update_fields=["merge_request"])
    return http, root + "/merge_requests/" + str(mr["iid"])


def check_merge_request(config, mr, source):
    """An MR must still describe exactly this repository, branch pair and reviewed head."""
    if (
        str(mr.get("source_project_id")) != config.repository.external_id
        or str(mr.get("target_project_id")) != config.repository.external_id
        or mr.get("source_branch") != config.draft_branch
        or mr.get("target_branch") != config.adopted_branch
    ):
        raise ValueError("merge_request_changed")
    if mr.get("sha") != source:
        raise ValueError("source_changed")


def prepare_one():
    """Prepare a persisted review's MR before dispatch, without giving AI write credentials."""
    from plane.db.models import RequirementReviewRun

    run = (
        RequirementReviewRun.objects.filter(status="queued", merge_request={})
        .filter(Q(dispatch_at__isnull=True) | Q(dispatch_at__lt=timezone.now() - timedelta(seconds=60)))
        .order_by("created_at")
        .first()
    )
    if not run:
        return
    try:
        ensure_merge_request(run)
        RequirementReviewRun.objects.filter(pk=run.pk).update(error="", dispatch_at=None)
    except Exception as error:
        RequirementReviewRun.objects.filter(pk=run.pk).update(
            error=getattr(error, "code", type(error).__name__)[:100], dispatch_at=timezone.now()
        )


def report_one():
    """Publish the exact review result on GitLab, without treating a status as merge authority."""
    from plane.db.models import RequirementReviewRun

    run = (
        RequirementReviewRun.objects.filter(status__in=["completed", "failed"], merge_request__reported__isnull=True)
        .exclude(merge_request={})
        .order_by("created_at")
        .first()
    )
    if not run:
        return
    config = current_input(run)
    state = "success" if run.status == "completed" and run.result.get("verdict") == "passed" else "failed"
    transport(config).request(
        "POST",
        "/projects/" + component(config.repository.external_id) + "/statuses/" + run.source_sha,
        body={
            "state": state,
            "name": "requirement-review/" + str(run.pk),
            "description": "Plane document review: " + (run.result.get("verdict") or run.status),
            "target_url": run.merge_request["web_url"],
        },
        success_statuses=(201,),
    )
    run.merge_request = {**run.merge_request, "reported": state}
    run.save(update_fields=["merge_request"])
