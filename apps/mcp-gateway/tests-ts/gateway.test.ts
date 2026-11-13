// Copyright (c) 2023-present Plane Software, Inc. and contributors
// SPDX-License-Identifier: AGPL-3.0-only
// See the LICENSE file for details.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomBytes } from "node:crypto";
import { Vault, canonical, Cipher } from "../src/vault.js";
import { Plane, PlaneError, invoke, type Transport } from "../src/core.js";
import { createGateway, tools } from "../src/main.js";
const id = "11111111-1111-4111-8111-111111111111",
  decision = "22222222-2222-4222-8222-222222222222";
function fixture() {
  const path = join(mkdtempSync(join(tmpdir(), "singularity-ts-")), "vault.sqlite"),
    key = randomBytes(32).toString("base64url"),
    vault = new Vault(path, key);
  const state = { actor: "alice", revoked: false, status: 200, ambiguous: false, fail: false };
  const calls: { url: URL; method: string; headers: Record<string, string>; body?: string }[] = [];
  const send: Transport = async (url, method, headers, body) => {
    calls.push({ url, method, headers, body });
    if (url.pathname.endsWith("exchange/"))
      return {
        status: state.revoked ? 401 : 200,
        data: {
          connection_id: state.actor,
          subject: state.actor,
          scope: "projects:read workitems:read workitems:write capabilities:read",
          expires_at: Date.now() / 1000 + 600,
          access_token: "downstream-test",
          expires_in: 300,
        },
      };
    if (state.fail) throw new Error("upstream secret must not leak");
    if (state.status !== 200) return { status: state.status, data: { secret: "upstream secret must not leak" } };
    const project = { id, workspace: "test", name: "POS", identifier: "POS" };
    if (url.pathname.endsWith("projects/"))
      return { status: 200, data: { results: state.ambiguous ? [project, project] : [project], next_offset: null } };
    if (url.pathname.endsWith("prepare/")) return { status: 202, data: { decision_id: decision } };
    return { status: 200, data: { id, status: method === "POST" ? "created" : "read" } };
  };
  const plane = new Plane("https://plane.test", "exchange-test", vault, send);
  return { path, key, vault, state, calls, plane };
}
const prepare = {
  intent: "prepare_create",
  project_ref: "POS",
  title: "讨论 😀",
  description_markdown: "Private discussion",
  workspace: "test",
};
test("exact five tools with no secret/user/admin parameters", () => {
  assert.equal(tools.length, 5);
  for (const tool of tools) {
    assert.doesNotMatch(JSON.stringify(tool.inputSchema), /user_id|access_token|password/);
  }
  assert(!tools.some((t) => t.name.includes("delete")));
});
test("prepare persists encrypted, retries across restart and binds connection", async () => {
  const f = fixture();
  const result = await invoke(f.plane, "test-bearer", "save_discussion_result", prepare);
  assert.equal(result.decision_id, decision);
  assert.equal(f.calls.filter((c) => c.method === "POST" && !c.url.pathname.includes("exchange")).length, 1);
  assert(!readFileSync(f.path).includes(Buffer.from("Private discussion")));
  f.vault.close();
  const restored = new Vault(f.path, f.key);
  assert.equal(
    restored.prepared("alice", {
      path: `workspaces/test/projects/${id}/work-items/`,
      payload: { append: true, title: prepare.title, description_markdown: prepare.description_markdown },
      prepared_by: "plane",
    }),
    decision
  );
  assert.throws(() => restored.decision("bob", decision));
  restored.close();
});
test("commit always reauthorizes; revocation cannot use stored data", async () => {
  const f = fixture();
  await invoke(f.plane, "bearer", "save_discussion_result", prepare);
  await invoke(f.plane, "bearer", "save_discussion_result", { intent: "commit", decision_id: decision });
  const call = f.calls.find((c) => c.method === "POST" && c.url.pathname.endsWith("work-items/"));
  assert.equal(call?.headers.Authorization, "Bearer downstream-test");
  assert(!call?.body?.includes("bearer"));
  f.state.revoked = true;
  await assert.rejects(
    () => invoke(f.plane, "bearer", "save_discussion_result", { intent: "commit", decision_id: decision }),
    PlaneError
  );
  f.vault.close();
});
test("ambiguous projects do not prepare or write", async () => {
  const f = fixture();
  f.state.ambiguous = true;
  assert.equal((await invoke(f.plane, "x", "save_discussion_result", prepare)).status, "ambiguous");
  assert(!f.calls.some((c) => c.url.pathname.endsWith("prepare/")));
  f.vault.close();
});
test("forged identities, arbitrary IDs and missing update versions rejected", async () => {
  const f = fixture();
  for (const args of [
    { ...prepare, user_id: "other" },
    { intent: "commit", decision_id: decision },
    { intent: "prepare_update", project_ref: "POS", title: "x", existing_work_item_id: id },
  ])
    // Sequential cases share one vault and a request history.
    // eslint-disable-next-line no-await-in-loop
    await assert.rejects(() => invoke(f.plane, "x", "save_discussion_result", args));
  await invoke(f.plane, "x", "search_work_items", { project_ref: "http://169.254.169.254/secret" });
  assert(f.calls.every((c) => c.url.host === "plane.test"));
  f.vault.close();
});
for (const status of [401, 402, 403, 404, 409, 429, 500])
  test(`upstream ${status} is sanitized without fallback`, async () => {
    const f = fixture();
    f.state.status = status;
    await assert.rejects(
      () => invoke(f.plane, "x", "list_accessible_projects", {}),
      (error: unknown) => error instanceof PlaneError && error.status === status && !error.message.includes("secret")
    );
    f.vault.close();
  });
