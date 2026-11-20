# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Crash-safe administrator PAT replacement in the isolated provisioning worker.

The bootstrap secret is read only on first use. Encrypted durable state is the
authority thereafter; never fall back to a retired bootstrap credential.
"""

import base64
import fcntl
import json
import os
import secrets
import uuid
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.utils import timezone

from .company import CompanyError, GitLabCompanyClient
from .repository_managed import revoke
from .vault import keyring


class AdminCredentialStore:
    """Serialize rotation AND consumers so no process uses a just-retired PAT."""

    def __init__(self, directory, bootstrap):
        self.directory = Path(directory)
        self.bootstrap = Path(bootstrap)
        self.path = self.directory / "credential.json"
        self.aad = ("company-admin-v1:" + settings.SINGULARITY_COMPANY_URL.rstrip("/")).encode()

    def save(self, state):
        """Atomic replace plus fsync before any remote credential revocation."""
        version, keys = keyring()
        nonce = secrets.token_bytes(12)
        encrypted = AESGCM(keys[version]).encrypt(nonce, json.dumps(state).encode(), self.aad)
        payload = json.dumps({"version": version, "ciphertext": base64.b64encode(nonce + encrypted).decode()})
        temp = self.directory / "credential.tmp"
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, self.path)
        fd = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def load(self):
        if not self.path.exists():
            return {"token": self.bootstrap.read_text().strip(), "retired": [], "pending": "", "next_check": 0}
        try:
            payload = json.loads(self.path.read_text())
            _, keys = keyring()
            raw = base64.b64decode(payload["ciphertext"], validate=True)
            return json.loads(AESGCM(keys[payload["version"]]).decrypt(raw[:12], raw[12:], self.aad))
        except (KeyError, ValueError, InvalidTag, TypeError):
            raise CompanyError("admin_state_unreadable") from None

    def cleanup(self, state, client):
        for token_id in list(state["retired"]):
            revoke(client, token_id)
            state["retired"].remove(token_id)
            self.save(state)
        if state["pending"]:
            page = 1
            while True:
                tokens = client.call(
                    "GET",
                    "personal_access_tokens",
                    params={
                        "user_id": state["user_id"],
                        "search": state["pending"],
                        "revoked": False,
                        "per_page": 100,
                        "page": page,
                    },
                )
                matches = [
                    t
                    for t in tokens
                    if t.get("name") == state["pending"]
                    and t.get("user_id") == state["user_id"]
                    and t["id"] != state["id"]
                ]
                for token in matches:
                    revoke(client, token["id"])
                if len(tokens) < 100:
                    break
                if not matches:
                    page += 1
            state["pending"] = ""
            self.save(state)

    def maintain(self, state):
        client = GitLabCompanyClient(state["token"])
        self.cleanup(state, client)
        now = timezone.now()
        if state["next_check"] > now.timestamp():
            return client
        current = client.call("GET", "personal_access_tokens/self")
        actor = client.call("GET", "user")
        if (
            not current.get("active")
            or current.get("revoked")
            or not actor.get("is_admin")
            or actor.get("state") != "active"
            or current["user_id"] != actor["id"]
            or "api" not in current.get("scopes", [])
            or (state.get("id") and (state["id"] != current["id"] or state["user_id"] != actor["id"]))
        ):
            raise CompanyError("admin_identity_invalid")
        config = client.call("GET", "application/settings")
        days = min(365, max(1, int(config.get("max_personal_access_token_lifetime") or 365)))
        window = min(timedelta(days=30), timedelta(days=days) / 4)
        due = not state.get("managed") or (
            current.get("expires_at") and date.fromisoformat(current["expires_at"]) <= (now + window).date()
        )
        state.update(id=current["id"], user_id=actor["id"], expires_at=current.get("expires_at"))
        if due:
            # Separate issuance deliberately preserves the old token until the
            # replacement is durable; self/rotate revokes it before persistence.
            state["pending"] = "plane-company-admin-" + uuid.uuid4().hex
            self.save(state)
            fresh = client.call(
                "POST",
                f"users/{actor['id']}/personal_access_tokens",
                json={
                    "name": state["pending"],
                    "scopes": current["scopes"],
                    "expires_at": (now.date() + timedelta(days=days)).isoformat(),
                },
            )
            if (
                not fresh.get("token")
                or fresh.get("user_id") != actor["id"]
                or set(fresh.get("scopes", [])) != set(current["scopes"])
                or date.fromisoformat(fresh["expires_at"]) <= now.date()
            ):
                raise CompanyError("invalid_admin_token_response")
            replacement = GitLabCompanyClient(fresh["token"])
            verified = replacement.call("GET", "personal_access_tokens/self")
            verified_actor = replacement.call("GET", "user")
            if (
                verified.get("id") != fresh["id"]
                or not verified.get("active")
                or verified_actor.get("id") != actor["id"]
                or not verified_actor.get("is_admin")
            ):
                raise CompanyError("admin_replacement_not_verified")
            state.update(
                token=fresh["token"],
                id=fresh["id"],
                expires_at=fresh["expires_at"],
                managed=True,
                pending="",
                retired=[current["id"]],
                generation=state.get("generation", 0) + 1,
                rotated_at=now.isoformat(),
            )
            self.save(state)
            client.session.close()
            client = replacement
            self.cleanup(state, client)
        state["next_check"] = (now + min(timedelta(hours=1), window / 4)).timestamp()
        self.save(state)
        return client

    @contextmanager
    def client(self):
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (self.directory / "rotation.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            client = self.maintain(self.load())
            try:
                yield client
            finally:
                client.session.close()
                fcntl.flock(lock, fcntl.LOCK_UN)
