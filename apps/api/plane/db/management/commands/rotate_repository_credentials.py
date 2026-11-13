# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.core.management.base import BaseCommand, CommandError
from plane.singularity.vault import VaultError, rotate_credentials


class Command(BaseCommand):
    help = "Re-encrypt repository credentials with the current key; retain old keys for backups."

    def handle(self, *args, **options):
        try:
            count = rotate_credentials()
        except VaultError as error:
            raise CommandError(str(error)) from None
        self.stdout.write(f"Rotated {count} repository credentials. No secrets displayed.")
