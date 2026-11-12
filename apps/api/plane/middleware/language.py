from django.utils import translation
from django.utils.cache import patch_vary_headers

from plane.utils.language import request_language


class UserLanguageMiddleware:
    """Resolve the UI language after session authentication, isolated per request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language = request_language(request)
        request.LANGUAGE_CODE = language
        with translation.override(language):
            response = self.get_response(request)
        response.headers.setdefault("Content-Language", language)
        patch_vary_headers(response, ("Accept-Language", "Cookie"))
        return response
