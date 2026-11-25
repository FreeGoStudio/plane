# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Freeze repository documents; expose review and adoption without conflating approval."""

import re
import os
import json
from html import escape
from html.parser import HTMLParser
from datetime import timedelta
from pathlib import PurePosixPath

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from plane.db.models import RequirementReviewConfig, RequirementReviewRun, RequirementAdoption, RequirementReviewEvent
from .repository_bindings import resolve_repository
from .repository_provider import RepositoryProvider, safe_path
from .repository_provider import component
from .repository_transport import RepositoryError
from .vault import selected_credential
from .wbs import require_member, digest, WbsConflict

RULE_VERSION = "documents-v1"
MAX_BYTES = 300000
MAX_FILES = 80
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".mmd"}


def branch_name(value):
    """Accept ordinary Git branch names, excluding ambiguous revisions and main."""
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,199}", value)
        or any(x in value for x in ("..", "//", "@{"))
        or any(p.startswith(".") or p.endswith((".", ".lock")) for p in value.split("/"))
        or value.endswith("/")
        or value == "main"
    ):
        raise ValidationError("Invalid requirement branch")
    return value


def authority(config, user=None):
    """Revalidate current membership and the authoritative documentation binding."""
    require_member(user or config.owner, config.issue.project, True)
    repo, revision = resolve_repository(config.issue.project, "documentation")
    if not config.enabled or repo.pk != config.repository_id or revision != config.binding_revision:
        raise WbsConflict("Repository binding changed; reconfigure document review")
    return repo


def provider_for(config):
    repo = authority(config)
    _, token = selected_credential(config.owner, repo)
    return RepositoryProvider(repo.instance, token)


def target_head(config, provider):
    """A missing adopted branch is an explicit unborn ref, never an accepted revision."""
    provider.metadata(config.repository.external_id)
    try:
        return provider.resolve(config.repository, config.adopted_branch)[2]
    except RepositoryError as error:
        if error.status == 404 and not config.adopted_sha:
            return "0" * 40
        raise


def normalize_basis(value):
    """Ignore editor-only wrappers/attributes while retaining text, structure and links."""
    parts = []

    class Parser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag in ("div", "span"):
                return
            semantic = sorted(
                (key, val or "")
                for key, val in attrs
                if key in ("href", "src", "alt", "title", "colspan", "rowspan", "checked", "start", "value")
            )
            parts.append("<" + tag + "".join(f' {key}="{escape(val, quote=True)}"' for key, val in semantic) + ">")

        def handle_endtag(self, tag):
            if tag not in ("div", "span"):
                parts.append("</" + tag + ">")

        def handle_data(self, data):
            parts.append(escape(data))

    parser = Parser()
    parser.feed(value["description_html"] or "")
    parser.close()
    return {"title": value["title"], "description_html": "".join(parts)}


def basis(issue):
    return normalize_basis({"title": issue.name, "description_html": issue.description_html or ""})


@transaction.atomic
def configure(user, issue, data):
    """Register an explicitly identified branch pair without changing repository content."""
    require_member(user, issue.project, True)
    if set(data) != {"draft_branch", "adopted_branch", "paths", "expected_revision"}:
        raise ValidationError("Provide branches, document paths and expected_revision")
    draft, target = branch_name(data["draft_branch"]), branch_name(data["adopted_branch"])
    paths = data["paths"]
    if draft == target or not isinstance(paths, list) or not 1 <= len(paths) <= 20:
        raise ValidationError("Distinct branches and bounded document paths required")
    for path in paths:
        safe_path(path, False)
    if len(set(paths)) != len(paths):
        raise ValidationError("Duplicate document paths")
    repo, revision = resolve_repository(issue.project, "documentation")
    if repo.instance.provider != "gitlab":
        raise ValidationError("Document review currently requires GitLab")
    # Lock the parent even when its configuration has not yet been created.
    type(issue).objects.select_for_update().get(pk=issue.pk)
    old = RequirementReviewConfig.objects.select_for_update().filter(issue=issue).first()
    if data["expected_revision"] != (old.revision if old else 0):
        raise WbsConflict("Review configuration changed")
    if old and RequirementAdoption.objects.filter(config=old, status__in=["pending", "running"]).exists():
        raise WbsConflict("An adoption must finish before reconfiguration")
    values = dict(
        repository=repo,
        binding_revision=revision,
        owner=user,
        draft_branch=draft,
        adopted_branch=target,
        paths=paths,
        enabled=True,
        error="",
        poll_after=None,
        revision=old.revision + 1 if old else 1,
    )
    row, _ = RequirementReviewConfig.objects.update_or_create(issue=issue, defaults=values)
    return row


