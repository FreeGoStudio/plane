# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Only protocol endpoints are public; application registration is operator managed."""

from django.urls import path
from oauth2_provider import views
from .oidc import PlaneAuthorizationView, oidc_enabled

app_name = "oauth2_provider"
urlpatterns = [
    path("authorize/", oidc_enabled(PlaneAuthorizationView.as_view()), name="authorize"),
    path("token/", oidc_enabled(views.TokenView.as_view()), name="token"),
    path("revoke_token/", oidc_enabled(views.RevokeTokenView.as_view()), name="revoke-token"),
    path(
        ".well-known/openid-configuration",
        oidc_enabled(views.ConnectDiscoveryInfoView.as_view()),
        name="oidc-connect-discovery-info",
    ),
    path(".well-known/jwks.json", oidc_enabled(views.JwksInfoView.as_view()), name="jwks-info"),
    path("userinfo/", oidc_enabled(views.UserInfoView.as_view()), name="user-info"),
]
