# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.conf import settings

# Third party imports
from rest_framework.throttling import SimpleRateThrottle


class ApiKeyRateThrottle(SimpleRateThrottle):
    scope = "api_key"

    def get_rate(self):
        return settings.API_KEY_RATE_LIMIT

    def get_cache_key(self, request, view):
        """Count one business request against its stable originating credential."""
        identity = getattr(request, "plane_credential_id", None)
        grant = getattr(getattr(request, "auth", None), "grant", None)
        if grant:
            identity = str(grant.source_api_token or grant.pk)
        if identity:
            return f"{self.scope}:{identity}"
        raw = request.headers.get("X-Api-Key")
        if raw:
            from plane.utils.personal_tokens import authenticate_personal_token

            return f"{self.scope}:{authenticate_personal_token(raw).pk}"
        if request.user.is_authenticated:
            return f"{self.scope}:user:{request.user.pk}"
        return None

    def allow_request(self, request, view):
        allowed = super().allow_request(request, view)

        if allowed and self.key is not None:
            now = self.timer()
            # Calculate the remaining limit and reset time
            history = self.cache.get(self.key, [])

            # Remove old histories
            while history and history[-1] <= now - self.duration:
                history.pop()

            # Calculate the requests
            num_requests = len(history)

            # Check available requests
            available = self.num_requests - num_requests

            # Unix timestamp for when the rate limit will reset
            reset_time = int(now + self.duration)

            # Add headers
            request.META["X-RateLimit-Remaining"] = max(0, available)
            request.META["X-RateLimit-Reset"] = reset_time

        return allowed
