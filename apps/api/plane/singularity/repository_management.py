# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Durable, group-scoped GitLab administration. Credentials exist only in the worker."""

import hashlib
from functools import wraps
from contextlib import contextmanager
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from plane.db.models import (
    CompanyAccount,
    Project,
    ProjectMember,
    WorkspaceMember,
    RepositoryIdentity,
    RepositoryInstance,
    ProjectRepository,
    ProjectRepositoryBinding,
    ProjectRepositoryBindingRevision,
    RepositoryProvisioning,
    RepositoryMemberGrant,
    RepositoryManagementEvent,
)
from .repository_bindings import ROLES, binding_data
from .repository_transport import RepositoryError, RepositoryTransport

ROLE_ACCESS = {20: 40, 15: 30, 5: 20}


def event(project, operation, details, actor=None):
    RepositoryManagementEvent.objects.create(project=project, actor=actor, operation=operation, details=details)


@contextmanager
def project_lock(project_id):
    key = int.from_bytes(
        hashlib.sha256(f"repository-management:{project_id}".encode()).digest()[:8], "big", signed=True
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [key])
        acquired = cursor.fetchone()[0]
    if not acquired:
        raise RepositoryError("repository_management_busy", 409)
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [key])


def serialized_project_operation(fn):
    @wraps(fn)
    def wrapped(self, request, slug, project_id, *args, **kwargs):
        with project_lock(project_id):
            return fn(self, request, slug, project_id, *args, **kwargs)

    return wrapped


def management_instance():
    if not settings.SINGULARITY_REPOSITORY_PROVISIONING_ENABLED:
        raise RepositoryError("repository_management_disabled", 409)
    instance_id = settings.SINGULARITY_REPOSITORY_MANAGEMENT_INSTANCE_ID
    group_id = settings.SINGULARITY_REPOSITORY_MANAGEMENT_GROUP_ID
    if not instance_id or not group_id.isdigit():
        raise RepositoryError("repository_management_not_configured", 409)
    try:
        instance = RepositoryInstance.objects.get(pk=instance_id, enabled=True, provider="gitlab")
    except (RepositoryInstance.DoesNotExist, ValueError):
        raise RepositoryError("repository_management_not_configured", 409) from None
    return instance, group_id


class GitLabRepositoryManager:
    def __init__(self, instance, group_id, token):
        if not token:
            raise RepositoryError("repository_management_credential_missing", 409)
        self.instance, self.group_id = instance, str(group_id)
        self.http = RepositoryTransport(instance, token)

    def call(self, method, path, body=None, params=None):
        return self.http.request(
            method, path, body=body, params=params, json_body=True, success_statuses=(200, 201, 204)
        )

    def optional(self, path):
        try:
            return self.call("GET", path)
        except RepositoryError as error:
            if error.status == 404:
                return None
            raise

    def group(self):
        group = self.call("GET", f"/groups/{quote(self.group_id, safe='')}")
        if str(group.get("id")) != self.group_id or not group.get("full_path"):
            raise RepositoryError("repository_management_group_invalid", 409)
        # Project membership does not grant group membership. Check each execution
        # identity against the group's creation threshold before granting access.
        thresholds = {"maintainer": 40, "owner": 50, "administrator": 60}
        if group.get("project_creation_level") not in thresholds:
            raise RepositoryError("group_project_creation_not_restricted", 409)
        self.creation_threshold = thresholds[group["project_creation_level"]]
        return group

    def repository(self, external_id):
        remote = self.call("GET", "/projects/" + quote(str(external_id), safe=""))
        if str(remote.get("namespace", {}).get("id")) != self.group_id:
            raise RepositoryError("repository_outside_managed_group", 409)
        return remote

    def protect(self, remote):
        root = f"/projects/{remote['id']}/protected_branches"
        current = self.optional(root + "/main")
        if current:
            self.call(
                "PATCH",
                root + "/main",
                {
                    "allowed_to_push": [
                        {"id": x["id"], "_destroy": True} for x in current.get("push_access_levels", [])
                    ]
                    + [{"access_level": 0}],
                    "allowed_to_merge": [
                        {"id": x["id"], "_destroy": True} for x in current.get("merge_access_levels", [])
                    ]
                    + [{"access_level": 40}],
                },
            )
        else:
            self.call("POST", root, {"name": "main", "push_access_level": 0, "merge_access_level": 40})
        verified = self.call("GET", root + "/main")
        # GitLab CE accepts PATCH but ignores access-level arrays. This method
        # only runs on operation-owned repositories before binding/grant sync.
        # Never recreate protection after an external direct member was added.
        if current and (
            any(x.get("access_level") != 0 for x in verified.get("push_access_levels", []))
            or any(x.get("access_level") != 40 for x in verified.get("merge_access_levels", []))
        ):
            if self.call("GET", f"/projects/{remote['id']}/members", params={"per_page": 1}):
                raise RepositoryError("repository_protection_requires_manual_review", 409)
            self.call("DELETE", root + "/main")
            self.call("POST", root, {"name": "main", "push_access_level": 0, "merge_access_level": 40})
            verified = self.call("GET", root + "/main")
        if not verified.get("push_access_levels") or any(
            x.get("access_level") != 0 for x in verified["push_access_levels"]
        ):
            raise RepositoryError("repository_protection_not_confirmed", 409)
        if not verified.get("merge_access_levels") or any(
            x.get("access_level") != 40 for x in verified["merge_access_levels"]
        ):
            raise RepositoryError("repository_protection_not_confirmed", 409)


