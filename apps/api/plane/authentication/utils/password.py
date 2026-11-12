# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from functools import lru_cache
from unicodedata import normalize

from django.contrib.auth.password_validation import CommonPasswordValidator
from django.core.exceptions import ValidationError
from zxcvbn.frequency_lists import FREQUENCY_LISTS

PASSWORD_MIN_LENGTH = 15


@lru_cache(maxsize=1)
def password_blocklist():
    """Whole-password local corpus, versioned through uv.lock.

    Combine Django's common-password corpus with zxcvbn's leaked-password list.
    Do not use zxcvbn scoring, substring matching, or its names/word dictionaries.
    """
    return frozenset(CommonPasswordValidator().passwords) | frozenset(FREQUENCY_LISTS["passwords"])


def password_validation_error(password, user=None, email=None):
    if not isinstance(password, str) or len(normalize("NFC", password)) < PASSWORD_MIN_LENGTH:
        return "PASSWORD_TOO_SHORT"
    candidate = normalize("NFC", password).lower()
    context = {"plane"}
    for value in (email, getattr(user, "email", None), getattr(user, "username", None)):
        if value:
            context.add(normalize("NFC", value).lower())
            context.add(normalize("NFC", value.split("@")[0]).lower())
    if candidate in password_blocklist() or candidate in context:
        return "PASSWORD_TOO_WEAK"
    return None


def is_password_strong(password):
    """Compatibility wrapper for callers that only need a boolean."""
    return password_validation_error(password) is None


class PasswordPolicyValidator:
    """Use one policy for Django management commands and auth endpoints."""

    def validate(self, password, user=None):
        error = password_validation_error(password, user=user)
        if error:
            message = (
                "Use at least 15 characters."
                if error == "PASSWORD_TOO_SHORT"
                else "This password is common, compromised, or matches your account. Choose a different passphrase."
            )
            raise ValidationError(message, code=error)

    def get_help_text(self):
        return "Use at least 15 characters and avoid common, compromised, or account-specific passwords."
