# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Personal company connection UI. No management credentials enter this process."""

from django.conf import settings
from django.db import connection, transaction, IntegrityError
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from plane.db.models import CompanyAccount
from .company import CompanyError, GitLabCompanyClient, request_account
from .oidc import eligible


@sensitive_post_parameters("gitlab_token")
@require_http_methods(["GET", "POST"])
def company_account(request):
    if not settings.SINGULARITY_COMPANY_ENABLED:
        raise Http404
    if not eligible(request.user):
        return render(request, "singularity/login.html", {"return_url": request.path}, status=401)
    error = None
    if request.method == "POST":
        try:
            row = request_account(request.user)
            if request.POST.get("action") == "link":
                remote = GitLabCompanyClient(request.POST.get("gitlab_token", "")).call("GET", "user")
                if remote.get("state") != "active" or not isinstance(remote.get("id"), int):
                    raise CompanyError("invalid_existing_account")
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT pg_advisory_xact_lock(%s)",
                            [int.from_bytes(request.user.pk.bytes[:8], "big", signed=True)],
                        )
                    row = CompanyAccount.objects.select_for_update().get(pk=request.user.pk)
                    if row.external_id or row.create_requested or row.status == "processing":
                        raise CompanyError("account_already_in_progress")
                    if CompanyAccount.objects.exclude(pk=row.pk).filter(external_id=remote["id"]).exists():
                        raise CompanyError("account_already_associated")
                    row.proposed_external_id = remote["id"]
                    row.status, row.error_code, row.next_attempt_at = "pending", "", timezone.now()
                    row.save()
        except CompanyError as failure:
            error = str(failure)
        except IntegrityError:
            error = "account_already_associated"
    row = CompanyAccount.objects.filter(user=request.user).first()
    response = render(
        request, "singularity/company_account.html", {"account": row, "error": error}, status=400 if error else 200
    )
    response["Cache-Control"] = "no-store"
    # Native same-origin form POSTs must retain Origin for Django CSRF checks.
    response["Referrer-Policy"] = "same-origin"
    return response