def request_provisioning(project, actor=None):
    management_instance()
    with transaction.atomic():
        Project.objects.select_for_update().get(pk=project.pk)
        row, _ = RepositoryProvisioning.objects.get_or_create(project=project, defaults={"requested_by": actor})
        row.status, row.error_code, row.next_attempt_at = "pending", "", timezone.now()
        if actor:
            row.requested_by = actor
        row.save()
        event(project, "initialization_requested", {"operation_id": str(row.operation_id)}, actor)
    return row


def provision_slots(row, client):
    group = client.group()
    if row.instance_id and (row.instance_id != client.instance.pk or row.group_id != client.group_id):
        raise RepositoryError("repository_management_configuration_changed", 409)
    if row.instance_id is None:
        row.instance, row.group_id = client.instance, client.group_id
        row.save()
    project = row.project
    actor = (
        row.requested_by
        or project.created_by
        or (
            ProjectMember.objects.filter(project=project, role=20, is_active=True, member__is_active=True)
            .select_related("member")
            .first()
        )
    )
    if isinstance(actor, ProjectMember):
        actor = actor.member
    if actor is None:
        raise RepositoryError("project_administrator_pending", 409)
    for role in ROLES:
        binding, _ = ProjectRepositoryBinding.objects.get_or_create(project=project)
        if getattr(binding, role + "_repository_id"):
            continue  # A manual binding is authoritative; never replace it on retry.
        revision = binding.revision
        slot = row.slots.get(role)
        if not slot:
            slot = {"path": f"plane-{project.pk.hex}-{role}", "marker": f"plane:{project.pk}:{row.operation_id}:{role}"}
            row.slots = {**row.slots, role: slot}
            row.save()  # Durable ownership marker before any upstream side effect.
        full_path = group["full_path"] + "/" + slot["path"]
        remote = (
            client.repository(slot["external_id"])
            if slot.get("external_id")
            else client.optional("/projects/" + quote(full_path, safe=""))
        )
        if remote is None:
            remote = client.call(
                "POST",
                "/projects",
                {
                    "name": f"{project.name[:180]} - {'Project documents' if role == 'documentation' else 'Storybook'}",
                    "path": slot["path"],
                    "namespace_id": client.group_id,
                    "visibility": "private",
                    "description": slot["marker"],
                    "initialize_with_readme": True,
                    "default_branch": "main",
                    "merge_method": "ff",
                    "squash_option": "never",
                },
            )
        if remote.get("description") != slot["marker"] or str(remote.get("namespace", {}).get("id")) != client.group_id:
            raise RepositoryError("repository_initialization_ownership_conflict", 409)
        slot = {**slot, "external_id": str(remote["id"])}
        row.slots = {**row.slots, role: slot}
        row.save()
        client.protect(remote)
        with transaction.atomic():
            Project.objects.select_for_update().get(pk=project.pk)
            binding.refresh_from_db()
            if binding.revision != revision or getattr(binding, role + "_repository_id"):
                raise RepositoryError("repository_binding_changed_during_initialization", 409)
            repository, _ = ProjectRepository.objects.get_or_create(
                project=project,
                instance=client.instance,
                external_id=str(remote["id"]),
                defaults={
                    "path": remote["path_with_namespace"],
                    "default_branch": remote.get("default_branch") or "main",
                    "purpose": role,
                },
            )
            if repository.purpose != role or not repository.enabled:
                raise RepositoryError("repository_initialization_mapping_conflict", 409)
            setattr(binding, role + "_repository", repository)
            binding.revision += 1
            binding.save()
            ProjectRepositoryBindingRevision.objects.create(
                project=project, revision=binding.revision, snapshot=binding_data(binding), changed_by=actor
            )
            event(
                project,
                "repository_created_and_bound",
                {"role": role, "repository_id": str(repository.pk), "external_id": repository.external_id},
                actor,
            )