def read_documents(config, provider, commit):
    """Read all registered text at one immutable commit; never silently truncate."""
    files, visited = {}, set()

    def read(path, depth=0):
        if path in visited:
            return
        visited.add(path)
        if depth > 12 or len(visited) > 250:
            raise ValidationError("Document tree exceeds input limits")
        if PurePosixPath(path).suffix.lower() in TEXT_SUFFIXES:
            result = provider.file(config.repository, commit, path)
            if result["commit_sha"] != commit:
                raise ValidationError("Repository returned a different commit")
            files[path] = result["content"]
            if len(files) > MAX_FILES or sum(len(x.encode("utf-8")) for x in files.values()) > MAX_BYTES:
                raise ValidationError("Documents exceed input limits")
            return
        page = 1
        while page:
            result = provider.directory(config.repository, commit, path, page)
            if result["commit_sha"] != commit:
                raise ValidationError("Repository returned a different commit")
            for entry in result["entries"]:
                if entry["type"] == "tree" or PurePosixPath(entry["path"]).suffix.lower() in TEXT_SUFFIXES:
                    if entry["type"] not in ("tree", "blob"):
                        raise ValidationError("Unsupported document type")
                    read(entry["path"], depth + 1)
            page = result["next_page"]

    for path in config.paths:
        before = len(files)
        read(path)
        if not files or (len(files) == before and not any(p == path or p.startswith(path + "/") for p in files)):
            raise ValidationError("A registered document path is empty")
    return dict(sorted(files.items()))


def capture(config, source_sha=None):
    """Resolve HEAD once, snapshot full documents, then persist idempotently."""
    provider = provider_for(config)
    _, _, commit = provider.resolve(config.repository, source_sha or config.draft_branch)
    if source_sha and commit != source_sha:
        raise ValidationError("Repository returned a different commit")
    config.issue.refresh_from_db()
    source_basis = basis(config.issue)
    key = digest({"sha": commit, "revision": config.revision, "basis": source_basis, "rules": RULE_VERSION})
    old = RequirementReviewRun.objects.filter(config=config, request_key=key).first()
    if old:
        return old
    documents = read_documents(config, provider, commit)
    baseline = target_head(config, provider)
    if set(baseline) == {"0"}:
        try:
            marker = json.loads(provider.file(config.repository, commit, ".singularity/requirement.json")["content"])
            baseline = marker["base_sha"]
            if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", baseline):
                raise ValidationError("Invalid requirement baseline")
            main = provider.resolve(config.repository, "main")[2]
            for descendant in (main, commit):
                ancestor = provider.http.get(
                    "/projects/" + component(config.repository.external_id) + "/repository/merge_base",
                    {"refs[]": [baseline, descendant]},
                )
                if ancestor.get("id") != baseline:
                    raise ValidationError("Requirement baseline must belong to main and the draft history")
        except RepositoryError as error:
            if error.status not in (404, 422):
                raise
            # Explicit legacy branches predate the workspace marker.
            baseline = provider.resolve(config.repository, "main")[2]
    snapshot = {
        "documents": documents,
        "basis": source_basis,
        "rules": RULE_VERSION,
        "config_revision": config.revision,
        "repository_id": str(config.repository_id),
        "binding_revision": config.binding_revision,
        "branch": config.draft_branch,
        "source_sha": commit,
        "baseline_sha": baseline,
    }
    with transaction.atomic():
        current = RequirementReviewConfig.objects.select_for_update().get(pk=config.pk)
        if current.revision != config.revision:
            raise WbsConflict("Configuration changed during capture")
        row, _ = RequirementReviewRun.objects.get_or_create(
            config=config,
            request_key=key,
            defaults={"source_sha": commit, "snapshot": snapshot, "input_digest": digest(snapshot)},
        )
        current.latest_sha, current.error = commit, ""
        current.save(update_fields=["latest_sha", "error", "updated_at"])
        return row


