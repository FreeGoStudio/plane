# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Dedicated process: only this process receives the company admin credential."""

import time
from contextlib import nullcontext
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone
from plane.db.models import CompanyAccount
from plane.singularity.company import CompanyError, GitLabCompanyClient, process_account
from plane.singularity.vault import VaultError


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--secret-file", required=True)
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--credential-state-dir")

    def handle(self, *args, **options):
        if not settings.SINGULARITY_COMPANY_ENABLED:
            raise CommandError("Company provisioning is disabled")
        if options["credential_state_dir"]:
            from plane.singularity.company_admin import AdminCredentialStore

            store = AdminCredentialStore(options["credential_state_dir"], options["secret_file"])
            client_context = store.client
        else:
            client = GitLabCompanyClient(Path(options["secret_file"]).read_text().strip())

            def client_context():
                return nullcontext(client)

        while True:
            close_old_connections()
            try:
                with client_context() as client:
                    rows = CompanyAccount.objects.filter(next_attempt_at__lte=timezone.now()).filter(
                        Q(status__in=["pending", "processing", "retry"])
                        | Q(user__is_active=False) & ~Q(status__in=["blocked", "disconnected"])
                    )
                    for user_id in list(rows.order_by("next_attempt_at").values_list("user_id", flat=True)[:100]):
                        process_account(user_id, client)
                    from plane.singularity.repository_managed import maintain_connections

                    maintain_connections(client)
            except (CompanyError, VaultError, OSError, ValueError, KeyError, TypeError):
                # Never emit upstream response bodies, state or credential values.
                self.stderr.write("Company administrator credential maintenance failed; retrying")
                if options["once"]:
                    raise CommandError("Company credential maintenance failed") from None
                time.sleep(25)
            if options["once"]:
                return
            time.sleep(5)
