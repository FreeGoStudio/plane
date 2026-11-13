# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path
from . import api, auth_views
from .company_views import company_account
from .repository_views import repository_settings
from .repository_api import RepositoryInstances, RepositoryCredentials, ProjectRepositories, RepositoryAccess

auth_patterns = [
    path("repository-access/", repository_settings),
    path("workspaces/<slug:slug>/projects/<uuid:project_id>/repositories/", repository_settings),
    path("company-account/", company_account),
    path("authorize/", auth_views.authorize),
    path("token/", auth_views.token),
    path("revoke/", auth_views.revoke),
    path("connections/", auth_views.connections),
    path("personal-tokens/", auth_views.personal_tokens),
    path("exchange/", auth_views.exchange),
]
base = "workspaces/<slug:slug>/projects/<uuid:project_id>/"
urlpatterns = [
    path("repository-hosts/", RepositoryInstances.as_view()),
    path("repository-credentials/", RepositoryCredentials.as_view()),
    path("repository-credentials/<uuid:pk>/", RepositoryCredentials.as_view()),
    path(base + "repositories/", ProjectRepositories.as_view()),
    path(base + "repositories/<uuid:pk>/", ProjectRepositories.as_view()),
    path(base + "repositories/<uuid:pk>/access/", RepositoryAccess.as_view()),
    path(base + "repositories/<uuid:pk>/tree/", RepositoryAccess.as_view(), {"operation": "tree"}),
    path(base + "repositories/<uuid:pk>/file/", RepositoryAccess.as_view(), {"operation": "file"}),
    path("me/", api.Me.as_view()),
    path("projects/", api.Projects.as_view()),
    path(base + "work-items/", api.Items.as_view()),
    path(base + "work-items/<uuid:pk>/", api.Items.as_view()),
    path(base + "capabilities/", api.Capabilities.as_view()),
    path(base + "work-items/<uuid:pk>/capabilities/", api.Capabilities.as_view()),
]
