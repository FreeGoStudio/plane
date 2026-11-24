# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Read GitLab metadata and immutable trees/blobs; no repository writes."""

import base64
import re
from urllib.parse import quote
from .repository_transport import RepositoryError, RepositoryTransport

MAX_FILE = 1024 * 1024


def component(value):
    return quote(str(value), safe="")


def safe_path(value, allow_empty=True):
    if not isinstance(value, str) or len(value) > 1024 or "\\" in value or any(ord(c) < 32 for c in value):
        raise RepositoryError("invalid_path")
    if not value and allow_empty:
        return value
    if not value or any(part in ("", ".", "..") for part in value.split("/")):
        raise RepositoryError("invalid_path")
    return value


def sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-fA-F0-9]{40}|[a-fA-F0-9]{64}", value):
        raise RepositoryError("invalid_upstream_response", 502)
    return value


class RepositoryProvider:
    def __init__(self, instance, token=None):
        self.instance = instance
        self.http = RepositoryTransport(instance, token)
        if instance.provider != "gitlab":
            raise RepositoryError("unsupported_provider")

    def actor(self):
        value = self.http.get("/user")
        if not isinstance(value, dict) or not isinstance(value.get("id"), int):
            raise RepositoryError("invalid_upstream_identity", 502)
        # Report upstream identity; a project/bot token is never labelled personal.
        return str(value["id"]), str(value.get("username") or value["id"])

    def metadata(self, identifier, by_id=True):
        value = self.http.get("/projects/" + component(identifier))
        if not isinstance(value, dict) or not isinstance(value.get("id"), int):
            raise RepositoryError("invalid_upstream_response", 502)
        path = safe_path(value.get("path_with_namespace"), False)
        if by_id and str(value["id"]) != str(identifier):
            raise RepositoryError("repository_identity_changed", 409)
        return {"external_id": str(value["id"]), "path": path, "default_branch": value.get("default_branch") or ""}

    def resolve(self, repository, ref):
        metadata = self.metadata(repository.external_id)
        ref = ref or repository.default_branch or metadata["default_branch"]
        if not isinstance(ref, str) or not 1 <= len(ref) <= 255 or any(ord(c) < 32 for c in ref):
            raise RepositoryError("invalid_ref")
        root = "/projects/" + component(repository.external_id)
        commit = self.http.get(root + "/repository/commits/" + component(ref))
        commit_sha = sha(commit.get("id"))
        return metadata, root, commit_sha

    def directory(self, repository, ref="", path="", page=1):
        safe_path(path)
        if not isinstance(page, int) or not 1 <= page <= 10000:
            raise RepositoryError("invalid_page")
        metadata, root, version = self.resolve(repository, ref)
        entries = self.http.get(
            root + "/repository/tree", {"ref": version, "path": path, "page": page, "per_page": 100}
        )
        more = len(entries) == 100
        result = []
        for entry in entries:
            kind = (
                "submodule"
                if entry.get("mode") == "160000"
                else "symlink"
                if entry.get("mode") == "120000"
                else entry["type"]
            )
            name = entry.get("name")
            result.append(
                {
                    "name": name,
                    "path": f"{path}/{name}" if path else name,
                    "type": kind,
                    "object_sha": entry.get("id"),
                }
            )
        return {
            "commit_sha": version,
            "path": path,
            "entries": result,
            "next_page": page + 1 if more else None,
            "source_url": self.link(metadata["path"], version, path, "tree"),
        }

    def file(self, repository, ref, path):
        safe_path(path, False)
        metadata, root, version = self.resolve(repository, ref)
        parent, _, name = path.rpartition("/")
        entry = None
        for page in range(1, 101):
            entries = self.http.get(
                root + "/repository/tree", {"ref": version, "path": parent, "page": page, "per_page": 100}
            )
            entry = next((item for item in entries if item.get("name") == name), None)
            if entry or len(entries) < 100:
                break
        if not entry:
            raise RepositoryError("file_not_found_or_directory_limit", 422)
        if entry.get("type") != "blob" or entry.get("mode") in ("160000", "120000"):
            raise RepositoryError("unsupported_file_type", 422)
        value = self.http.get(root + "/repository/files/" + component(path), {"ref": version})
        if value.get("commit_id") != version:
            raise RepositoryError("upstream_version_mismatch", 502)
        object_sha = value.get("blob_id")
        if value.get("size", MAX_FILE + 1) > MAX_FILE:
            raise RepositoryError("file_too_large", 422)
        if value.get("encoding") != "base64":
            raise RepositoryError("unsupported_file_encoding", 422)
        try:
            raw = base64.b64decode("".join(value["content"].split()), validate=True)
            if len(raw) > MAX_FILE:
                raise RepositoryError("file_too_large", 422)
            if b"\x00" in raw:
                raise RepositoryError("binary_file", 422)
            content = raw.decode("utf-8")
        except (ValueError, UnicodeError):
            raise RepositoryError("binary_or_invalid_file", 422) from None
        if content.startswith("version https://git-lfs.github.com/spec/v1"):
            raise RepositoryError("lfs_file", 422)
        return {
            "commit_sha": version,
            "object_sha": sha(object_sha),
            "path": path,
            "content": content,
            "source_url": self.link(metadata["path"], version, path, "blob"),
        }

    def link(self, repository_path, version, path, kind):
        return (
            self.instance.web_url.rstrip("/")
            + "/"
            + quote(repository_path, safe="/")
            + "/-/"
            + kind
            + "/"
            + version
            + "/"
            + quote(path, safe="/")
        )
