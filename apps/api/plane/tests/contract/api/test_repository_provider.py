# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Provider contracts: exact commits, bounded content, registered-host transport."""

import base64
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest

from plane.singularity.repository_transport import RepositoryTransport, RepositoryError
from plane.singularity.repository_provider import RepositoryProvider, MAX_FILE, safe_path

COMMIT, TREE, BLOB = "a" * 40, "b" * 40, "c" * 40


def host(provider="gitlab", **kwargs):
    return SimpleNamespace(
        provider=provider,
        api_url="https://api.example.test",
        web_url="https://example.test",
        allowed_networks=kwargs.get("networks", []),
        allow_http=False,
        ca_file="",
        enabled=True,
    )


def provider(kind, content=b"<script>alert('untrusted')</script>"):
    adapter = RepositoryProvider(host(kind), "private-token")
    repo = SimpleNamespace(external_id="123", default_branch="main")
    meta = {"id": 123, "path_with_namespace": "team/repo", "default_branch": "main"}
    entry = {
        "name": "README.md",
        "path": "README.md",
        "mode": "100644",
        "type": "blob",
        "id": BLOB,
        "sha": BLOB,
        "size": len(content),
    }
    blob = {
        "size": len(content),
        "encoding": "base64",
        "content": base64.b64encode(content).decode(),
        "commit_id": COMMIT,
        "blob_id": BLOB,
    }

    def get(path, params=None):
        if path == "/projects/123":
            return meta
        if "/commits/" in path:
            return {"id": COMMIT}
        if path.endswith("/repository/tree"):
            assert params["ref"] == COMMIT
            return [entry]
        if "/repository/files/" in path:
            assert params["ref"] == COMMIT
            return blob
        raise AssertionError(path)

    adapter.http.get = Mock(side_effect=get)
    return adapter, repo, entry, blob


@pytest.mark.parametrize("kind", ["gitlab"])
def test_real_content_contract_is_pinned_to_resolved_commit(kind):
    adapter, repo, _, _ = provider(kind)
    listing = adapter.directory(repo)
    result = adapter.file(repo, "main", "README.md")
    assert listing["commit_sha"] == result["commit_sha"] == COMMIT
    assert result["object_sha"] == BLOB and result["content"].startswith("<script>")
    assert COMMIT in result["source_url"]
    assert listing["entries"][0]["path"] == "README.md"


@pytest.mark.parametrize("kind", ["gitlab"])
@pytest.mark.parametrize("mode", ["160000", "120000"])
def test_submodules_and_symlinks_never_follow_other_repositories(kind, mode):
    adapter, repo, entry, _ = provider(kind)
    entry["mode"] = mode
    with pytest.raises(RepositoryError, match="unsupported_file_type"):
        adapter.file(repo, "main", "README.md")


@pytest.mark.parametrize("kind", ["gitlab"])
@pytest.mark.parametrize(
    "content,error",
    [
        (b"binary\x00", "binary_file"),
        (b"version https://git-lfs.github.com/spec/v1\noid test", "lfs_file"),
        (b"a" * (MAX_FILE + 1), "file_too_large"),
    ],
)
def test_preview_content_limits(kind, content, error):
    adapter, repo, _, _ = provider(kind, content)
    with pytest.raises(RepositoryError, match=error):
        adapter.file(repo, "main", "README.md")


@pytest.mark.parametrize("path", ["../secret", "/absolute", "foo/../bar", "foo\\bar", "foo\x00", "foo//bar"])
def test_path_rejects_traversal(path):
    with pytest.raises(RepositoryError, match="invalid_path"):
        safe_path(path)


def dns(address):
    return [(2, 1, 6, "", (address, 443))]


def test_private_dns_rejected_before_sending_credential():
    with patch("socket.getaddrinfo", return_value=dns("127.0.0.1")), patch("urllib3.HTTPSConnectionPool") as pool:
        with pytest.raises(RepositoryError, match="address_not_allowed"):
            RepositoryTransport(host(), "private-token").get("/user")
        pool.assert_not_called()


