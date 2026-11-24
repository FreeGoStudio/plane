# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import time
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone
from plane.db.models import RepositoryProvisioning, RepositoryRegistration
from plane.singularity.repository_registration import process_registration
from plane.singularity.repository_management import management_instance, GitLabRepositoryManager, process_project


class Command(BaseCommand):
    help = "Dedicated GitLab repository administrator; never mount its secret into API or execution workers."

    def add_arguments(self, parser):
        parser.add_argument("--secret-file", required=True)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            instance, group_id = management_instance()
            client = GitLabRepositoryManager(instance, group_id, Path(options["secret_file"]).read_text().strip())
            for pk in (
                RepositoryRegistration.objects.filter(next_attempt_at__lte=timezone.now())
                .order_by("next_attempt_at")
                .values_list("pk", flat=True)[:100]
            ):
                process_registration(pk, client)
            ids = list(
                RepositoryProvisioning.objects.filter(next_attempt_at__lte=timezone.now())
                .exclude(status="blocked")
                .order_by("next_attempt_at")
                .values_list("project_id", flat=True)[:100]
            )
            for project_id in ids:
                process_project(project_id, client)
            if options["once"]:
                return
            time.sleep(5)
