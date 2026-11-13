// Copyright (c) 2023-present Plane Software, Inc. and contributors
// SPDX-License-Identifier: AGPL-3.0-only
// See the LICENSE file for details.
import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { Vault } from "../src/vault.js";
const root = process.argv[2];
const fixture = JSON.parse(readFileSync(join(root, "fixture.json"), "utf8")) as {
  key: string;
  pending: unknown;
  id: string;
};
const vault = new Vault(join(root, "vault.sqlite"), fixture.key);
assert.equal(vault.prepared("compat-user", fixture.pending), fixture.id);
assert.deepEqual(vault.decision("compat-user", fixture.id), fixture.pending);
const id = "33333333-3333-4333-8333-333333333333",
  data = { ...(fixture.pending as object), extra: "TypeScript → Python 😀" };
vault.prepare("compat-user", data, id);
vault.record("compat-user", "GET", 200);
vault.close();
writeFileSync(join(root, "typescript.json"), JSON.stringify({ id, data }));
console.log("Python-created decisions and Unicode fingerprints read by TypeScript.");