def test_explicit_network_pins_address_and_keeps_hostname_verification():
    with (
        patch("socket.getaddrinfo", return_value=dns("10.20.1.2")) as resolve,
        patch("urllib3.HTTPSConnectionPool") as pool,
    ):
        response = pool.return_value.urlopen.return_value
        response.status = 200
        response.read.return_value = b'{"id":1}'
        assert RepositoryTransport(host(networks=["10.20.1.0/24"]), "private-token").get("/user") == {"id": 1}
        assert resolve.call_count == 1
        assert pool.call_args.args == ("10.20.1.2",)
        assert pool.call_args.kwargs["assert_hostname"] == "api.example.test"
        assert pool.call_args.kwargs["server_hostname"] == "api.example.test"
        assert pool.call_args.kwargs["cert_reqs"] == "CERT_REQUIRED"
        assert pool.return_value.urlopen.call_args.kwargs["redirect"] is False
        assert pool.return_value.urlopen.call_args.kwargs["headers"]["Authorization"] == "Bearer private-token"


@pytest.mark.parametrize(
    "status,error",
    [
        (302, "upstream_redirect_refused"),
        (401, "upstream_authentication_required"),
        (403, "upstream_access_denied"),
        (404, "upstream_resource_invisible"),
        (429, "upstream_rate_limited"),
        (500, "upstream_unavailable"),
    ],
)
def test_upstream_errors_do_not_redirect_or_retry_anonymously(status, error):
    with patch("socket.getaddrinfo", return_value=dns("8.8.8.8")), patch("urllib3.HTTPSConnectionPool") as pool:
        response = pool.return_value.urlopen.return_value
        response.status = status
        with pytest.raises(RepositoryError, match=error):
            RepositoryTransport(host(), "private-token").get("/user")
        assert pool.return_value.urlopen.call_count == 1
        response.read.assert_not_called()


def test_gitlab_directory_pagination():
    adapter, repo, entry, _ = provider("gitlab")
    original = adapter.http.get.side_effect
    adapter.http.get.side_effect = (
        lambda path, params=None: ([entry] * 100 if params["page"] == 1 else [entry])
        if path.endswith("/repository/tree")
        else original(path, params)
    )
    assert adapter.directory(repo)["next_page"] == 2
    assert len(adapter.directory(repo, page=2)["entries"]) == 1
    assert adapter.directory(repo, page=2)["next_page"] is None


@pytest.mark.parametrize("kind", ["github", "unsupported"])
def test_other_providers_rejected_before_network(kind):
    with patch("socket.getaddrinfo") as dns:
        with pytest.raises(RepositoryError, match="unsupported_provider"):
            RepositoryProvider(host(kind), "private-token")
        with pytest.raises(RepositoryError, match="unsupported_provider"):
            RepositoryTransport(host(kind), "private-token").get("/user")
        dns.assert_not_called()


@pytest.mark.parametrize("method,status", [("POST", 201), ("PATCH", 200), ("DELETE", 204)])
def test_management_transport_json_and_empty_delete_response(method, status):
    with patch("socket.getaddrinfo", return_value=dns("8.8.8.8")), patch("urllib3.HTTPSConnectionPool") as pool:
        response = pool.return_value.urlopen.return_value
        response.status = status
        response.read.return_value = b'{"id":1}'
        body = {"allowed_to_push": [{"access_level": 0}]} if method != "DELETE" else None
        result = RepositoryTransport(host("gitlab"), "management-token").request(
            method, "/projects/1", body=body, json_body=True, success_statuses=(200, 201, 204)
        )
        request = pool.return_value.urlopen.call_args.kwargs
        assert request["redirect"] is False
        if body:
            assert request["headers"]["Content-Type"] == "application/json"
            assert json.loads(request["body"]) == body
        if status == 204:
            assert result is None
            response.read.assert_not_called()
        else:
            assert result == {"id": 1}
