# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Execute persisted document adoption grants without model credentials."""

import time
import logging
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from plane.singularity.requirement_adoption import process_one


class Command(BaseCommand):
    def handle(self, *args, **options):
        while True:
            try:
                process_one()
            except Exception:
                logging.getLogger(__name__).warning("Document adoption reconciliation failed")
            finally:
                close_old_connections()
            time.sleep(10)
