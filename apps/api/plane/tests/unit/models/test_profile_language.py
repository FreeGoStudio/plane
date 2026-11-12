import pytest

from plane.db.models import Profile


@pytest.mark.unit
def test_new_profile_defaults_to_simplified_chinese():
    assert Profile().language == "zh-CN"


@pytest.mark.unit
@pytest.mark.parametrize("language", ["en", "zh-TW", "fr", "zh-CN"])
def test_explicit_profile_language_is_preserved(language):
    assert Profile(language=language).language == language
