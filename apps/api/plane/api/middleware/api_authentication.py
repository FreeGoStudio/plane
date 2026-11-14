# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports

# Third party imports
from rest_framework import authentication

# Module imports
from plane.utils.personal_tokens import authenticate_personal_token


class APIKeyAuthentication(authentication.BaseAuthentication):
    """
    Authentication with an API Key
    """

    www_authenticate_realm = "api"
    media_type = "application/json"
    auth_header_name = "X-Api-Key"

    def get_api_token(self, request):
        return request.headers.get(self.auth_header_name)

    def validate_api_token(self, token):
        api_token = authenticate_personal_token(token)
        return api_token.user, api_token.token

    def authenticate(self, request):
        token = self.get_api_token(request=request)
        if token:
            source = authenticate_personal_token(token)
            request.plane_credential_id = str(source.pk)
            return source.user, source.token
        if request.headers.get("Authorization", "").startswith("Bearer "):
            from plane.singularity.authentication import DelegatedAuthentication
            from plane.singularity.operations import check_operation_scope

            user, delegated = DelegatedAuthentication().authenticate(request)
            request.delegation_audit_grant = delegated.grant
            check_operation_scope(request, delegated)
            request.plane_credential_id = str(delegated.grant.source_api_token or delegated.grant_id)
            return user, delegated
        return None
