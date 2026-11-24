# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import logging

# Django imports
from django.conf import settings
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

# Third party imports
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

## Module imports
from plane.app.serializers import UserSerializer
from plane.authentication.utils.login import user_login
from plane.authentication.utils.password import password_validation_error
from plane.db.models import User
from plane.authentication.adapter.error import (
    AuthenticationException,
    AUTHENTICATION_ERROR_CODES,
)
from django.middleware.csrf import get_token
from plane.utils.cache import invalidate_cache
from plane.authentication.utils.host import base_host
from plane.authentication.rate_limit import AuthenticationThrottle


logger = logging.getLogger("plane.authentication")


@method_decorator(never_cache, name="dispatch")
class CSRFTokenEndpoint(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        # Generate a CSRF token
        csrf_token = get_token(request)
        # Return the CSRF token in a JSON response
        return Response({"csrf_token": str(csrf_token)}, status=status.HTTP_200_OK)


def csrf_failure(request, reason=""):
    """Custom CSRF failure view"""
    # Django's Origin/Referer reasons contain untrusted URLs. Never log those
    # values, query strings, credentials or token contents.
    if reason.startswith("Origin checking failed"):
        safe_reason = "origin_not_trusted"
    elif reason.startswith("Referer checking failed"):
        safe_reason = "referer_missing" if "no Referer" in reason else "referer_invalid"
    elif reason == "CSRF cookie not set.":
        safe_reason = "csrf_cookie_missing"
    elif reason == "CSRF token missing.":
        safe_reason = "csrf_token_missing"
    elif reason.startswith("CSRF token from") and reason.endswith("incorrect."):
        safe_reason = "csrf_token_mismatch"
    elif reason.startswith("CSRF cookie"):
        safe_reason = "csrf_cookie_malformed"
    elif reason.startswith("CSRF token from"):
        safe_reason = "csrf_token_malformed"
    else:
        safe_reason = "csrf_rejected"
    logger.warning(
        "CSRF verification failed",
        extra={
            "csrf_reason": safe_reason,
            "view_name": getattr(request.resolver_match, "view_name", None),
            "method": request.method,
            "is_secure": request.is_secure(),
            "csrf_cookie_present": settings.CSRF_COOKIE_NAME in request.COOKIES,
            "origin_present": "HTTP_ORIGIN" in request.META,
            "referer_present": "HTTP_REFERER" in request.META,
        },
    )
    return render(
        request,
        "csrf_failure.html",
        {"reason": reason, "root_url": base_host(request=request)},
    )


class ChangePasswordEndpoint(APIView):
    throttle_classes = [AuthenticationThrottle]

    def post(self, request):
        user = User.objects.get(pk=request.user.id)

        # If the user password is not autoset then we need to check the old passwords
        if not user.is_password_autoset:
            old_password = request.data.get("old_password", False)
            if not old_password:
                exc = AuthenticationException(
                    error_code=AUTHENTICATION_ERROR_CODES["MISSING_PASSWORD"],
                    error_message="MISSING_PASSWORD",
                    payload={"error": "Old password is missing"},
                )
                return Response(exc.get_error_dict(), status=status.HTTP_400_BAD_REQUEST)

        # Get the new password
        new_password = request.data.get("new_password", False)

        if not new_password:
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["MISSING_PASSWORD"],
                error_message="MISSING_PASSWORD",
                payload={"error": "Old or new password is missing"},
            )
            return Response(exc.get_error_dict(), status=status.HTTP_400_BAD_REQUEST)

        # If the user password is not autoset then we need to check the old passwords
        if not user.is_password_autoset and not user.check_password(old_password):
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["INCORRECT_OLD_PASSWORD"],
                error_message="INCORRECT_OLD_PASSWORD",
                payload={"error": "Old password is not correct"},
            )
            return Response(exc.get_error_dict(), status=status.HTTP_400_BAD_REQUEST)

        # Check length and the whole-password blocklist
        if password_error := password_validation_error(new_password, user=user):
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES[password_error],
                error_message=password_error,
            )
            return Response(exc.get_error_dict(), status=status.HTTP_400_BAD_REQUEST)

        # set_password also hashes the password that the user will get
        user.set_password(new_password)
        user.is_password_autoset = False
        user.save()
        user_login(user=user, request=request, is_app=True)
        return Response({"message": "Password updated successfully"}, status=status.HTTP_200_OK)


class SetUserPasswordEndpoint(APIView):
    @invalidate_cache("/api/users/me/")
    def post(self, request):
        user = User.objects.get(pk=request.user.id)
        password = request.data.get("password", False)

        # If the user password is not autoset then return error
        if not user.is_password_autoset:
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["PASSWORD_ALREADY_SET"],
                error_message="PASSWORD_ALREADY_SET",
                payload={"error": "Your password is already set please change your password from profile"},
            )
            return Response(exc.get_error_dict(), status=status.HTTP_400_BAD_REQUEST)

        # Check password validation
        if not password:
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["INVALID_PASSWORD"],
                error_message="INVALID_PASSWORD",
            )
            return Response(exc.get_error_dict(), status=status.HTTP_400_BAD_REQUEST)

        if password_error := password_validation_error(password, user=user):
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES[password_error],
                error_message=password_error,
            )
            return Response(exc.get_error_dict(), status=status.HTTP_400_BAD_REQUEST)

        # Set the user password
        user.set_password(password)
        user.is_password_autoset = False
        user.save()
        # Login the user as the session is invalidated
        user_login(user=user, request=request, is_app=True)
        # Return the user
        serializer = UserSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)
