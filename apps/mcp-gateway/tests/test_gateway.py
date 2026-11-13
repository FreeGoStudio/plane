# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from cryptography.fernet import Fernet
from gateway import Vault, Plane, PlaneError, Verifier, build_server


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.key = Fernet.generate_key()
        self.db = str(Path(self.tmp.name) / "vault.sqlite")
        self.vault = Vault(self.db, self.key)
        self.requests = []
        self.status = 200
        self.project = {
            "id": "11111111-1111-1111-1111-111111111111",
            "workspace": "test",
            "name": "POS",
            "identifier": "POS",
        }
        self.projects = [self.project]
        self.identity = "alice"
        self.revoked = False

        def handle(request):
            self.requests.append(request)
            if request.url.path.endswith("exchange/"):
                if self.revoked:
                    return httpx.Response(401)
                return httpx.Response(
                    200,
                    json={
                        "scope": "projects:read workitems:read workitems:write",
                        "expires_at": 9999999999,
                        "connection_id": self.identity,
                        "subject": self.identity,
                        "access_token": "private-plane-token",
                        "refresh_token": "private-plane-refresh",
                        "expires_in": 300,
                    },
                )
            if self.status != 200:
                return httpx.Response(self.status, json={"secret": "must not leak"})
            if request.url.path.endswith("projects/"):
                return httpx.Response(200, json={"results": self.projects, "next_offset": None})
            if request.url.path.endswith("prepare/"):
                return httpx.Response(
                    202, json={"status": "prepared", "decision_id": "33333333-3333-3333-3333-333333333333"}
                )
            return httpx.Response(200, json={"status": "created", "id": "item-1"})

        self.plane = Plane("https://plane.test", "gateway-secret", self.vault, transport=httpx.MockTransport(handle))
        self.context = patch("gateway.get_access_token", return_value=SimpleNamespace(token="gateway-token"))
        self.context.start()
        self.mcp = build_server(self.plane, "https://plane.test", "https://plane.test/mcp")

    async def asyncTearDown(self):
        self.context.stop()
        await self.plane.client.aclose()
        self.tmp.cleanup()

    async def call(self, name, args):
        result = await self.mcp.call_tool(name, args)
        if isinstance(result, tuple):
            return result[1]
        return json.loads(result[0].text)

    async def test_exact_five_tools_and_no_delete(self):
        tools = await self.mcp.list_tools()
        self.assertEqual(
            {t.name for t in tools},
            {
                "list_accessible_projects",
                "search_work_items",
                "get_work_item",
                "save_discussion_result",
                "get_my_capabilities",
            },
        )
        with self.assertRaises(Exception):
            await self.call("delete_work_item", {})

    async def test_prepare_replay_is_server_owned_and_encrypted(self):
        args = {"intent": "prepare_create", "project_ref": "POS", "title": "Sensitive discussion"}
        first, second = await asyncio.gather(
            self.call("save_discussion_result", args), self.call("save_discussion_result", args)
        )
        self.assertEqual(first["decision_id"], second["decision_id"])
        self.assertFalse(
            any(
                r.method == "POST" and "/api/" in r.url.path and not r.url.path.endswith("prepare/")
                for r in self.requests
            )
        )
        self.assertEqual(first["decision_id"], "33333333-3333-3333-3333-333333333333")
        self.assertNotIn(b"Sensitive discussion", Path(self.db).read_bytes())
        self.assertNotIn(b"private-plane-token", Path(self.db).read_bytes())
        reopened = Vault(self.db, self.key)
        self.assertEqual(reopened.decision("alice", first["decision_id"])["payload"]["title"], "Sensitive discussion")
        result = await self.call("save_discussion_result", {"intent": "commit", "decision_id": first["decision_id"]})
        self.assertEqual(result["status"], "created")
        self.identity = "bob"
        with self.assertRaises(Exception):
            await self.call("save_discussion_result", {"intent": "commit", "decision_id": first["decision_id"]})

    async def test_revoked_connection_never_uses_cached_plane_token(self):
        await self.plane.context()
        self.revoked = True
        with self.assertRaises(PlaneError):
            await self.plane.request("GET", "projects/")
        self.assertIsNone(await Verifier(self.plane, "https://plane.test/mcp").verify_token("gateway-token"))

    async def test_ambiguous_project_never_writes(self):
        self.projects = [self.project, {**self.project, "id": "22222222-2222-2222-2222-222222222222"}]
        result = await self.call(
            "save_discussion_result", {"intent": "prepare_create", "project_ref": "POS", "title": "test"}
        )
        self.assertEqual(result["status"], "ambiguous")
        self.assertFalse(any(r.method == "POST" and "/api/" in r.url.path for r in self.requests))

    async def test_errors_include_402_without_fallback(self):
        for status in (401, 402, 403, 404, 409, 429, 500):
            self.status = status
            with self.assertRaises(PlaneError) as caught:
                await self.plane.request("GET", "projects/")
            self.assertEqual(caught.exception.status, status)
            self.assertNotIn("must not leak", str(caught.exception))
        self.assertFalse(any("X-Api-Key" in r.headers for r in self.requests))

    async def test_unknown_decision_update_without_version_and_arbitrary_url_rejected(self):
        for args in (
            {"intent": "commit", "decision_id": "11111111-1111-1111-1111-111111111111"},
            {"intent": "prepare_update", "project_ref": "POS", "title": "test"},
        ):
            with self.assertRaises(Exception):
                await self.call("save_discussion_result", args)
        await self.call("list_accessible_projects", {"search": "http://169.254.169.254/metadata"})
        self.assertTrue(all(r.url.host == "plane.test" for r in self.requests))


if __name__ == "__main__":
    unittest.main()
