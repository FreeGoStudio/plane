# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Project-bound, session-owned repository OAuth. No provider secrets reach AI."""

import base64
import hashlib
import json
import secrets
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote, urlencode

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET

from plane.db.models import ProjectRepository, RepositorySelection, ProjectMember, Project, RepositoryInstance
from .api import visible_projects
from .repository_provider import RepositoryProvider
from .repository_transport import RepositoryError, RepositoryTransport
from .vault import VaultError


def project_url(repository):
    return (
        settings.WEB_URL.rstrip("/")
        + "/"
        + quote(repository.project.workspace.slug, safe="")
        + f"/settings/projects/{repository.project_id}/repositories/?repository={repository.pk}"
    )


def oauth_config(instance):
    """Prefer encrypted administrator configuration, retaining legacy file fallback."""
    from plane.db.models import RepositoryOAuthApplication
    from .repository_oauth_setup import application_secret

    app = RepositoryOAuthApplication.objects.filter(instance=instance).first()
    if app:
        return {"client_id": app.client_id, "client_secret": application_secret(app)}
    try:
        configs = json.loads(Path(settings.SINGULARITY_REPOSITORY_OAUTH_FILE).read_text())
        config = configs[str(instance.pk)]
        if not isinstance(config.get("client_id"), str) or not config["client_id"]:
            raise ValueError
        return config
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise RepositoryError("repository_oauth_not_configured", 503) from None


def callback_url():
    return settings.WEB_URL.rstrip("/") + "/auth/singularity/repository-callback/"


def start(request, repository, draft=None):
    config = oauth_config(repository.instance)
    verifier = secrets.token_urlsafe(48)
    nonce = secrets.token_urlsafe(32)
    state = signing.dumps(
        {
            "nonce": nonce,
            "owner": str(request.user.pk),
            **({"draft": True} if draft else {"repository": str(repository.pk)}),
        },
        salt="repository-oauth",
    )
    # Server-side session; multiple repository tabs can complete independently.
    pending = request.session.get("repository_oauth", {})
    pending = {key: value for key, value in pending.items() if value["expires"] > timezone.now().timestamp()}
    if len(pending) >= 10:
        raise RepositoryError("too_many_pending_connections", 429)
    pending[nonce] = {"verifier": verifier, "expires": timezone.now().timestamp() + 600, "draft": draft}
    request.session["repository_oauth"] = pending
    scope = "read_api" if repository.instance.provider == "gitlab" else "repo"
    params = dict(
        client_id=config["client_id"],
        redirect_uri=callback_url(),
        response_type="code",
        scope=scope,
        state=state,
        code_challenge_method="S256",
        code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode(),
    )
    path = "/oauth/authorize" if repository.instance.provider == "gitlab" else "/login/oauth/authorize"
    return {"authorization_url": repository.instance.web_url.rstrip("/") + path + "?" + urlencode(params)}


def start_add(request, project, instance, path, purpose):
    """Keep an unsaved repository draft in the owner session until OAuth verifies access."""
    return start(
        request,
        SimpleNamespace(instance=instance),
        {
            "project": str(project.pk),
            "instance": str(instance.pk),
            "path": path,
            "purpose": purpose,
        },
    )


def exchange(instance, config, code, verifier):
    return token_request(instance, config, dict(grant_type="authorization_code", code=code, code_verifier=verifier))


def token_request(instance, config, grant):
    # GitLab may have a separately registered internal API authority. It is still
    # checked/pinned by the existing transport, including explicit private CIDRs.
    base = instance.api_url.removesuffix("/api/v4") if instance.provider == "gitlab" else instance.web_url
    endpoint = SimpleNamespace(
        api_url=base,
        web_url=instance.web_url,
        provider=instance.provider,
        allowed_networks=instance.allowed_networks,
        allow_http=instance.allow_http,
        ca_file=instance.ca_file,
        enabled=instance.enabled,
    )
    path = "/oauth/token" if instance.provider == "gitlab" else "/login/oauth/access_token"
    result = RepositoryTransport(endpoint).request(
        "POST",
        path,
        body=dict(
            client_id=config["client_id"],
            client_secret=config.get("client_secret", ""),
            redirect_uri=callback_url(),
            **grant,
        ),
        success_statuses=(200, 400),
    )
    if not isinstance(result, dict):
        raise RepositoryError("invalid_upstream_response", 502)
    if result.get("error"):
        if result["error"] == "invalid_grant":
            raise RepositoryError("upstream_authentication_required", 401)
        raise RepositoryError("repository_oauth_configuration_error", 503)
    return result


