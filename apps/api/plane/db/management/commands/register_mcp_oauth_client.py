# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Explicitly register the configured MCP public client without changing grants."""

import ipaddress
from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from oauth2_provider.models import get_application_model
from plane.singularity.oauth import CLIENT_ID


def valid_redirect(value):
    """Accept exact HTTPS callbacks or literal loopback HTTP callbacks only."""
    try:
        uri = urlsplit(value)
        port = uri.port
        if not uri.hostname or uri.username or uri.password or uri.fragment:
            return False
        if any(c.isspace() for c in value) or "*" in value or "\\" in value:
            return False
        if uri.scheme == "https":
            return port is None or port > 0
        return uri.scheme == "http" and ipaddress.ip_address(uri.hostname).is_loopback and bool(port)
    except ValueError:
        return False


class Command(BaseCommand):
    help = "Register configured exact MCP callbacks; refuse conflicting existing registrations."

    @transaction.atomic
    def handle(self, *args, **options):
        callbacks = settings.SINGULARITY_REDIRECT_URIS
        if not callbacks or not all(valid_redirect(value) for value in callbacks):
            raise CommandError("MCP callbacks must be exact HTTPS or literal loopback HTTP URLs.")
        application = get_application_model()
        expected = dict(
            client_type=application.CLIENT_PUBLIC,
            authorization_grant_type=application.GRANT_AUTHORIZATION_CODE,
            redirect_uris=" ".join(sorted(set(callbacks))),
            algorithm="",
            skip_authorization=False,
        )
        app, created = application.objects.get_or_create(
            client_id=CLIENT_ID, defaults={**expected, "name": "Singularity MCP"}
        )
        if any(getattr(app, key) != value for key, value in expected.items()):
            raise CommandError("Existing MCP registration differs; review it explicitly before changing callbacks.")
        self.stdout.write("MCP DOT registration created." if created else "MCP DOT registration verified.")