def capture_error(error):
    """Keep code locations and structural counts, never arbitrary exception payloads."""
    if isinstance(error, RepositoryError):
        return error.code[:100]
    detail = type(error).__name__
    # Python's unpack counts are safe; URLs, response bodies and locals are not.
    match = re.fullmatch(r"not enough values to unpack \(expected (\d+), got (\d+)\)", str(error))
    if isinstance(error, ValueError) and match:
        detail += f": unpack expected {match[1]}, got {match[2]}"
    trace = error.__traceback__
    location = ""
    while trace:
        code = trace.tb_frame.f_code
        filename = code.co_filename.replace("\\", "/")
        if "/plane/singularity/" in filename:
            location = f" at {filename.rsplit('/', 1)[-1]}:{trace.tb_lineno}"
        trace = trace.tb_next
    return (detail + location)[:100]


def poll_one():
    """Lease one due configuration; failures remain visible and retry independently."""
    with transaction.atomic():
        from django.db.models import Q

        config = (
            RequirementReviewConfig.objects.select_for_update(skip_locked=True)
            .filter(enabled=True)
            .filter(Q(poll_after__isnull=True) | Q(poll_after__lte=timezone.now()))
            .order_by("poll_after", "issue_id")
            .first()
        )
        if not config:
            return
        config.poll_after = timezone.now() + timedelta(seconds=60)
        config.save(update_fields=["poll_after"])
    try:
        # Drain durable push events before reconciling HEAD, so rapid pushes retain history.
        for event in RequirementReviewEvent.objects.filter(
            repository=config.repository, branch=config.draft_branch, processed_at__isnull=True
        ).order_by("created_at")[:10]:
            if set(event.source_sha) != {"0"}:
                capture(config, event.source_sha)
            event.processed_at = timezone.now()
            event.save(update_fields=["processed_at"])
        capture(config)
        RequirementReviewConfig.objects.filter(pk=config.pk, revision=config.revision).update(error="")
    except Exception as error:
        RequirementReviewConfig.objects.filter(pk=config.pk, revision=config.revision).update(
            error=capture_error(error)
        )


def is_superseded(row):
    """Keep an older fixed-version verdict historical once explicit reassessment starts."""
    return RequirementReviewRun.objects.filter(
        config_id=row.config_id,
        source_sha=row.source_sha,
        created_at__gt=row.created_at,
        snapshot__has_key="rereview_of",
    ).exists()


def current_input(row):
    """An approval may only consume the same configuration and business basis."""
    config = RequirementReviewConfig.objects.select_related("issue__project", "owner", "repository__instance").get(
        pk=row.config_id
    )
    authority(config)
    if (
        config.revision != row.snapshot["config_revision"]
        or basis(config.issue) != normalize_basis(row.snapshot["basis"])
        or row.snapshot["rules"] != RULE_VERSION
    ):
        raise WbsConflict("Review inputs changed; request a new review")
    if is_superseded(row):
        raise WbsConflict("A newer explicit reassessment supersedes this review")
    return config


@transaction.atomic
def retry_run(user, row, key):
    require_member(user, row.config.issue.project, True)
    current_input(row)
    if row.status != "failed":
        raise WbsConflict("Only an execution failure can be retried")
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", key):
        raise ValidationError("Invalid retry key")
    new, _ = RequirementReviewRun.objects.get_or_create(
        config=row.config,
        request_key="retry:" + key,
        defaults={
            "source_sha": row.source_sha,
            "snapshot": row.snapshot,
            "input_digest": row.input_digest,
            "merge_request": row.merge_request,
            "retry_of": row,
        },
    )
    if new.retry_of_id != row.pk:
        raise WbsConflict("Retry key belongs to another run")
    return new


