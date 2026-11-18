# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Fail-closed project repository routing; never discovers or creates repositories."""

from plane.db.models import ProjectRepositoryBinding
from .repository_transport import RepositoryError

ROLES = ("documentation", "prototype")


def repository_identity(row):
    return {
        "repository_id": str(row.pk),
        "instance_id": str(row.instance_id),
        "external_id": row.external_id,
        "path": row.path,
        "provider": row.instance.provider,
        "api_url": row.instance.api_url,
        "web_url": row.instance.web_url.rstrip("/") + "/" + row.path,
        "purpose": row.purpose,
    }


def binding_data(binding):
    result = {"revision": binding.revision if binding else 0}
    for role in ROLES:
        row = getattr(binding, role + "_repository", None) if binding else None
        result[role + "_repository_id"] = str(row.pk) if row else None
        result[role] = repository_identity(row) if row else None
    return result


def resolve_repository(project, role):
    if role not in ROLES:
        raise RepositoryError("invalid_repository_role", 400)
    binding = (
        ProjectRepositoryBinding.objects.filter(project=project)
        .select_related("documentation_repository__instance", "prototype_repository__instance")
        .first()
    )
    row = getattr(binding, role + "_repository", None) if binding else None
    if row is None:
        raise RepositoryError("project_repository_binding_required", 409)
    if row.project_id != project.pk or row.purpose != role:
        raise RepositoryError("project_repository_binding_invalid", 409)
    if not row.enabled or not row.instance.enabled:
        raise RepositoryError("project_repository_binding_unavailable", 409)
    return row, binding.revision
