# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Company account lifecycle through GitLab APIs; never manipulates GitLab DB."""

from datetime import timedelta
from urllib.parse import urlsplit

import requests
from django.conf import settings
from django.db import connection
from django.utils import timezone
from plane.db.models import CompanyAccount


class CompanyError(Exception):
    """Sanitized failure code, never an upstream body or credential."""


class GitLabCompanyClient:
    def __init__(self, token):
        self.base = settings.SINGULARITY_COMPANY_URL.rstrip("/")
        parsed = urlsplit(self.base)
        if (
            not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.scheme not in (["https", "http"] if settings.SINGULARITY_COMPANY_ALLOW_HTTP else ["https"])
        ):
            raise CompanyError("invalid_company_instance")
        if not token:
            raise CompanyError("missing_credential")
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers["PRIVATE-TOKEN"] = token
        self.session.verify = settings.SINGULARITY_COMPANY_CA_FILE or True

    def call(self, method, path, **kwargs):
        """Only code-owned relative API paths reach the fixed company instance."""
        try:
            response = self.session.request(
                method, self.base + "/api/v4/" + path, timeout=(5, 20), allow_redirects=False, **kwargs
            )
        except requests.RequestException:
            raise CompanyError("company_unreachable") from None
        if not 200 <= response.status_code < 300:
            raise CompanyError("company_http_" + str(response.status_code))
        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError:
            raise CompanyError("invalid_company_response") from None

    def identity_users(self, subject):
        return self.call(
            "GET",
            "users",
            params={"provider": settings.SINGULARITY_COMPANY_PROVIDER, "extern_uid": str(subject), "per_page": 100},
        )


def request_account(user):
    """Existing users opt in; subsequent retries retain the same durable identity."""
    if not settings.SINGULARITY_COMPANY_ENABLED or not user.is_active or not user.is_email_verified or user.is_bot:
        raise CompanyError("account_not_eligible")
    row, _ = CompanyAccount.objects.get_or_create(
        user=user, defaults={"instance_url": settings.SINGULARITY_COMPANY_URL.rstrip("/")}
    )
    if row.status in ("retry", "awaiting_activation"):
        row.status, row.error_code, row.next_attempt_at = "pending", "", timezone.now()
        row.save()
    return row


def linked(user):
    return CompanyAccount.objects.filter(
        user=user, status="linked", instance_url=settings.SINGULARITY_COMPANY_URL.rstrip("/"), external_id__isnull=False
    ).exists()


def identity_matches(remote, user_id):
    return any(
        i.get("provider") == settings.SINGULARITY_COMPANY_PROVIDER and i.get("extern_uid") == str(user_id)
        for i in remote.get("identities", [])
    )


def process_account(user_id, client):
    """Serialize each intent using a PostgreSQL session lock across API requests.

    Intent is committed before creation. A response loss is reconciled by the
    immutable provider subject on the next attempt, never by email alone.
    """
    lock_key = int.from_bytes(user_id.bytes[:8], "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [lock_key])
        if not cursor.fetchone()[0]:
            return
    try:
        row = CompanyAccount.objects.select_related("user").get(user_id=user_id)
        if row.instance_url != client.base:
            raise CompanyError("company_instance_changed")
        user = row.user
        if not user.is_active or user.is_bot:
            if row.external_id and row.managed and row.status != "blocked":
                client.call("POST", f"users/{row.external_id}/block")
                remote = client.call("GET", f"users/{row.external_id}")
                if remote.get("state") != "blocked":
                    raise CompanyError("block_not_confirmed")
            row.status = "blocked" if row.managed else "disconnected"
            row.error_code = ""
            row.save()
            return
        if not user.is_email_verified:
            row.status = "awaiting_activation"
            row.save()
            return
        if row.status in ("linked", "conflict", "blocked", "disconnected"):
            return
        row.status, row.error_code = "processing", ""
        row.attempts += 1
        row.next_attempt_at = timezone.now() + timedelta(minutes=2)
        row.save()
        existing = client.identity_users(user.pk)
        if len(existing) > 1:
            raise CompanyError("duplicate_external_subject")
        if existing:
            remote = client.call("GET", f"users/{existing[0]['id']}")
            if not identity_matches(remote, user.pk):
                raise CompanyError("external_subject_mismatch")
            row.external_id = remote["id"]
            row.managed = row.create_requested and row.proposed_external_id is None
        elif row.proposed_external_id:
            remote = client.call("GET", f"users/{row.proposed_external_id}")
            identities = [
                i for i in remote.get("identities", []) if i.get("provider") == settings.SINGULARITY_COMPANY_PROVIDER
            ]
            if identities and not identity_matches(remote, user.pk):
                row.status, row.error_code = "conflict", "existing_identity_conflict"
                row.save()
                return
            client.call(
                "PUT",
                f"users/{row.proposed_external_id}",
                json={"provider": settings.SINGULARITY_COMPANY_PROVIDER, "extern_uid": str(user.pk)},
            )
            row.external_id, row.managed = row.proposed_external_id, False
        else:
            username = "plane_" + user.pk.hex
            email_matches = client.call("GET", "users", params={"search": user.email, "per_page": 100})
            name_matches = client.call("GET", "users", params={"username": username})
            if any(r.get("email", "").casefold() == user.email.casefold() for r in email_matches) or name_matches:
                row.status, row.error_code = "conflict", "prove_existing_account"
                row.save()
                return
            row.create_requested = True
            row.save(update_fields=["create_requested", "updated_at"])
            remote = client.call(
                "POST",
                "users",
                json={
                    "email": user.email,
                    "username": username,
                    "name": user.display_name or user.first_name or username,
                    "force_random_password": True,
                    "skip_confirmation": True,
                    "admin": False,
                    "can_create_group": False,
                    "projects_limit": 0,
                    "provider": settings.SINGULARITY_COMPANY_PROVIDER,
                    "extern_uid": str(user.pk),
                },
            )
            row.external_id, row.managed = remote["id"], True
        verified = client.call("GET", f"users/{row.external_id}")
        if not identity_matches(verified, user.pk) or verified.get("state") != "active":
            raise CompanyError("association_not_confirmed")
        row.status, row.error_code = "linked", ""
        row.save()
    except CompanyError as error:
        CompanyAccount.objects.filter(user_id=user_id).update(
            status="retry", error_code=str(error), next_attempt_at=timezone.now() + timedelta(minutes=1)
        )
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_key])
