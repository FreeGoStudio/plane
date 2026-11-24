# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import logging

import pytest
from django.http import HttpResponse
from django.middleware.csrf import CsrfViewMiddleware, get_token, rotate_token
from django.test import RequestFactory

from plane.authentication.views.common import CSRFTokenEndpoint


pytestmark = pytest.mark.unit


def check(token=None, cookie=None, origin="https://testserver"):
    request = RequestFactory().post(
        "/auth/sign-in/?password=DO_NOT_LOG",
        {"csrfmiddlewaretoken": token or "", "password": "DO_NOT_LOG"},
        secure=True,
        HTTP_ORIGIN=origin,
    )
    if cookie is not None:
        request.COOKIES["csrftoken"] = cookie
    middleware = CsrfViewMiddleware(lambda request: HttpResponse())
    middleware.process_request(request)
    return middleware.process_view(request, lambda request: HttpResponse(), (), {})


def test_rotated_cookie_rejects_old_form_but_accepts_fresh_token(caplog, settings):
    settings.CSRF_COOKIE_NAME = "csrftoken"
    caplog.set_level(logging.WARNING, logger="plane.authentication")
    browser = RequestFactory().get("/")
    stale = get_token(browser)
    rotate_token(browser)
    current = get_token(browser)
    cookie = browser.META["CSRF_COOKIE"]
    assert check(stale, cookie) is not None
    record = next(r for r in caplog.records if r.name == "plane.authentication")
    assert record.csrf_reason == "csrf_token_mismatch"
    assert record.csrf_cookie_present is True
    assert check(current, cookie) is None
    output = str([r.__dict__ for r in caplog.records if r.name == "plane.authentication"])
    for secret in (stale, current, cookie, "DO_NOT_LOG"):
        assert secret not in output


@pytest.mark.parametrize(
    "token,cookie,origin,reason",
    [
        (None, None, "https://testserver", "csrf_cookie_missing"),
        (None, "a" * 32, "https://testserver", "csrf_token_missing"),
        ("x", "a" * 32, "https://testserver", "csrf_token_malformed"),
        ("a" * 32, "x", "https://testserver", "csrf_cookie_malformed"),
        ("a" * 32, "a" * 32, "https://evil.invalid/?secret=DO_NOT_LOG", "origin_not_trusted"),
    ],
)
def test_failure_reasons_are_distinct_and_redacted(caplog, settings, token, cookie, origin, reason):
    settings.CSRF_COOKIE_NAME = "csrftoken"
    settings.CSRF_TRUSTED_ORIGINS = []
    caplog.set_level(logging.WARNING, logger="plane.authentication")
    assert check(token, cookie, origin) is not None
    records = [r for r in caplog.records if r.name == "plane.authentication"]
    assert len(records) == 1
    assert records[0].csrf_reason == reason
    assert "DO_NOT_LOG" not in str(records[0].__dict__)


def test_token_response_cannot_be_cached():
    request = RequestFactory().get("/auth/get-csrf-token/")
    response = CSRFTokenEndpoint.as_view()(request)
    assert response.status_code == 200
    assert response.data["csrf_token"]
    assert "no-store" in response["Cache-Control"]
    assert "private" in response["Cache-Control"]
