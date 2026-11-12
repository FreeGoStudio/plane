import pytest
from django.utils import translation

from plane.db.models import Profile
from plane.utils.email import generate_plain_text_from_html, render_localized_email


@pytest.mark.unit
@pytest.mark.parametrize(
    "preference, expected", [(None, "你的 Plane"), ("zh-CN", "你的 Plane"), ("en", "Your unique Plane")]
)
def test_login_email_uses_recipient_language_and_preserves_code(mocker, preference, expected):
    lookup = mocker.patch.object(Profile.objects, "filter")
    lookup.return_value.values_list.return_value.first.return_value = preference
    with translation.override("fr"):
        subject, html = render_localized_email(
            "emails/auth/magic_signin.html",
            {"code": "A1B2C3", "email": "person@example.com"},
            "person@example.com",
            "Your unique Plane login code is %(code)s",
            {"code": "A1B2C3"},
        )
        assert translation.get_language() == "fr"
    lookup.assert_called_once_with(user__email__iexact="person@example.com")
    assert expected in subject
    assert "A1B2C3" in subject
    assert "A1B2C3" in generate_plain_text_from_html(html)
    assert "person@example.com" in html
    if preference != "en":
        assert "此验证码在 10 分钟内有效" in html
        assert "This code is valid" not in html
    else:
        assert "This code is valid" in html


@pytest.mark.unit
def test_password_reset_email_preserves_link_and_escapes_recipient(mocker):
    lookup = mocker.patch.object(Profile.objects, "filter")
    lookup.return_value.values_list.return_value.first.return_value = "zh-CN"
    url = "https://example.com/reset?token=abc&uid=123"
    subject, html = render_localized_email(
        "emails/auth/forgot_password.html",
        {"forgot_password_url": url, "email": "<script>@example.com"},
        "person@example.com",
        "A new password to your Plane account has been requested",
    )
    assert "密码重置请求" in subject
    assert "重置你的 Plane 密码" in html
    assert "Reset your Plane password" not in html
    assert "<script>" not in html
    assert "&lt;script&gt;@example.com" in html
    assert url in generate_plain_text_from_html(html)
