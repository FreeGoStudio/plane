# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Versioned WBS changes: analysis is read-only, human approval applies atomically."""

import difflib
import json
import re
from pathlib import PurePosixPath
from types import SimpleNamespace

import nh3
from crum import impersonate
from django.db.models import Q
from django.utils import timezone
from django.utils.html import strip_tags
from markdown_it import MarkdownIt

from plane.api.serializers import IssueSerializer
from plane.db.models import (
    Issue,
    IssueActivity,
    IssueRelation,
    State,
    WbsRun,
    RequirementReviewConfig,
    RequirementAdoption,
)
from .wbs import WbsConflict, digest


PRIMARY_PRD_POLICY = "primary-prd-v1"


def primary_prd_paths(paths):
    """Resolve the registered delivery directory, never search the repository."""
    from .requirement_review import TEXT_SUFFIXES

    candidates = set()
    for value in paths:
        path = PurePosixPath(value)
        if path.name == "prd.md":
            candidates.add(str(path))
        elif path.suffix.lower() not in TEXT_SUFFIXES:
            candidates.add(str(path / "prd.md"))
    if len(candidates) != 1:
        raise WbsConflict(
            "Register one delivery directory or its prd.md for WBS; primary prd.md is missing or ambiguous"
        )
    return sorted(candidates)


def read_wbs_documents(config, provider, commit, paths):
    """Reuse fixed-SHA/size validation without modifying the review configuration."""
    from .requirement_review import read_documents
    from .repository_transport import RepositoryError

    try:
        documents = read_documents(SimpleNamespace(repository=config.repository, paths=paths), provider, commit)
    except RepositoryError as error:
        if error.code in {"file_not_found", "upstream_resource_invisible", "file_not_found_or_directory_limit"}:
            raise WbsConflict(
                f"Primary prd.md is missing or unreadable at {paths[0]}; no alternative file was selected"
            ) from None
        raise
    if any(not body.strip() for body in documents.values()):
        raise WbsConflict("Primary prd.md is empty; complete the implementation requirements before WBS")
    return documents


def source_for(issue, primary_only=True):
    from .requirement_review import provider_for, read_documents, basis

    config = RequirementReviewConfig.objects.filter(issue=issue).first()
    if not config:
        body = basis(issue)
        return {"kind": "body", "basis": body, "digest": digest(body)}
    provider = provider_for(config)
    commit = provider.resolve(config.repository, config.draft_branch)[2]
    paths = primary_prd_paths(config.paths) if primary_only else config.paths
    documents = (
        read_wbs_documents(config, provider, commit, paths)
        if primary_only
        else read_documents(config, provider, commit)
    )
    return {
        "kind": "documents",
        "repository_id": str(config.repository_id),
        "revision": config.revision,
        "commit": commit,
        "paths": paths,
        "documents": documents,
        "basis": basis(issue),
        "digest": digest(documents),
        **({"input_policy": PRIMARY_PRD_POLICY} if primary_only else {}),
    }


def children_for(issue, lock=False):
    rows = Issue.issue_objects.filter(parent=issue).order_by("id")
    if lock:
        rows = rows.select_for_update(of=("self",))
    rows = list(rows.select_related("state"))
    progressed = set(
        State.all_state_objects.filter(project=issue.project, group__in=["started", "completed"]).values_list(
            "id", flat=True
        )
    )
    history = set(
        IssueActivity.objects.filter(issue_id__in=[c.pk for c in rows], field="state")
        .filter(Q(old_identifier__in=progressed) | Q(new_identifier__in=progressed))
        .values_list("issue_id", flat=True)
    )
    result = []
    for child in rows:
        group = child.state.group if child.state else "unknown"
        stage = (
            "completed"
            if group == "completed"
            else "started"
            if group == "started" or child.pk in history
            else "unstarted"
            if group in ["backlog", "unstarted", "cancelled"]
            else "unknown"
        )
        result.append(
            {
                "id": str(child.pk),
                "name": child.name,
                "description_html": child.description_html,
                "state_id": str(child.state_id) if child.state_id else None,
                "state_group": group,
                "stage": stage,
                "updated_at": child.updated_at.isoformat(),
            }
        )
    return result


def source_text(source):
    if source["kind"] == "documents":
        return "\n".join(f"# {path}\n{body}" for path, body in source["documents"].items())
    return strip_tags(source["basis"]["description_html"])


