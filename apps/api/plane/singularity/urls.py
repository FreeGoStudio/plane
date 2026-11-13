# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path
from . import api, auth_views

auth_patterns = [
    path("authorize/", auth_views.authorize),
    path("token/", auth_views.token),
    path("revoke/", auth_views.revoke),
    path("connections/", auth_views.connections),
    path("personal-tokens/", auth_views.personal_tokens),
    path("exchange/", auth_views.exchange),
]
base = "workspaces/<slug:slug>/projects/<uuid:project_id>/"
urlpatterns = [
    path("me/", api.Me.as_view()),
    path("projects/", api.Projects.as_view()),
    path(base + "work-items/", api.Items.as_view()),
    path(base + "work-items/<uuid:pk>/", api.Items.as_view()),
    path(base + "capabilities/", api.Capabilities.as_view()),
    path(base + "work-items/<uuid:pk>/capabilities/", api.Capabilities.as_view()),
]
