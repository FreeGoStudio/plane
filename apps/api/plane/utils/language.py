from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import get_supported_language_variant
from django.utils.translation.trans_real import parse_accept_lang_header


def normalize_language(value):
    if not isinstance(value, str) or not value:
        return None
    value = value.lower()
    value = {"zh-cn": "zh-hans", "zh-tw": "zh-hant", "ua": "uk"}.get(value, value)
    try:
        return get_supported_language_variant(value)
    except LookupError:
        return None


def user_language(user):
    if user is not None and user.is_authenticated:
        try:
            return normalize_language(user.profile.language)
        except ObjectDoesNotExist:
            pass
    return None


def request_language(request):
    for language, quality in parse_accept_lang_header(request.META.get("HTTP_ACCEPT_LANGUAGE", "")):
        if quality > 0 and language != "*":
            supported = normalize_language(language)
            if supported:
                return supported
    return user_language(getattr(request, "user", None)) or settings.LANGUAGE_CODE
