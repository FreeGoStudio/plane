# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from unicodedata import normalize

from django.contrib.auth.hashers import PBKDF2PasswordHasher


class NFCPasswordHasher(PBKDF2PasswordHasher):
    # Keep legacy hashes exact; Django upgrades them after successful login.
    algorithm = "pbkdf2_sha256_nfc"

    def encode(self, password, salt, iterations=None):
        return super().encode(normalize("NFC", password), salt, iterations)