@transaction.atomic
def rereview_run(user, row, key):
    """Explicitly reassess the same unadopted fixed input, preserving completed reports."""
    require_member(user, row.config.issue.project, True)
    config = RequirementReviewConfig.objects.select_for_update().get(pk=row.config_id)
    if row.status not in ("completed", "failed"):
        raise WbsConflict("Wait for review completion")
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", key):
        raise ValidationError("Invalid rereview key")
    prior = RequirementReviewRun.objects.filter(config=config, request_key="rereview:" + key).first()
    if prior:
        if prior.retry_of_id != row.pk:
            raise WbsConflict("Rereview key belongs to another run")
        return prior
    current_input(row)
    if version_adoption(row):
        raise WbsConflict("An adopted or adopting version cannot be reassessed in place")
    if RequirementReviewRun.objects.filter(config=config, status__in=["queued", "running"]).exists():
        raise WbsConflict("Another review is active")
    from .requirement_review_coverage import POLICY_VERSION

    snapshot = {**row.snapshot, "report_policy": POLICY_VERSION, "rereview_of": str(row.pk)}
    return RequirementReviewRun.objects.create(
        config=config,
        request_key="rereview:" + key,
        source_sha=row.source_sha,
        snapshot=snapshot,
        input_digest=digest(snapshot),
        merge_request=row.merge_request,
        retry_of=row,
    )


def version_adoption(row):
    """Find an effective adoption independently of request keys and history pages."""
    return (
        RequirementAdoption.objects.filter(
            config_id=row.config_id,
            config_revision=row.snapshot["config_revision"],
            source_sha=row.source_sha,
            status__in=["pending", "running", "completed"],
        )
        .order_by("status", "-created_at")
        .first()
    )


@transaction.atomic
def adopt(user, row, data, human_session=False):
    """Persist explicit immutable authorization; only the executor updates Git."""
    config = RequirementReviewConfig.objects.select_for_update().get(pk=row.config_id)
    require_member(user, config.issue.project, True)
    current_input(row)
    if str(config.repository_id) not in os.environ.get("DOCUMENT_REVIEW_GATED_REPOSITORIES", "").split(","):
        raise WbsConflict("Repository adoption gate has not been installed and verified")
    if set(data) - {"idempotency_key", "target_sha", "override", "reason", "confirmed"}:
        raise ValidationError("Unknown adoption fields")
    key, target = data.get("idempotency_key", ""), data.get("target_sha", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", key) or not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", target):
        raise ValidationError("Exact target SHA and idempotency key required")
    override = data.get("override", False)
    if not isinstance(override, bool):
        raise ValidationError("override must be a boolean")
    reason = str(data.get("reason", "")).strip()
    if override and (not human_session or data.get("confirmed") is not True or not 1 <= len(reason) <= 5000):
        raise ValidationError("A signed-in human must explicitly confirm and explain the override")
    if not override and (row.status != "completed" or row.result.get("verdict") != "passed"):
        raise WbsConflict("AI review has not passed")
    if override and row.status not in ("completed", "failed"):
        raise WbsConflict("Wait for review completion or an execution failure before override")
    old = RequirementAdoption.objects.filter(config=config, request_key=key).first()
    if old:
        if (
            old.run_id != row.pk
            or old.actor_id != user.pk
            or old.target_sha != target
            or old.kind != ("override" if override else "ai_passed")
            or old.reason != reason
        ):
            raise WbsConflict("Adoption key already used")
        return old
    # The configuration lock serializes different clients/request keys too.
    # Preserve the original authorization and audit actor; failed attempts can retry.
    existing = version_adoption(row)
    if existing:
        return existing
    if RequirementAdoption.objects.filter(config=config, status__in=["pending", "running"]).exists():
        raise WbsConflict("An adoption is already active")
    return RequirementAdoption.objects.create(
        config=config,
        run=row,
        actor=user,
        source_sha=row.source_sha,
        target_sha=target,
        config_revision=config.revision,
        kind="override" if override else "ai_passed",
        reason=reason,
        request_key=key,
    )
