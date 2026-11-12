from types import SimpleNamespace

import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from django.utils import translation

from plane.middleware.language import UserLanguageMiddleware
from plane.utils.language import request_language


@pytest.mark.unit
@pytest.mark.parametrize(
    "header, preference, expected",
    [
        ("", None, "zh-hans"),
        ("", "en", "en"),
        ("zh-CN", "en", "zh-hans"),
        ("en", "zh-CN", "en"),
        ("xx-invalid", "en", "en"),
        ("xx-invalid", None, "zh-hans"),
        ("zh-TW", None, "zh-hant"),
        ("en;q=0,zh-CN;q=0.9", "en", "zh-hans"),
        ("*", "en", "en"),
    ],
)
def test_language_selection(header, preference, expected):
    request = RequestFactory().get("/", HTTP_ACCEPT_LANGUAGE=header)
    request.user = SimpleNamespace(
        is_authenticated=preference is not None, profile=SimpleNamespace(language=preference)
    )
    assert request_language(request) == expected


@pytest.mark.unit
def test_language_context_is_restored_and_response_varies():
    request = RequestFactory().get("/", HTTP_ACCEPT_LANGUAGE="zh-CN")

    def view(request):
        assert request.LANGUAGE_CODE == "zh-hans"
        assert translation.get_language() == "zh-hans"
        return HttpResponse("ok")

    with translation.override("en"):
        response = UserLanguageMiddleware(view)(request)
        assert translation.get_language() == "en"
    assert response["Content-Language"] == "zh-hans"
    assert set(response["Vary"].split(", ")) == {"Accept-Language", "Cookie"}


@pytest.mark.unit
def test_language_context_is_restored_on_failure():
    request = RequestFactory().get("/", HTTP_ACCEPT_LANGUAGE="zh-CN")

    def view(request):
        raise RuntimeError("test failure")

    with translation.override("en"):
        with pytest.raises(RuntimeError):
            UserLanguageMiddleware(view)(request)
        assert translation.get_language() == "en"
