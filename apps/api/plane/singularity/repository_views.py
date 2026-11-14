# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_GET
from plane.db.models import ProjectMember
from plane.license.models import InstanceAdmin
from .api import visible_projects


@require_GET
def repository_settings(request, slug=None, project_id=None):
    if not settings.SINGULARITY_REPOSITORIES_ENABLED:
        raise Http404
    if not request.user.is_authenticated or not request.user.is_active or request.user.is_bot:
        return render(request, "singularity/login.html", {"return_url": request.path}, status=401)
    projects = visible_projects(request.user).select_related("workspace").order_by("name")
    project = get_object_or_404(projects, pk=project_id, workspace__slug=slug) if project_id else None
    if project:
        from .repository_oauth import project_url
        from types import SimpleNamespace

        return redirect(project_url(SimpleNamespace(project=project, project_id=project.pk, pk="")))
    admin = bool(
        project and ProjectMember.objects.filter(project=project, member=request.user, is_active=True, role=20).exists()
    )
    config = {
        "project_url": f"/api/singularity/v1/workspaces/{slug}/projects/{project_id}/repositories/"
        if project
        else None,
        "project_admin": admin,
    }
    response = render(
        request,
        "singularity/repositories.html",
        {
            "project": project,
            "projects": projects,
            "config": config,
            "project_admin": admin,
            "platform_admin": InstanceAdmin.objects.filter(user=request.user, role__gte=15).exists(),
        },
    )
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response
