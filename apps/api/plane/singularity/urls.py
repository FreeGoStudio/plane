# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path
from . import api, auth_views
from .wbs import WbsAPI
from .requirement_review_api import RequirementReviewAPI, RequirementPushWebhook, RequirementAdoptionGate
from .company_views import company_account
from .repository_views import repository_settings
from .repository_api import RepositoryInstances, RepositoryCredentials, ProjectRepositories, RepositoryAccess
from .repository_api import ProjectRepositoryConnections, DelegatedRepositoryRead
from .repository_api import ProjectRepositoryBindings, BoundRepositoryRead, DelegatedBoundRepositoryRead
from .repository_oauth import callback as repository_callback
from .repository_add import AddRepository
from .repository_oauth_setup import RepositoryOAuthSetup
from .repository_management_api import RepositoryManagement, RepositoryMembers

auth_patterns = [
    path("repository-callback/", repository_callback),
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
    path("requirement-review/push/<uuid:repository_id>/", RequirementPushWebhook.as_view()),
    path("requirement-review/adoption-gate/", RequirementAdoptionGate.as_view()),
    path(base + "work-items/<uuid:pk>/requirement-review/", RequirementReviewAPI.as_view()),
    path(base + "work-items/<uuid:pk>/requirement-review/configure/", RequirementReviewAPI.as_view(), {"action": "configure"}),
    path(base + "work-items/<uuid:pk>/requirement-review/<uuid:run_id>/", RequirementReviewAPI.as_view()),
    path(base + "work-items/<uuid:pk>/requirement-review/<uuid:run_id>/<str:action>/", RequirementReviewAPI.as_view()),
    path(base + "work-items/<uuid:pk>/wbs/", WbsAPI.as_view()),
    path(base + "work-items/<uuid:pk>/wbs/<uuid:run_id>/", WbsAPI.as_view()),
    path(base + "repository-add/", AddRepository.as_view()),
    path(base + "repository-connections/", ProjectRepositoryConnections.as_view()),
    path(base + "repositories/<uuid:pk>/connection/", ProjectRepositoryConnections.as_view()),
    path(base + "ai-repositories/", DelegatedRepositoryRead.as_view()),
    path(base + "repository-bindings/", ProjectRepositoryBindings.as_view()),
    path(base + "repository-management/", RepositoryManagement.as_view()),
    path(base + "repositories/<uuid:pk>/members/", RepositoryMembers.as_view()),
    path(base + "repositories/<uuid:pk>/members/<uuid:user_id>/", RepositoryMembers.as_view()),
    path(base + "bound-repositories/<str:role>/", BoundRepositoryRead.as_view()),
    path(base + "bound-repositories/<str:role>/<str:operation>/", BoundRepositoryRead.as_view()),
    path(base + "ai-bound-repositories/<str:role>/", DelegatedBoundRepositoryRead.as_view()),
    path(base + "ai-bound-repositories/<str:role>/<str:operation>/", DelegatedBoundRepositoryRead.as_view()),
    path(base + "ai-repositories/<uuid:pk>/tree/", DelegatedRepositoryRead.as_view(), {"operation": "tree"}),
    path(base + "ai-repositories/<uuid:pk>/file/", DelegatedRepositoryRead.as_view(), {"operation": "file"}),
    path("repository-oauth-setup/", RepositoryOAuthSetup.as_view()),
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
    path(base + "work-items/prepare/", api.DiscussionPrepare.as_view()),
    path(base + "work-items/<uuid:pk>/prepare/", api.DiscussionPrepare.as_view()),
    path(base + "work-items/<uuid:pk>/", api.Items.as_view()),
    path(base + "capabilities/", api.Capabilities.as_view()),
    path(base + "work-items/<uuid:pk>/capabilities/", api.Capabilities.as_view()),
]
