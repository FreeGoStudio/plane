# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Manual repository registration and worker-only platform verification."""

from datetime import timedelta
from urllib.parse import quote

from django.db import transaction
from django.conf import settings
from django.utils import timezone
from plane.db.models import ProjectRepository, RepositoryRegistration, RepositoryMemberGrant, ProjectMember
from .repository_add import resolve_address
from .repository_management import project_lock, active_members, sync_grant, ROLE_ACCESS, event
from .repository_provider import safe_path
from .repository_transport import RepositoryError


def serialize(row):
    return {
        "id": str(row.pk),
        "path": row.path,
        "url": row.instance.web_url.rstrip("/") + "/" + quote(row.path, safe="/"),
        "instance_id": str(row.instance_id),
        "purpose": row.repository.purpose if row.repository_id else row.purpose,
        "status": row.status,
        "error_code": row.error_code,
        "repository_id": str(row.repository_id) if row.repository_id else None,
    }


def registrations(project):
    return [
        serialize(row)
        for row in RepositoryRegistration.objects.filter(project=project).select_related("repository", "instance")
    ]


def register(project, actor, address, purpose, instance_id=None):
    instance, path = resolve_address(address, instance_id)
    if len(path) > 512:
        raise RepositoryError("invalid_repository_url", 400)
    with transaction.atomic():
        row, created = RepositoryRegistration.objects.get_or_create(
            project=project,
            instance=instance,
            path=path,
            defaults={"purpose": purpose, "requested_by": actor},
        )
        row = RepositoryRegistration.objects.select_for_update(of=("self",)).select_related("repository").get(pk=row.pk)
        if not created and row.status not in ("ready", "pending", "syncing", "disabled"):
            row.status, row.error_code, row.next_attempt_at = "pending", "", timezone.now()
            row.requested_by = actor
            row.save()
        if (
            not settings.SINGULARITY_REPOSITORY_PROVISIONING_ENABLED
            or str(instance.pk) != settings.SINGULARITY_REPOSITORY_MANAGEMENT_INSTANCE_ID
        ):
            row.status, row.error_code = "waiting_access", "repository_management_not_configured"
            row.save()
        if created:
            event(project, "repository_registration_requested", {"registration_id": str(row.pk)}, actor)
    return serialize(row)


def process_registration(pk, client):
    """Never initializes a repository or borrows a member's credentials."""
    row = RepositoryRegistration.objects.select_related("project", "instance", "repository").get(pk=pk)
    try:
        with project_lock(row.project_id):
            row.refresh_from_db()
            before = (row.status, row.error_code, row.repository_id)
            try:
                if row.instance_id != client.instance.pk or not row.instance.enabled:
                    raise RepositoryError("repository_management_not_configured", 409)
                if (
                    not row.repository_id
                    and not ProjectMember.objects.filter(
                        project=row.project, member=row.requested_by, role=20, is_active=True, member__is_active=True
                    ).exists()
                ):
                    raise RepositoryError("project_administrator_pending", 409)
                identifier = row.repository.external_id if row.repository_id else row.path
                remote = client.call("GET", "/projects/" + quote(identifier, safe=""))
                if not isinstance(remote, dict) or not isinstance(remote.get("id"), int):
                    raise RepositoryError("invalid_upstream_response", 502)
                path = safe_path(remote.get("path_with_namespace"), False)
                if row.repository_id and str(remote["id"]) != row.repository.external_id:
                    raise RepositoryError("repository_identity_changed", 409)
                with transaction.atomic():
                    repository, _ = ProjectRepository.objects.get_or_create(
                        project=row.project,
                        instance=row.instance,
                        external_id=str(remote["id"]),
                        defaults={
                            "path": path,
                            "default_branch": remote.get("default_branch") or "",
                            "purpose": row.purpose,
                        },
                    )
                    row.repository, row.status, row.error_code = repository, "syncing", ""
                    row.save()
                # Keep external grants intact, including inherited access and manual changes.
                members = (
                    {member.member_id: member for member in active_members(row.project)}
                    if repository.enabled and repository.purpose != "reference"
                    else {}
                )
                for member in members.values():
                    RepositoryMemberGrant.objects.get_or_create(repository=repository, user=member.member)
                errors = []
                for grant in RepositoryMemberGrant.objects.filter(repository=repository).select_related(
                    "repository__instance", "user"
                ):
                    previous_grant = (grant.status, grant.applied_access, grant.effective_access)
                    member = members.get(grant.user_id)
                    desired = (
                        (
                            grant.access_override
                            if grant.access_override is not None
                            else ROLE_ACCESS.get(member.role, 0)
                        )
                        if member
                        else 0
                    )
                    try:
                        sync_grant(grant, client, desired)
                    except RepositoryError as error:
                        grant.status, grant.error_code = "error", error.code
                        grant.save()
                    if grant.status in ("error", "conflict", "waiting_identity"):
                        errors.append(grant.error_code)
                    if previous_grant != (grant.status, grant.applied_access, grant.effective_access):
                        event(
                            row.project,
                            "repository_member_reconciled",
                            {
                                "repository_id": str(repository.pk),
                                "user_id": str(grant.user_id),
                                "desired": desired,
                                "status": grant.status,
                                "error_code": grant.error_code,
                            },
                        )
                row.status, row.error_code = (
                    ("sync_error", errors[0]) if errors else ("ready" if repository.enabled else "disabled", "")
                )
            except RepositoryError as error:
                row.status, row.error_code = "waiting_access", error.code
            row.next_attempt_at = timezone.now() + timedelta(seconds=60)
            row.save()
            if before != (row.status, row.error_code, row.repository_id):
                event(
                    row.project,
                    "repository_registration_updated",
                    {
                        "registration_id": str(row.pk),
                        "status": row.status,
                        "error_code": row.error_code,
                    },
                )
    except RepositoryError as error:
        if error.code != "repository_management_busy":
            raise