def snapshot_for(issue, previous):
    source = source_for(issue)
    text = source_text(source)
    old = previous.snapshot.get("source") if previous else None
    comparable = old and all(
        old.get(key) == source.get(key) for key in ("kind", "repository_id", "paths", "input_policy")
    )
    children = children_for(issue)
    return {
        "workflow": 2,
        "name": issue.name,
        "description_html": issue.description_html,
        "updated_at": issue.updated_at.isoformat(),
        "source": source,
        "criteria": list(dict.fromkeys(re.findall(r"\bAC[-_]?\d+\b", text, re.I))) or ["REQ-1"],
        "existing_children": children,
        "previous_run_id": str(previous.pk) if previous else None,
        "previous_result": previous.result if previous else {},
        "source_diff": "\n".join(
            difflib.unified_diff(
                source_text(old).splitlines(),
                text.splitlines(),
                fromfile="previous",
                tofile="current",
                lineterm="",
            )
        )
        if comparable
        else "",
        "scenario": "development"
        if any(c["stage"] != "unstarted" for c in children)
        else "created"
        if children
        else "draft"
        if previous
        else "initial",
    }


def start_update(user, issue, data, skill_files):
    """Reuse ordinary updates; explicitly regenerate only when no worker is active."""
    regenerate = data.get("mode") == "regenerate"
    if regenerate and WbsRun.objects.filter(issue=issue, status__in=["queued", "running"]).exists():
        raise WbsConflict("WBS analysis is in progress; wait before regenerating")
    previous = WbsRun.objects.filter(issue=issue).order_by("-created_at").first()
    snapshot = snapshot_for(issue, previous)
    if regenerate:
        snapshot["request_mode"] = "regenerate"
    if skill_files:
        snapshot["skill_files"] = skill_files
    active = WbsRun.objects.filter(issue=issue, status__in=["queued", "running", "ready"])
    for old in active:
        if (
            not regenerate
            and previous is not None
            and old.pk == previous.pk
            and old.snapshot.get("source") == snapshot["source"]
            and old.snapshot["existing_children"] == snapshot["existing_children"]
        ):
            # The UI refreshes the latest run after a successful POST. Reuse it
            # without changing its author, execution, result or review decision.
            return old
    active.update(status="superseded", execution_token=None, lease_until=None)
    return WbsRun.objects.create(
        issue=issue,
        requested_by=user,
        request_key=data["idempotency_key"],
        snapshot=snapshot,
        input_digest=digest(snapshot),
    )


def ensure_current(row, lock=False):
    if (
        source_for(row.issue, primary_only=row.snapshot["source"].get("input_policy") == PRIMARY_PRD_POLICY)
        != row.snapshot["source"]
    ):
        raise WbsConflict("PRD changed; update WBS again")
    if children_for(row.issue, lock=lock) != row.snapshot["existing_children"]:
        raise WbsConflict("Child tasks changed; update WBS again")
    if WbsRun.objects.filter(issue=row.issue, created_at__gt=row.created_at).exists():
        raise WbsConflict("A newer WBS analysis exists")


def ensure_adopted(row):
    source = row.snapshot["source"]
    if source["kind"] == "body":
        return
    from .requirement_review import provider_for, read_documents, target_head, normalize_basis

    config = RequirementReviewConfig.objects.get(issue=row.issue)
    adoption = (
        RequirementAdoption.objects.filter(
            config=config,
            config_revision=source["revision"],
            source_sha=source["commit"],
            status="completed",
            merged_sha=config.adopted_sha,
        )
        .select_related("run")
        .order_by("-completed_at")
        .first()
    )
    reviewed_documents = adoption.run.snapshot.get("documents", {}) if adoption else {}
    if source.get("input_policy") == PRIMARY_PRD_POLICY:
        reviewed_documents = {path: reviewed_documents.get(path) for path in source["paths"]}
    if (
        not adoption
        or reviewed_documents != source["documents"]
        or not adoption.run.snapshot.get("basis")
        or normalize_basis(adoption.run.snapshot["basis"]) != source["basis"]
    ):
        raise WbsConflict("Confirm this PRD version before applying WBS changes")
    provider = provider_for(config)
    target = target_head(config, provider)
    if target != adoption.merged_sha:
        raise WbsConflict("The adopted PRD no longer matches this analysis")
    documents = (
        read_wbs_documents(config, provider, target, source["paths"])
        if source.get("input_policy") == PRIMARY_PRD_POLICY
        else read_documents(config, provider, target)
    )
    if documents != source["documents"]:
        raise WbsConflict("The adopted PRD no longer matches this analysis")


def readiness(row):
    if row.snapshot.get("workflow") != 2 or row.status != "ready":
        return None
    try:
        ensure_current(row)
        ensure_adopted(row)
        return {"can_apply": True, "reason": "", "body_confirmation_required": row.snapshot["source"]["kind"] == "body"}
    except WbsConflict as error:
        return {"can_apply": False, "reason": str(error.detail)}
    except Exception:
        return {"can_apply": False, "reason": "Unable to verify the PRD source; retry after restoring access"}


