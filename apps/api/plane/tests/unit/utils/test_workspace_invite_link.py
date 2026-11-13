# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from plane.app.serializers.workspace import WorkSpaceMemberInviteSerializer

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "app_url, web_url, expected_origin",
    [
        ("", "http://192.168.3.56:8088", "192.168.3.56:8088"),
        ("https://plane.example.com/", "http://localhost:8088", "plane.example.com"),
        ("", "", ""),
    ],
)
def test_invite_link_uses_configured_public_origin(settings, app_url, web_url, expected_origin):
    settings.APP_BASE_URL = app_url
    settings.WEB_URL = web_url
    invitation = SimpleNamespace(id="example", workspace=SimpleNamespace(slug="team"), token="a.b-c_d")
    link = WorkSpaceMemberInviteSerializer().get_invite_link(invitation)
    parsed = urlsplit(link)
    assert parsed.netloc == expected_origin
    assert parsed.path == "/workspace-invitations/"
    assert parse_qs(parsed.query) == {
        "invitation_id": ["example"], "slug": ["team"], "token": ["a.b-c_d"]
    }
