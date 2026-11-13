# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Register one confidential SSO client without printing its secret."""

from pathlib import Path
from urllib.parse import urlsplit

from django.core.management.base import BaseCommand, CommandError
from oauth2_provider.models import get_application_model


class Command(BaseCommand):
    help = "Register a company GitLab OIDC client; existing clients are never overwritten."

    def add_arguments(self, parser):
        parser.add_argument("--client-id", required=True)
        parser.add_argument("--redirect-uri", required=True)
        parser.add_argument("--secret-file", required=True)
        parser.add_argument("--name", default="Company GitLab")

    def handle(self, *args, **options):
        uri = options["redirect_uri"]
        parsed = urlsplit(uri)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or "*" in uri
            or any(c.isspace() for c in uri)
        ):
            raise CommandError("An exact HTTPS redirect URI is required.")
        try:
            secret = Path(options["secret_file"]).read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as error:
            raise CommandError("Cannot read the client secret file.") from error
        if len(secret) < 32:
            raise CommandError("Use a randomly generated client secret of at least 32 characters.")
        application = get_application_model()
        if application.objects.filter(client_id=options["client_id"]).exists():
            raise CommandError("Client already exists; no changes were made.")
        application.objects.create(
            client_id=options["client_id"],
            client_secret=secret,
            name=options["name"],
            client_type="confidential",
            authorization_grant_type="authorization-code",
            redirect_uris=uri,
            algorithm="RS256",
            skip_authorization=False,
        )
        self.stdout.write(self.style.SUCCESS("Company OIDC client registered. Secret not displayed."))