test("response loss instructs same-decision retry", async () => {
  const f = fixture();
  f.state.fail = true;
  await assert.rejects(
    () => f.plane.request("x", "POST", "workspaces/test/", {}),
    /outcome_unknown_retry_same_decision/
  );
  f.vault.close();
});
test("cipher authenticates tampering and preserves Python ASCII JSON", () => {
  const cipher = new Cipher(randomBytes(32).toString("base64url"));
  const value = { z: "😀", a: "中" };
  assert.equal(canonical(value), '{"a": "\\u4e2d", "z": "\\ud83d\\ude00"}');
  const encoded = cipher.encode(value);
  assert.deepEqual(cipher.decode(encoded), value);
  encoded[50] = encoded[50] === 65 ? 66 : 65;
  assert.throws(() => cipher.decode(encoded));
});
test("official SDK HTTP initializes, lists tools and rejects revoked/missing auth", async () => {
  const f = fixture(),
    server = createGateway(f.plane, "http://localhost", "http://localhost/mcp");
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert(address && typeof address !== "string");
  const base = `http://127.0.0.1:${address.port}`;
  const rpc = (method: string, params: unknown, auth = true) =>
    fetch(base + "/mcp", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json, text/event-stream",
        ...(auth ? { Authorization: "Bearer test" } : {}),
      },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
    });
  try {
    assert.equal((await rpc("tools/list", {}, false)).status, 401);
    const init = await rpc("initialize", {
      protocolVersion: "2025-06-18",
      capabilities: {},
      clientInfo: { name: "test", version: "1" },
    });
    assert.equal(init.status, 200);
    const listed = await rpc("tools/list", {});
    assert.equal((await listed.json()).result.tools.length, 5);
    const call = await rpc("tools/call", { name: "list_accessible_projects", arguments: {} });
    assert.equal((await call.json()).result.structuredContent.results.length, 1);
    f.state.revoked = true;
    assert.equal((await rpc("tools/list", {})).status, 401);
    assert.equal(
      (await fetch(base + "/mcp", { method: "POST", headers: { Origin: "https://evil.test" } })).status,
      403
    );
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
    f.vault.close();
  }
});
