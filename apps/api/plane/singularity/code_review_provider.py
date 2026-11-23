# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.
"""Controlled project service identities; no fallback to a member's credentials."""

import json
import os
from pathlib import Path
from .repository_provider import RepositoryProvider, component, sha
from .repository_transport import RepositoryError


def provider_for(repository):
    if not repository.enabled or repository.purpose != "development" or repository.instance.provider != "gitlab":
        raise RepositoryError("review_repository_unavailable", 403)
    try:
        config = json.loads(Path(os.environ["CODE_REVIEW_IDENTITIES_FILE"]).read_text(encoding="utf-8-sig"))
        entry = config[str(repository.project_id)][str(repository.instance_id)]
        token = Path(entry["token_file"]).read_text(encoding="utf-8-sig").strip()
        if not token:
            raise ValueError()
    except (KeyError, ValueError, OSError):
        raise RepositoryError("review_service_identity_unavailable", 503) from None
    provider = RepositoryProvider(repository.instance, token)
    actor, _ = provider.actor()
    if actor != str(entry["actor_id"]):
        raise RepositoryError("review_service_identity_changed", 403)
    provider.metadata(repository.external_id)
    return provider


def remote_version(link):
    provider = provider_for(link.repository)
    root = "/projects/" + component(link.repository.external_id)
    mr = provider.http.get(root + "/merge_requests/" + str(link.mr_iid))
    if mr.get("target_project_id") != int(link.repository.external_id) or mr.get("iid") != link.mr_iid:
        raise RepositoryError("review_mr_identity_changed", 409)
    state = mr.get("state")
    if state not in ("opened", "closed", "merged"):
        raise RepositoryError("review_mr_state_unknown", 503)
    refs = mr.get("diff_refs") or {}
    source = sha(refs.get("head_sha"))
    if state == "merged":
        # A previously observed final source is sufficient only when GitLab still
        # confirms it. Never recompute a historical baseline against today's target.
        versions = provider.http.get(root + "/merge_requests/" + str(link.mr_iid) + "/versions", {"per_page": 100})
        final = next((v for v in versions if v.get("head_commit_sha") == source), None)
        if not final:
            raise RepositoryError("review_historical_baseline_unavailable", 503)
        target, base = sha(final.get("start_commit_sha")), sha(final.get("base_commit_sha"))
    else:
        target = provider.resolve(link.repository, mr["target_branch"])[2]
        merge = provider.http.get(root + "/repository/merge_base", {"refs[]": [source, target]})
        base = sha(merge.get("id"))
    return dict(
        source_sha=source,
        target_sha=target,
        merge_base=base,
        target_branch=mr["target_branch"],
        source_branch=mr["source_branch"],
        state=state,
        draft=bool(mr.get("draft") or mr.get("work_in_progress")),
        web_url=mr["web_url"],
    )


def list_merge_requests(repository, page=1):
    provider = provider_for(repository)
    rows = provider.http.get(
        "/projects/" + component(repository.external_id) + "/merge_requests",
        {"scope": "all", "state": "all", "per_page": 20, "page": page, "order_by": "updated_at"},
    )
    return [
        {
            "iid": row["iid"],
            "title": row["title"],
            "state": row["state"],
            "draft": bool(row.get("draft")),
            "web_url": row["web_url"],
        }
        for row in rows
    ]
