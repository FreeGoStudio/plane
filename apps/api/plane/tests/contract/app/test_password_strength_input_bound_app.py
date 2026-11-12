# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Password enrollment uses length and whole-password blocklisting, without truncation."""

import uuid
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from plane.db.models import User
from plane.license.models import Instance

LONG_STRONG_PASSWORD = "Xk9#mQ2$vL7@pR4!" * 20  # 320 chars


@pytest.fixture(autouse=True)
def _reset_auth_throttle_cache():
    cache.delete_pattern("throttle_authentication_*")
    yield
    cache.delete_pattern("throttle_authentication_*")


@pytest.fixture
def setup_instance(db):
    return Instance.objects.create(
        instance_name="Test Instance",
        instance_id=str(uuid.uuid4()),
        current_version="1.0.0",
        domain="http://localhost:8000",
        last_checked_at=timezone.now(),
        is_setup_done=True,
    )


@pytest.fixture
def django_client():
    return Client(HTTP_USER_AGENT="Mozilla/5.0")


@pytest.mark.contract
@pytest.mark.parametrize("url_name", ["sign-up", "space-sign-up"])
@patch("plane.authentication.adapter.base.user_activation_email")
def test_sign_up_stores_long_password_in_full(_mock_email, url_name, django_client, setup_instance):
    email = f"{url_name}@plane.so"
    django_client.post(reverse(url_name), {"email": email, "password": LONG_STRONG_PASSWORD})

    assert User.objects.get(email=email).check_password(LONG_STRONG_PASSWORD)


@pytest.mark.contract
@patch("plane.authentication.adapter.base.user_activation_email")
def test_sign_up_accepts_long_password_with_strong_tail(_mock_email, django_client, setup_instance):
    password = "password" * 16 + "Xk9#mQ2$vL7@pR4!"
    django_client.post(reverse("sign-up"), {"email": "tail@plane.so", "password": password})

    assert User.objects.get(email="tail@plane.so").check_password(password)


@pytest.mark.contract
def test_sign_up_still_rejects_weak_password(django_client, setup_instance):
    response = django_client.post(reverse("sign-up"), {"email": "weak@plane.so", "password": "password"})

    assert "PASSWORD_TOO_SHORT" in response.url
    assert not User.objects.filter(email="weak@plane.so").exists()


@pytest.mark.contract
@pytest.mark.parametrize("url_name", ["sign-up", "space-sign-up"])
@pytest.mark.parametrize(
    "password,error",
    [
        ("abcdefghijklmno", None),
        ("x" * 14, "PASSWORD_TOO_SHORT"),
        ("123456789987654321", "PASSWORD_TOO_WEAK"),
        ("  a long phrase with spaces  ", None),
        ("😀" * 14, "PASSWORD_TOO_SHORT"),
        ("😀" * 15, None),
    ],
)
@patch("plane.authentication.adapter.base.user_activation_email")
def test_signup_password_policy(_email, url_name, password, error, django_client, setup_instance):
    email = "policy@plane.so"
    response = django_client.post(reverse(url_name), {"email": email, "password": password})
    if error:
        assert error in response.url
        assert not User.objects.filter(email=email).exists()
    else:
        user = User.objects.get(email=email)
        assert user.check_password(password)
        assert not user.check_password(password + "x")


@pytest.mark.contract
@pytest.mark.parametrize("endpoint", ["change-password", "set-password"])
@pytest.mark.parametrize(
    "password,error",
    [
        ("a quiet walk through the garden", None),
        ("Abcdefghijk1!", "PASSWORD_TOO_SHORT"),
        ("123456789987654321", "PASSWORD_TOO_WEAK"),
    ],
)
@patch("plane.authentication.views.common.user_login")
def test_authenticated_password_endpoints(_login, endpoint, password, error, api_client, create_user):
    user = create_user
    user.is_password_autoset = endpoint == "set-password"
    user.save()
    previous_hash = user.password
    api_client.force_authenticate(user=user)
    response = api_client.post(
        f"/auth/{endpoint}/",
        {
            "password": password,
            "new_password": password,
            "old_password": "test-password",
        },
        format="json",
    )
    user.refresh_from_db()
    if error:
        assert response.status_code == 400
        assert response.data["error_message"] == error
        assert user.password == previous_hash
    else:
        assert response.status_code == 200
        assert user.check_password(password)


@pytest.mark.contract
@pytest.mark.parametrize("space", [False, True])
@pytest.mark.parametrize(
    "password,error",
    [
        ("  a quiet walk through the garden  ", None),
        ("Abcdefghijk1!", "PASSWORD_TOO_SHORT"),
        ("123456789987654321", "PASSWORD_TOO_WEAK"),
    ],
)
def test_reset_password_policy(space, password, error, django_client, create_user):
    from django.contrib.auth.tokens import PasswordResetTokenGenerator
    from django.utils.encoding import force_bytes
    from django.utils.http import urlsafe_base64_encode

    user = create_user
    previous_hash = user.password
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = PasswordResetTokenGenerator().make_token(user)
    prefix = "spaces/" if space else ""
    response = django_client.post(f"/auth/{prefix}reset-password/{uid}/{token}/", {"password": password})
    user.refresh_from_db()
    if error:
        assert error in response.url
        assert user.password == previous_hash
    else:
        assert user.check_password(password)
        assert not user.check_password(password.strip())


@pytest.mark.contract
@pytest.mark.parametrize("space", [False, True])
def test_legacy_short_password_can_still_sign_in(space, django_client, create_user, setup_instance):
    from django.contrib.auth.hashers import make_password

    user = create_user
    user.password = make_password("oldpass", hasher="pbkdf2_sha256")
    user.is_password_autoset = False
    user.save()
    prefix = "spaces/" if space else ""
    response = django_client.post(f"/auth/{prefix}sign-in/", {"email": user.email, "password": "oldpass"})
    assert response.status_code == 302
    assert "error_code" not in response.url
    user.refresh_from_db()
    assert user.check_password("oldpass")


@pytest.mark.contract
@pytest.mark.parametrize(
    "password,error",
    [
        ("a quiet walk through the garden", None),
        ("Abcdefghijk1!", "PASSWORD_TOO_SHORT"),
        ("123456789987654321", "PASSWORD_TOO_WEAK"),
    ],
)
@patch("plane.license.api.views.admin.user_login")
def test_admin_setup_password_policy(_login, password, error, django_client, setup_instance):
    setup_instance.is_setup_done = False
    setup_instance.save()
    email = "admin-policy@example.com"
    response = django_client.post(
        "/api/instances/admins/sign-up/",
        {
            "email": email,
            "password": password,
            "first_name": "Admin",
            "company_name": "Example",
        },
    )
    if error:
        assert error in response.url
        assert not User.objects.filter(email=email).exists()
    else:
        assert User.objects.get(email=email).check_password(password)


@pytest.mark.contract
@pytest.mark.parametrize(
    "password,error",
    [
        ("a quiet walk through the garden", None),
        ("Abcdefghijk1!", "15 characters"),
        ("123456789987654321", "common, compromised"),
    ],
)
def test_cli_password_reset_uses_same_policy(password, error, create_user):
    from django.core.management import call_command, CommandError

    with patch("getpass.getpass", return_value=password):
        if error:
            with pytest.raises(CommandError, match=error):
                call_command("reset_password", create_user.email)
        else:
            call_command("reset_password", create_user.email)
            create_user.refresh_from_db()
            assert create_user.check_password(password)
