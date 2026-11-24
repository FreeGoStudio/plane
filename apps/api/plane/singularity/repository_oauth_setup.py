# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Platform-admin OAuth registration guidance and encrypted client storage."""

import base64
import secrets
from urllib.parse import urlsplit
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from plane.db.models import RepositoryInstance, RepositoryOAuthApplication
from plane.license.models import InstanceAdmin
from .repository_api import RepositoryAPI, StrictSerializer, validated
from .repository_transport import RepositoryError, validate_instance
from .vault import keyring, VaultError


def can_configure(user):
    """Only platform administrators may configure shared provider applications."""
    return InstanceAdmin.objects.filter(user=user, role__gte=15).exists()


def application_secret(application):
    """Decrypt a client secret bound to this instance, never returning it from an API."""
    _, keys = keyring()
    try:
        value = base64.b64decode(application.encrypted_secret, validate=True)
        return (
            AESGCM(keys[application.key_version])
            .decrypt(value[:12], value[12:], f"repository-oauth:{application.instance_id}".encode())
            .decode()
        )
    except (KeyError, ValueError, InvalidTag, UnicodeError):
        raise VaultError("credential_unreadable") from None


class GuideInput(StrictSerializer):
    instance_id = serializers.UUIDField(required=False)
    provider = serializers.ChoiceField(choices=["gitlab"], required=False)
    web_url = serializers.URLField(required=False)
    api_url = serializers.URLField(required=False)
    allowed_networks = serializers.ListField(child=serializers.CharField(), default=list)


class SetupInput(GuideInput):
    client_id = serializers.CharField(max_length=255)
    client_secret = serializers.CharField(max_length=8192, trim_whitespace=False, write_only=True)


def proposed_instance(data):
    """Resolve an existing host or validate a new administrator-supplied site without network access."""
    if data.get("instance_id"):
        return get_object_or_404(RepositoryInstance, pk=data["instance_id"], enabled=True, provider="gitlab")
    web_url = data.get("web_url", "").rstrip("/")
    provider = data.get("provider")
    if not web_url or provider != "gitlab":
        raise RepositoryError("invalid_instance")
    existing = RepositoryInstance.objects.filter(web_url=web_url).first()
    if existing:
        if not existing.enabled or existing.provider != provider:
            raise RepositoryError("configuration_conflict", 409)
        return existing
    parsed = urlsplit(web_url)
    api_url = data.get("api_url") or web_url + "/api/v4"
    instance = RepositoryInstance(
        name="GitLab" + " · " + parsed.netloc,
        provider=provider,
        web_url=web_url,
        api_url=api_url.rstrip("/"),
        allowed_networks=data.get("allowed_networks", []),
    )
    validate_instance(instance)
    return instance


def guide(instance):
    """Return public registration instructions; client secrets never leave server storage."""
    from .repository_oauth import callback_url, oauth_config

    try:
        configured = False if instance._state.adding else bool(oauth_config(instance))
    except (RepositoryError, VaultError):
        configured = False
    app = RepositoryOAuthApplication.objects.filter(instance=instance).first() if not instance._state.adding else None
    return {
        "instance_id": str(instance.pk) if not instance._state.adding else None,
        "provider": instance.provider,
        "web_url": instance.web_url,
        "api_url": instance.api_url,
        "create_url": instance.web_url.rstrip("/") + "/-/user_settings/applications",
        "homepage_url": settings.WEB_URL.rstrip("/"),
        "callback_url": callback_url(),
        "scope": "read_api",
        "client_id": app.client_id if app else "",
        "configured": configured,
    }


class RepositoryOAuthSetup(RepositoryAPI):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not can_configure(request.user):
            raise PermissionDenied("Platform administrator required")

    def get(self, request):
        """Inspect registration instructions without persisting a host or contacting it."""
        return Response(guide(proposed_instance(validated(GuideInput, request.query_params.dict()))))

    @transaction.atomic
    def post(self, request):
        """Persist a validated host and encrypted OAuth secret atomically; saving is not consent."""
        data = validated(SetupInput, request.data)
        instance = proposed_instance(data)
        if any(c in data["client_secret"] for c in "\r\n\x00"):
            raise VaultError("invalid_credential")
        if instance._state.adding:
            instance.save()
        instance = RepositoryInstance.objects.select_for_update().get(pk=instance.pk)
        version, keys = keyring()
        nonce = secrets.token_bytes(12)
        encrypted = AESGCM(keys[version]).encrypt(
            nonce, data["client_secret"].encode(), f"repository-oauth:{instance.pk}".encode()
        )
        RepositoryOAuthApplication.objects.update_or_create(
            instance=instance,
            defaults={
                "client_id": data["client_id"],
                "key_version": version,
                "encrypted_secret": base64.b64encode(nonce + encrypted).decode(),
                "updated_by": request.user,
            },
        )
        return Response(guide(instance))