def external_user(user, instance):
    identity = RepositoryIdentity.objects.filter(owner=user, instance=instance).first()
    if identity:
        return identity.external_id
    account = CompanyAccount.objects.filter(user=user, status="linked", external_id__isnull=False).first()
    if account and instance.api_url.rstrip("/") == account.instance_url.rstrip("/") + "/api/v4":
        return str(account.external_id)
    return None  # Never infer identity from name/email or a borrowed credential.


def active_members(project):
    return ProjectMember.objects.filter(
        project=project,
        is_active=True,
        member__is_active=True,
        member_id__in=WorkspaceMember.objects.filter(workspace=project.workspace, is_active=True).values("member_id"),
    ).select_related("member")


def sync_grant(grant, client, desired):
    repository = grant.repository
    client.repository(repository.external_id)  # Fixed group boundary before permission writes.
    identity = external_user(grant.user, repository.instance)
    if not grant.external_user_id:
        if not identity:
            grant.status, grant.error_code = "waiting_identity", "verified_gitlab_identity_required"
            grant.save()
            return
        grant.external_user_id = identity
    elif desired and identity != grant.external_user_id:
        raise RepositoryError("repository_member_identity_changed", 409)
    root = f"/projects/{quote(repository.external_id, safe='')}/members"
    suffix = quote(grant.external_user_id, safe="")
    if desired:
        group_member = client.optional(f"/groups/{client.group_id}/members/all/{suffix}")
        if group_member and int(group_member.get("access_level", 0)) >= client.creation_threshold:
            raise RepositoryError("execution_identity_has_group_creation_rights", 409)
    direct = client.optional(root + "/" + suffix)
    effective = client.optional(root + "/all/" + suffix)
    if grant.adopt_requested:
        if direct is None or int(direct["access_level"]) != grant.direct_access:
            raise RepositoryError("external_permission_changed_before_adoption", 409)
        grant.managed, grant.applied_access, grant.adopt_requested = True, grant.direct_access, False
    grant.desired_access = desired
    grant.direct_access = int(direct["access_level"]) if direct else None
    grant.effective_access = int((effective or {}).get("access_level", 0))
    if not grant.managed and direct:
        grant.status, grant.error_code = "unmanaged", "external_direct_grant_preserved"
    elif grant.managed and direct and int(direct["access_level"]) != grant.applied_access:
        grant.status, grant.error_code = "conflict", "external_permission_change_preserved"
    elif desired == 0:
        if grant.managed and direct:
            client.call("DELETE", root + "/" + suffix)
        grant.managed, grant.create_requested, grant.applied_access = False, False, None
        grant.direct_access = None
        effective = client.optional(root + "/all/" + suffix)
        grant.effective_access = int((effective or {}).get("access_level", 0))
        grant.status, grant.error_code = ("inherited", "inherited_access_remains") if effective else ("removed", "")
    elif not direct and grant.effective_access >= desired:
        grant.status, grant.error_code = "inherited", "external_inherited_grant_preserved"
    else:
        if not direct:
            grant.create_requested = True
            grant.save()
            client.call("POST", root, {"user_id": grant.external_user_id, "access_level": desired})
        elif grant.applied_access != desired:
            client.call("PUT", root + "/" + suffix, {"access_level": desired})
        verified = client.optional(root + "/" + suffix)
        if not verified or int(verified["access_level"]) != desired:
            raise RepositoryError("repository_permission_not_confirmed", 409)
        grant.managed, grant.applied_access = True, desired
        grant.direct_access = desired
        grant.effective_access = max(desired, grant.effective_access)
        grant.status, grant.error_code = "synced", ""
    grant.save()