@require_GET
def callback(request):
    if not settings.SINGULARITY_REPOSITORIES_ENABLED:
        return HttpResponseBadRequest("Repository access is unavailable")
    try:
        data = signing.loads(request.GET.get("state", ""), salt="repository-oauth", max_age=600)
        if not request.user.is_authenticated or not request.user.is_active or request.user.is_bot:
            raise ValueError
        if data["owner"] != str(request.user.pk):
            raise ValueError
        pending = request.session.get("repository_oauth", {})
        entry = pending.pop(data["nonce"], None)
        if not entry or entry["expires"] <= timezone.now().timestamp():
            raise ValueError
        if not cache.add("repository-oauth-used:" + data["nonce"], True, 600):
            raise ValueError
        request.session["repository_oauth"] = pending
    except (signing.BadSignature, ValueError, KeyError, TypeError):
        return HttpResponseBadRequest(
            "Connection expired or does not belong to this session. Return to the project and retry."
        )
    draft = entry.get("draft") if data.get("draft") else None
    if draft:
        project = get_object_or_404(
            Project.objects.select_related("workspace"),
            pk=draft["project"],
            pk__in=visible_projects(request.user).values("pk"),
            id__in=ProjectMember.objects.filter(member=request.user, role=20, is_active=True).values("project_id"),
        )
        instance = get_object_or_404(RepositoryInstance, pk=draft["instance"], enabled=True)
        repository = SimpleNamespace(instance=instance, project=project, project_id=project.pk, pk="")
    else:
        repository = get_object_or_404(
            ProjectRepository.objects.select_related("instance", "project__workspace"),
            pk=data["repository"],
            enabled=True,
            instance__enabled=True,
            project__in=visible_projects(request.user),
            project_id__in=ProjectMember.objects.filter(member=request.user, is_active=True).values("project_id"),
        )
    result = "cancelled"
    if not request.GET.get("error") and request.GET.get("code"):
        try:
            token = exchange(
                repository.instance, oauth_config(repository.instance), request.GET["code"], entry["verifier"]
            )
            raw = token.get("access_token")
            if not isinstance(raw, str) or not raw:
                raise RepositoryError("authorization_failed")
            provider = RepositoryProvider(repository.instance, raw)
            actor_id, actor_label = provider.actor()
            # A login is not proof of repository access. Verify before saving a selection.
            metadata = (
                provider.metadata(draft["path"], by_id=False) if draft else provider.metadata(repository.external_id)
            )
            expires = token.get("expires_in")
            if expires is not None and not 0 < int(expires) <= 315360000:
                raise RepositoryError("authorization_failed")
            with transaction.atomic():
                from .repository_add import save_oauth, finish_add

                row = save_oauth(
                    request.user,
                    repository.instance,
                    raw,
                    actor_id,
                    actor_label,
                    timezone.now() + timedelta(seconds=int(expires)) if expires else None,
                    refresh_token=token.get("refresh_token"),
                )
                if draft:
                    repository = finish_add(project, request.user, instance, metadata, draft["purpose"], row)
                RepositorySelection.objects.update_or_create(
                    owner=request.user, repository=repository, defaults={"credential": row, "anonymous": False}
                )
            result = "connected"
        except (RepositoryError, VaultError, ValueError, TypeError) as error:
            result = error.code if isinstance(error, RepositoryError) else "authorization_failed"
    target = project_url(repository)
    if draft:
        target += "&section=" + quote(draft["purpose"], safe="")
    response = redirect(target + "&connection=" + quote(result, safe=""))
    response["Cache-Control"] = "no-store"
    response["Referrer-Policy"] = "no-referrer"
    return response