def validate_changes(value, snapshot):
    from .wbs_generation import ChangeDraft

    value = ChangeDraft.model_validate(value).model_dump()
    changes = {c["id"]: c for c in value["changes"]}
    targets = [c["target_id"] for c in value["changes"] if c["target_id"]]
    existing = {c["id"]: c for c in snapshot["existing_children"]}
    if any(c["target_id"] is not None and c["target_id"] not in existing for c in value["changes"]):
        raise ValueError("Unknown child reference")
    coverage = {c["criterion_id"]: c for c in value["coverage"]}
    if len(changes) != len(value["changes"]) or len(targets) != len(set(targets)) or set(targets) != set(existing):
        raise ValueError("Every existing child must appear exactly once")
    if len(coverage) != len(value["coverage"]) or set(coverage) != set(snapshot["criteria"]):
        raise ValueError("Invalid requirement coverage")
    for c in value["coverage"]:
        if not set(c["task_ids"]) <= changes.keys() or (not c["task_ids"]) != (c["disposition"] == "existing"):
            raise ValueError("Invalid coverage references")
        if c["disposition"] != "existing" and not any(changes[key]["task"] for key in c["task_ids"]):
            raise ValueError("A requirement gap needs implementation or investigation work")
    for change in changes.values():
        action, target, task = change["action"], change["target_id"], change["task"]
        if (action == "create") != (target is None) or (action in ["create", "update", "append"]) != (task is not None):
            raise ValueError("Invalid change action")
        if target and existing[target]["stage"] == "completed" and action not in ["keep", "append"]:
            raise ValueError("Completed tasks must retain their original acceptance")
        if task:
            if task["id"] != change["id"]:
                raise ValueError("Invalid task references: task ID mismatch")
            if not set(task["dependencies"]) <= changes.keys():
                raise ValueError("Invalid task references: unknown task dependency")
            if any(c not in coverage or change["id"] not in coverage[c]["task_ids"] for c in task["criteria"]):
                raise ValueError("Invalid task references: acceptance mapping mismatch")

    def visit(key, active, done):
        if key in active:
            raise ValueError("Cyclic dependency")
        if key in done:
            return
        for dep in (changes[key]["task"] or {}).get("dependencies", []):
            visit(dep, active | {key}, done)
        done.add(key)

    done = set()
    for key in changes:
        visit(key, set(), done)
    return value


def task_html(row, change, related=None):
    task = change["task"]
    text = (
        f"{task['scope']}\n\n## 产出\n{task['deliverable']}\n\n## 验收标准\n{task['acceptance']}"
        f"\n\n来源验收项：{', '.join(task['criteria'])}\n\n依赖：{', '.join(task['dependencies']) or '无'}"
        f"\n\nWBS：{row.pk} / {change['id']}\n\n责任角色：{task['role']}"
        f"\n\nPRD 版本：{row.snapshot['source'].get('commit', row.snapshot['source']['digest'])}"
    )
    if related:
        text += f"\n\n关联原任务：{related}"
    return nh3.clean(MarkdownIt().render(text))


