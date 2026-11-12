import pytest
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from types import SimpleNamespace

from plane.authentication.utils.password import PasswordPolicyValidator, password_validation_error
from plane.authentication.utils.hashers import NFCPasswordHasher

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "password",
    [
        "abcdefghijklmno",
        "ABCDEFGHIJKLMNO",
        "834729618362947",
        "!@#$%^&*[]~`+=?",
        "a quiet walk through the garden",
        "😀" * 15,
        "  long phrase with spaces  ",
        "x" * 64,
        "x" * 320,
        "password is part of this longer phrase",
    ],
)
def test_accepts_without_composition_or_substring_rules(password):
    assert password_validation_error(password) is None
    PasswordPolicyValidator().validate(password)


@pytest.mark.parametrize("password", [None, False, 123, "", "A1!abcdefghijk", "😀" * 14, "e\u0301" * 14])
def test_minimum_counts_normalized_unicode_codepoints(password):
    assert password_validation_error(password) == "PASSWORD_TOO_SHORT"


def test_blocks_known_leaked_whole_password_and_account_name():
    assert password_validation_error("123456789987654321") == "PASSWORD_TOO_WEAK"
    user = SimpleNamespace(email="longaccountname@example.com", username="longaccountname")
    assert password_validation_error("longaccountname", user=user) == "PASSWORD_TOO_WEAK"
    assert password_validation_error("longaccountname is part of a phrase", user=user) is None
    with pytest.raises(ValidationError, match="common, compromised"):
        PasswordPolicyValidator().validate("123456789987654321")


def test_nfc_hashing_and_legacy_verification():
    composed = "é" * 15
    decomposed = "e\u0301" * 15
    encoded = make_password(decomposed)
    assert encoded.startswith(NFCPasswordHasher.algorithm + "$")
    assert check_password(composed, encoded)
    assert check_password(decomposed, encoded)
    assert not check_password(composed + "x", encoded)
    # Existing short or decomposed passwords retain exact legacy verification.
    legacy = make_password("short", hasher="pbkdf2_sha256")
    assert check_password("short", legacy)
    legacy_unicode = make_password(decomposed, hasher="pbkdf2_sha256")
    assert check_password(decomposed, legacy_unicode)
    assert not check_password(composed, legacy_unicode)


@pytest.mark.parametrize(
    "password,valid", [("e\u0301" * 14, False), ("e\u0301" * 15, True), ("123456789987654321", False)]
)
def test_password_serializer_uses_normalized_policy(password, valid):
    from plane.app.serializers.user import ResetPasswordSerializer

    serializer = ResetPasswordSerializer(data={"new_password": password})
    assert serializer.is_valid() is valid
