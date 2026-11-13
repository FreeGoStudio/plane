# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Dedicated process: only this process receives the company admin credential."""

import time
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone
from plane.db.models import CompanyAccount
from plane.singularity.company import GitLabCompanyClient, process_account


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--secret-file", required=True)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        if not settings.SINGULARITY_COMPANY_ENABLED:
            raise CommandError("Company provisioning is disabled")
        client = GitLabCompanyClient(Path(options["secret_file"]).read_text().strip())
        while True:
            close_old_connections()
            rows = CompanyAccount.objects.filter(next_attempt_at__lte=timezone.now()).filter(
                Q(status__in=["pending", "processing", "retry"])
                | Q(user__is_active=False) & ~Q(status__in=["blocked", "disconnected"])
            )
            for user_id in list(rows.order_by("next_attempt_at").values_list("user_id", flat=True)[:100]):
                process_account(user_id, client)
            if options["once"]:
                return
            time.sleep(5)
