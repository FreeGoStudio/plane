# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Personal MCP gateway. Plane remains the sole authorization authority."""

import hashlib
import json
import logging
import os
import sqlite3
import ssl
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import httpx
from cryptography.fernet import Fernet
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings


class PlaneError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(f"Plane request failed: {status} {code}")


class Vault:
    """Encrypt tokens and pending discussion content; never persist MCP bearer tokens."""

    def __init__(self, path, key):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path, self.cipher = path, Fernet(key)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tokens (key TEXT PRIMARY KEY, data BLOB NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY, connection TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    data BLOB NOT NULL, result BLOB, UNIQUE(connection,fingerprint));
                CREATE TABLE IF NOT EXISTS audit (
                    trace TEXT PRIMARY KEY, connection TEXT, operation TEXT, status INTEGER, at REAL);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def encode(self, value):
        return self.cipher.encrypt(json.dumps(value, sort_keys=True).encode())

    def decode(self, value):
        return json.loads(self.cipher.decrypt(value))

    def get_token(self, key):
        with self.connect() as db:
            row = db.execute("SELECT data FROM tokens WHERE key=? AND expires>?", (key, time.time() + 20)).fetchone()
            return self.decode(row["data"]) if row else None

    def set_token(self, key, data):
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO tokens VALUES (?,?,?)",
                (key, self.encode(data), time.time() + data["expires_in"]),
            )

    def prepare(self, connection, data):
        fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO decisions(id,connection,fingerprint,data) VALUES (?,?,?,?)",
                (str(uuid.uuid4()), connection, fingerprint, self.encode(data)),
            )
            row = db.execute(
                "SELECT id FROM decisions WHERE connection=? AND fingerprint=?", (connection, fingerprint)
            ).fetchone()
            return row["id"]

    def decision(self, connection, decision_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM decisions WHERE id=? AND connection=?", (decision_id, connection)
            ).fetchone()
            if not row:
                raise ValueError("Unknown decision for this connection")
            return self.decode(row["data"])

    def record(self, connection, operation, status):
        with self.connect() as db:
            db.execute(
                "INSERT INTO audit VALUES (?,?,?,?,?)", (str(uuid.uuid4()), connection, operation, status, time.time())
            )


class Plane:
    def __init__(self, base, secret, vault, ca=None, transport=None):
        self.base, self.secret, self.vault = base.rstrip("/"), secret, vault
        self.client = httpx.AsyncClient(
            base_url=self.base,
            timeout=20,
            follow_redirects=False,
            verify=ssl.create_default_context(cafile=ca),
            transport=transport,
        )

    async def exchange(self, bearer, inspect=False):
        try:
            response = await self.client.post(
                "/auth/singularity/exchange/",
                data={
                    "subject_token": bearer,
                    "inspect": "1" if inspect else "0",
                },
                headers={"X-Gateway-Secret": self.secret},
            )
        except httpx.HTTPError:
            raise PlaneError(503, "authorization_unavailable") from None
        if response.status_code != 200:
            raise PlaneError(response.status_code, "authorization_failed")
        return response.json()

    async def context(self):
        access = get_access_token()
        if not access:
            raise PlaneError(401, "login_required")
        # Do not rely on the earlier HTTP authentication check when invoking a tool.
        identity = await self.exchange(access.token, inspect=True)
        cache_key = hashlib.sha256(access.token.encode()).hexdigest()
        token = self.vault.get_token(cache_key)
        if not token:
            token = await self.exchange(access.token)
            self.vault.set_token(cache_key, token)
        return identity["connection_id"], token["access_token"]

    async def request(self, method, path, *, payload=None, params=None):
        connection, token = await self.context()
        try:
            response = await self.client.request(
                method,
                "/api/singularity/v1/" + path,
                json=payload,
                params=params,
                headers={"Authorization": "Bearer " + token},
            )
        except httpx.HTTPError:
            self.vault.record(connection, method, 503)
            raise PlaneError(
                503, "outcome_unknown_retry_same_decision" if method == "POST" else "unavailable"
            ) from None
        self.vault.record(connection, method, response.status_code)
        if response.status_code >= 300:
            codes = {
                401: "reauthorize",
                403: "permission_or_scope_denied",
                402: "unsupported_capability",
                404: "not_found_or_invisible",
                409: "conflict",
                429: "rate_limited",
            }
            raise PlaneError(response.status_code, codes.get(response.status_code, "request_rejected"))
        return response.json()

    async def resolve(self, project_ref, workspace=None):
        if not project_ref or len(project_ref) > 255:
            raise ValueError("A project reference is required")
        candidates, offset = [], 0
        while True:
            result = await self.request(
                "GET",
                "projects/",
                params={
                    "search": project_ref,
                    "offset": offset,
                    **({"workspace": workspace} if workspace else {}),
                },
            )
            candidates.extend(result["results"])
            offset = result["next_offset"]
            if offset is None:
                break
        exact = [
            p
            for p in candidates
            if project_ref.casefold() in (p["id"].casefold(), p["identifier"].casefold(), p["name"].casefold())
        ]
        matches = exact or candidates
        if len(matches) != 1:
            return None, {"status": "ambiguous" if matches else "not_found", "candidates": matches}
        return matches[0], None


def project_path(project):
    return f"workspaces/{quote(project['workspace'], safe='')}/projects/{uuid.UUID(project['id'])}/"