def sync_members(row, client):
    project = row.project
    binding = ProjectRepositoryBinding.objects.filter(project=project).first()
    ids = [getattr(binding, role + "_repository_id", None) for role in ROLES] if binding else []
    repositories = ProjectRepository.objects.filter(project=project, enabled=True).filter(
        Q(pk__in=ids) | Q(purpose="development")
    )
    members = {member.member_id: member for member in active_members(project)}
    for repository in repositories:
        for member in members.values():
            RepositoryMemberGrant.objects.get_or_create(repository=repository, user=member.member)
    target_ids = set(repositories.values_list("pk", flat=True))
    grants = RepositoryMemberGrant.objects.filter(repository__project=project).select_related(
        "repository__instance", "user"
    )
    for grant in grants:
        if grant.repository.instance_id != client.instance.pk:
            RepositoryMemberGrant.objects.filter(pk=grant.pk).update(
                status="unmanaged", error_code="repository_outside_managed_instance"
            )
            continue
        member = members.get(grant.user_id)
        desired = (
            (grant.access_override if grant.access_override is not None else ROLE_ACCESS.get(member.role, 0))
            if member and grant.repository_id in target_ids
            else 0
        )
        before = (grant.status, grant.applied_access, grant.effective_access)
        try:
            sync_grant(grant, client, desired)
        except RepositoryError as error:
            grant.status, grant.error_code = "error", error.code
            grant.save()
        if before != (grant.status, grant.applied_access, grant.effective_access):
            event(
                project,
                "repository_member_reconciled",
                {
                    "repository_id": str(grant.repository_id),
                    "user_id": str(grant.user_id),
                    "desired": desired,
                    "applied": grant.applied_access,
                    "status": grant.status,
                    "error_code": grant.error_code,
                },
            )


def process_project(project_id, client):
    try:
        with project_lock(project_id):
            row = RepositoryProvisioning.objects.select_related("project__created_by").get(project_id=project_id)
            row.status, row.error_code = "processing", ""
            row.attempts += 1
            row.next_attempt_at = timezone.now() + timedelta(minutes=2)
            row.save()
            try:
                provision_slots(row, client)
                sync_members(row, client)
                row.status, row.error_code = "ready", ""
            except RepositoryError as error:
                row.status = (
                    "blocked" if error.status == 409 and error.code != "project_administrator_pending" else "retry"
                )
                row.error_code = error.code
                event(row.project, "repository_initialization_retry", {"error_code": error.code})
            row.next_attempt_at = timezone.now() + timedelta(seconds=30 if row.status == "ready" else 60)
            row.save()
    except RepositoryError as error:
        if error.code != "repository_management_busy":
            raise