def apply_changes(user, row, data):
    ensure_current(row, lock=True)
    ensure_adopted(row)
    if row.snapshot["source"]["kind"] == "body" and data.get("source_confirmed") is not True:
        raise WbsConflict("Explicit confirmation of this exact requirement text is required")
    result = validate_changes(row.result, row.snapshot)
    choices = data.get("choices", {})
    existing = {c["id"]: c for c in row.snapshot["existing_children"]}
    required = {
        c["id"]
        for c in result["changes"]
        if c["target_id"] and existing[c["target_id"]]["stage"] != "unstarted" and c["action"] != "keep"
    }
    if not isinstance(choices, dict) or set(choices) != required:
        raise WbsConflict("Confirm the action for every affected started or uncertain task")
    replacements = data.get("replacement_tasks", {})
    replacement_ids = {
        c["id"] for c in result["changes"] if not c["task"] and choices.get(c["id"]) in ["update", "append"]
    }
    if not isinstance(replacements, dict) or set(replacements) != replacement_ids:
        raise WbsConflict("Provide complete reviewed task content when replacing a cancellation")
    if replacements:
        from .wbs_generation import Task
        from rest_framework.exceptions import ValidationError

        try:
            for change in result["changes"]:
                if change["id"] not in replacements:
                    continue
                task = Task.model_validate(replacements[change["id"]]).model_dump()
                if any(not task[field].strip() for field in ["title", "role", "scope", "deliverable", "acceptance"]):
                    raise ValueError("Replacement task content cannot be blank")
                if task["id"] != change["id"] or not set(task["criteria"]) <= set(row.snapshot["criteria"]):
                    raise ValueError("Replacement must reference the current requirement criteria")
                change["task"], change["action"] = task, choices[change["id"]]
                for coverage in result["coverage"]:
                    if coverage["criterion_id"] in task["criteria"]:
                        coverage["disposition"] = "gap"
                        if change["id"] not in coverage["task_ids"]:
                            coverage["task_ids"].append(change["id"])
            result = validate_changes(result, row.snapshot)
        except ValueError:
            raise ValidationError("Invalid replacement task content or requirement references") from None
    actions = {}
    for change in result["changes"]:
        action = choices.get(change["id"], change["action"])
        allowed = {"update", "append", "cancel"} if change["task"] else {"keep", "cancel"}
        if change["target_id"] and existing[change["target_id"]]["stage"] == "completed":
            allowed = {"append"}
        if change["id"] in choices and action not in allowed:
            raise WbsConflict("Invalid action for the task's development stage")
        actions[change["id"]] = action
    cancelled = None
    if "cancel" in actions.values():
        cancelled = (
            State.objects.filter(project=row.issue.project, group="cancelled").order_by("sequence", "id").first()
        )
        if not cancelled:
            raise WbsConflict("Configure a cancelled state before approving cancellations")
    applied = []
    for change in result["changes"]:
        action = actions[change["id"]]
        target = change["target_id"]
        before = existing.get(target)
        if action == "keep":
            row.children[change["id"]] = target
            continue
        if action in ["create", "append"]:
            serializer = IssueSerializer(
                data={
                    "name": change["task"]["title"],
                    "parent": str(row.issue_id),
                    "description_html": task_html(row, change, target),
                    "external_source": "plane-wbs",
                    "external_id": f"{row.pk}:{change['id']}",
                },
                context={
                    "project_id": row.issue.project_id,
                    "workspace_id": row.issue.workspace_id,
                    "default_assignee_id": None,
                },
            )
        else:
            child = Issue.issue_objects.get(pk=target, parent=row.issue)
            fields = (
                {"state": str(cancelled.pk)}
                if action == "cancel"
                else {"name": change["task"]["title"], "description_html": task_html(row, change)}
            )
            serializer = IssueSerializer(
                child,
                data=fields,
                partial=True,
                context={"project_id": row.issue.project_id, "workspace_id": row.issue.workspace_id},
            )
        serializer.is_valid(raise_exception=True)
        with impersonate(user):
            child = serializer.save()
        row.children[change["id"]] = str(child.pk)
        audit = {
            "action": action,
            "before": before,
            "after": {
                "id": str(child.pk),
                "name": child.name,
                "description_html": child.description_html,
                "state_id": str(child.state_id),
            },
        }
        applied.append(audit)
        IssueActivity.objects.create(
            issue=child,
            project=child.project,
            workspace=child.workspace,
            actor=user,
            verb="updated",
            field="wbs",
            old_value=json.dumps(before, ensure_ascii=False),
            new_value=json.dumps(audit["after"], ensure_ascii=False),
            comment=f"WBS {row.pk}: {action}",
        )
        if action == "append":
            IssueRelation.objects.create(
                issue=child,
                related_issue_id=target,
                relation_type="relates_to",
                project=child.project,
                workspace=child.workspace,
            )
            IssueActivity.objects.create(
                issue_id=target,
                project=child.project,
                workspace=child.workspace,
                actor=user,
                verb="updated",
                field="wbs",
                comment=f"WBS {row.pk}: linked change {child.pk}",
            )
        if action == "cancel":
            IssueActivity.objects.create(
                issue=child,
                project=child.project,
                workspace=child.workspace,
                actor=user,
                verb="updated",
                field="state",
                old_identifier=before["state_id"],
                new_identifier=child.state_id,
                old_value=before["state_group"],
                new_value="cancelled",
                comment=f"WBS {row.pk}: cancel remaining work",
            )
    # Keep model result and its digest immutable; execution evidence belongs to the decision snapshot.
    row.execution = {"changes": applied, "choices": choices, "replacement_tasks": replacements}
    row.status = "completed"


def review_update(user, row, data):
    if data["decision"] == "approve":
        apply_changes(user, row, data)
    else:
        row.status = "rejected"
    row.decision, row.decision_reason = data["decision"], str(data.get("reason", ""))[:5000]
    row.reviewed_by, row.reviewed_at = user, timezone.now()
    row.save()
    return row