class Verifier(TokenVerifier):
    def __init__(self, plane, resource):
        self.plane, self.resource = plane, resource

    async def verify_token(self, token):
        try:
            data = await self.plane.exchange(token, inspect=True)
            return AccessToken(
                token=token,
                client_id="singularity-codex",
                scopes=data["scope"].split(),
                expires_at=data["expires_at"],
                resource=self.resource,
            )
        except (PlaneError, ValueError, KeyError):
            return None


def build_server(plane, issuer, resource):
    mcp = FastMCP(
        "Singularity",
        token_verifier=Verifier(plane, resource),
        auth=AuthSettings(issuer_url=issuer, resource_server_url=resource, required_scopes=[]),
        host="0.0.0.0",
        port=8001,
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["localhost:*", "127.0.0.1:*", "gateway:8001"],
            allowed_origins=[issuer],
        ),
    )

    @mcp.tool()
    async def list_accessible_projects(workspace: str | None = None, search: str = "", offset: int = 0):
        """List only projects visible to the authenticated Plane user."""
        return await plane.request(
            "GET",
            "projects/",
            params={"search": search, "offset": offset, **({"workspace": workspace} if workspace else {})},
        )

    @mcp.tool()
    async def search_work_items(project_ref: str, keyword: str = "", workspace: str | None = None, offset: int = 0):
        """Search visible work items; similarity never authorizes overwriting."""
        project, ambiguity = await plane.resolve(project_ref, workspace)
        return ambiguity or await plane.request(
            "GET", project_path(project) + "work-items/", params={"search": keyword, "offset": offset}
        )

    @mcp.tool()
    async def get_work_item(project_ref: str, item_id: str, workspace: str | None = None):
        """Read a visible work item and its exact update version."""
        project, ambiguity = await plane.resolve(project_ref, workspace)
        return ambiguity or await plane.request("GET", project_path(project) + f"work-items/{uuid.UUID(item_id)}/")

    @mcp.tool()
    async def get_my_capabilities(project_ref: str, item_id: str | None = None, workspace: str | None = None):
        """Show current capability hints; every actual write is checked again."""
        project, ambiguity = await plane.resolve(project_ref, workspace)
        suffix = f"work-items/{uuid.UUID(item_id)}/capabilities/" if item_id else "capabilities/"
        return ambiguity or await plane.request("GET", project_path(project) + suffix)

    @mcp.tool()
    async def save_discussion_result(
        intent: str,
        project_ref: str | None = None,
        title: str | None = None,
        description_markdown: str | None = None,
        decision_id: str | None = None,
        existing_work_item_id: str | None = None,
        expected_updated_at: str | None = None,
        workspace: str | None = None,
        work_item_type: str | None = None,
        append: bool = True,
    ):
        """Explicit archive only. First prepare_create/prepare_update, then commit its decision_id.

        Preparing does not write Plane. Commit exactly the returned decision ID;
        retry that ID after transport failures. Updates require a previously read
        version. Never archive exploratory discussion or auto-overwrite similar titles.
        """
        connection, _ = await plane.context()
        if intent == "commit":
            if not decision_id or any(
                v is not None
                for v in (
                    project_ref,
                    title,
                    description_markdown,
                    existing_work_item_id,
                    expected_updated_at,
                    workspace,
                    work_item_type,
                )
            ):
                raise ValueError("Commit takes only the prepared decision_id")
            data = plane.vault.decision(connection, str(uuid.UUID(decision_id)))
            # Always call Plane, even on replay, so revoked membership is never bypassed.
            return await plane.request("POST", data["path"], payload={**data["payload"], "decision_id": decision_id})
        if intent not in ("prepare_create", "prepare_update") or decision_id:
            raise ValueError("Use prepare_create, prepare_update or commit")
        if intent == "prepare_update" and (not existing_work_item_id or not expected_updated_at):
            raise ValueError("Updates require an explicit item ID and previously read version")
        if intent == "prepare_create" and (existing_work_item_id or expected_updated_at or not title):
            raise ValueError("Create requires title and no existing item")
        if title is not None and (not title.strip() or len(title) > 255):
            raise ValueError("Title must be 1–255 characters")
        if description_markdown is not None and len(description_markdown) > 50000:
            raise ValueError("Description too long")
        if title is None and description_markdown is None:
            raise ValueError("No explicit content")
        project, ambiguity = await plane.resolve(project_ref, workspace)
        if ambiguity:
            return ambiguity
        path = project_path(project) + "work-items/"
        if existing_work_item_id:
            path += str(uuid.UUID(existing_work_item_id)) + "/"
            await plane.request("GET", path)
        payload = {"append": append}
        for key, value in {
            "title": title,
            "description_markdown": description_markdown,
            "expected_updated_at": expected_updated_at,
            "work_item_type": work_item_type,
        }.items():
            if value is not None:
                payload[key] = value
        prepared = plane.vault.prepare(connection, {"path": path, "payload": payload})
        return {
            "status": "prepared",
            "decision_id": prepared,
            "project": project,
            "message": "No work item has been written. Commit this decision only for explicit user archive instructions.",
        }

    return mcp


def main():
    logging.getLogger("httpx").setLevel(logging.WARNING)
    vault = Vault(os.environ["GATEWAY_DB"], os.environ["GATEWAY_VAULT_KEY"])
    plane = Plane(os.environ["PLANE_URL"], os.environ["GATEWAY_SECRET"], vault, os.environ.get("PLANE_CA_FILE"))
    build_server(plane, os.environ["GATEWAY_ISSUER"], os.environ["GATEWAY_RESOURCE"]).run(transport="streamable-http")


if __name__ == "__main__":
    main()
