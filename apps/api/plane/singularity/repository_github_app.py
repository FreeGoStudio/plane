# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""User-authorized GitHub App reads with live installation and repository checks."""

from datetime import timedelta
from urllib.parse import quote

from django.db import transaction
from django.utils import timezone

from plane.db.models import RepositoryCredential, RepositorySelection, User
from .repository_transport import RepositoryError, RepositoryTransport
from .vault import oauth_material, seal_oauth, require_owner

PERMISSIONS = {"contents": "read", "metadata": "read"}
KIND = "github_app"


def check_permissions(value):
    if value != PERMISSIONS:
        raise RepositoryError("github_app_read_only_required", 403)


def app_metadata(instance, slug, client_id):
    app = RepositoryTransport(instance).get("/apps/" + quote(slug, safe=""))
    if (
        not isinstance(app, dict)
        or not isinstance(app.get("id"), int)
        or app.get("client_id") != client_id
        or app.get("slug") != slug
    ):
        raise RepositoryError("github_app_configuration_invalid")
    check_permissions(app.get("permissions"))
    return app


def install_url(instance):
    from .repository_oauth import oauth_config

    if instance.provider != "github":
        return None
    try:
        config = oauth_config(instance)
    except RepositoryError:
        return None
    return instance.web_url.rstrip("/") + "/apps/" + quote(config["app_slug"], safe="") + "/installations/new"


def pages(http, path, key):
    # Never follow upstream links or silently accept a truncated permission list.
    for page in range(1, 101):
        result = http.get(path, {"per_page": 100, "page": page})
        if not isinstance(result, dict) or not isinstance(result.get(key), list):
            raise RepositoryError("invalid_upstream_response", 502)
        rows = result[key]
        if any(not isinstance(row, dict) for row in rows):
            raise RepositoryError("invalid_upstream_response", 502)
        yield from rows
        if len(rows) < 100:
            return
    raise RepositoryError("github_installation_list_limit", 422)


def installation(instance, raw, config, repository_id, expected=None):
    http = RepositoryTransport(instance, raw)
    for item in pages(http, "/user/installations", "installations"):
        if item.get("app_id") != config["app_id"] or (expected and item.get("id") != expected):
            continue
        if item.get("suspended_at") or item.get("repository_selection") != "selected":
            continue
        if (
            not isinstance(item.get("id"), int)
            or not isinstance(item.get("account"), dict)
            or not isinstance(item["account"].get("id"), int)
        ):
            raise RepositoryError("invalid_upstream_response", 502)
        for repo in pages(http, f"/user/installations/{item['id']}/repositories", "repositories"):
            if str(repo.get("id")) == str(repository_id):
                check_permissions(item.get("permissions"))
                return item
    raise RepositoryError("github_selected_repository_required", 403)


def scoped_token(instance, raw, config, repository_id, installed):
    """Content adapters receive only a single-repository, read-only user token."""
    result = RepositoryTransport(instance, basic_auth=(config["client_id"], config["client_secret"])).request(
        "POST",
        "/applications/" + quote(config["client_id"], safe="") + "/token/scoped",
        body={
            "access_token": raw,
            "target_id": installed["account"]["id"],
            "repository_ids": [int(repository_id)],
            "permissions": PERMISSIONS,
        },
        json_body=True,
    )
    if not isinstance(result, dict) or not isinstance(result.get("token"), str) or not result["token"]:
        raise RepositoryError("invalid_upstream_response", 502)
    return result["token"]


def token_expiry(token):
    try:
        access, refresh = int(token["expires_in"]), int(token["refresh_token_expires_in"])
        if (
            not 0 < access <= 315360000
            or not 0 < refresh <= 315360000
            or not isinstance(token.get("access_token"), str)
            or not token["access_token"]
            or not isinstance(token.get("refresh_token"), str)
            or not token["refresh_token"]
        ):
            raise ValueError
        now = timezone.now()
        return now + timedelta(seconds=access), now + timedelta(seconds=refresh)
    except (KeyError, TypeError, ValueError):
        raise RepositoryError("github_expiring_tokens_required", 400) from None


@transaction.atomic
def save_connection(owner, instance, token, actor, metadata, config, installed):
    User.objects.select_for_update().get(pk=owner.pk)
    expires, refresh_expires = token_expiry(token)
    # Different repository grants must never replace each other's selections.
    rows = RepositoryCredential.objects.filter(
        owner=owner,
        instance=instance,
        kind=KIND,
        github_client_id=config["client_id"],
        github_repository_id=metadata["external_id"],
        external_actor_id=actor[0],
        revoked_at__isnull=True,
    )
    row = rows.order_by("-created_at").first() or RepositoryCredential(owner=owner, instance=instance, kind=KIND)
    row.github_client_id = config["client_id"]
    row.github_repository_id = metadata["external_id"]
    row.github_installation_id = installed["id"]
    row.external_actor_id, row.external_actor_label = actor
    row.label = f"{instance.name} · {actor[1]} · {metadata['path']}"[:160]
    row.expires_at, row.refresh_expires_at = expires, refresh_expires
    row.validated_at, row.validation_status = timezone.now(), "repository_verified"
    seal_oauth(row, token["access_token"], token["refresh_token"])
    row.save()
    RepositorySelection.objects.filter(owner=owner, credential__in=rows.exclude(pk=row.pk)).update(credential=row)
    rows.exclude(pk=row.pk).update(revoked_at=timezone.now())
    return row


@transaction.atomic
def refreshed_connection(user, credential, repository_id):
    from .repository_oauth import oauth_config, token_request

    # Match save_connection's lock order; consent and rotating refresh cannot race.
    user = User.objects.select_for_update().get(pk=user.pk)
    row = RepositoryCredential.objects.select_for_update().select_related("instance").get(pk=credential.pk)
    if (
        row.kind != KIND
        or row.owner_id != user.pk
        or row.revoked_at
        or not user.is_active
        or user.is_bot
        or not row.instance.enabled
        or row.github_repository_id != str(repository_id)
    ):
        raise RepositoryError("github_app_connection_required", 403)
    config = oauth_config(row.instance)
    if row.github_client_id != config["client_id"]:
        raise RepositoryError("github_app_connection_required", 403)
    material = oauth_material(row)
    if row.expires_at and row.expires_at <= timezone.now() + timedelta(seconds=60):
        if not row.refresh_expires_at or row.refresh_expires_at <= timezone.now():
            raise RepositoryError("upstream_authentication_required", 401)
        token = token_request(
            row.instance,
            config,
            {
                "grant_type": "refresh_token",
                "refresh_token": material.get("refresh_token"),
            },
        )
        row.expires_at, row.refresh_expires_at = token_expiry(token)
        seal_oauth(row, token.get("access_token"), token["refresh_token"])
        row.save()
        material = oauth_material(row)
    require_owner(row, user)
    return row, config, material


def read_token(user, credential, repository_id):
    # Commit rotating refresh material before a subsequent permission/network failure.
    row, config, material = refreshed_connection(user, credential, repository_id)
    installed = installation(row.instance, material["access_token"], config, repository_id, row.github_installation_id)
    return scoped_token(row.instance, material["access_token"], config, repository_id, installed)
