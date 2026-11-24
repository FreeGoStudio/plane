// Copyright (c) 2023-present Plane Software, Inc. and contributors
// SPDX-License-Identifier: AGPL-3.0-only
// See the LICENSE file for details.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { wbsMessage } from "../components/issues/issue-detail-widgets/sub-issues/wbs-messages.ts";

test("WBS server reasons are translated across response shapes", () => {
  const expected = wbsMessage("PRD changed; update WBS again");
  assert.notEqual(expected.key, "wbs.server_error_unknown");
  assert.deepEqual(wbsMessage({ detail: "PRD changed; update WBS again" }), expected);
  assert.deepEqual(wbsMessage(["PRD changed; update WBS again"]), expected);
});
test("missing PRD retains its exact path as a translation parameter", () => {
  assert.equal(
    wbsMessage(
      "Primary prd.md is missing or unreadable at requirements/KIOSK-1/prd.md; no alternative file was selected"
    ).params.path,
    "requirements/KIOSK-1/prd.md"
  );
});
test("unknown and nested validation errors use a Chinese-capable fallback without losing diagnostics", () => {
  const error = { task: ["Unexpected condition"] };
  assert.equal(wbsMessage(error).key, "wbs.server_error_unknown");
  assert.equal(wbsMessage(error).details, JSON.stringify(error));
});
test("timeout and task dependency failures have distinct actionable messages", () => {
  assert.notEqual(wbsMessage("ReadTimeout").key, wbsMessage("Invalid task references: unknown task dependency").key);
  assert.notEqual(wbsMessage("ReadTimeout").key, "wbs.server_error_unknown");
});

test("all fixed WBS validation and permission messages have translations in every locale", () => {
  for (const file of ["wbs.py", "wbs_update.py", "wbs_generation.py"]) {
    const source = readFileSync(new URL(`../../api/plane/singularity/${file}`, import.meta.url), "utf8");
    for (const [, message] of source.matchAll(
      /raise (?:WbsConflict|ValidationError|PermissionDenied|ValueError)\(\s*"([^"]+)"/g
    )) {
      const translated = wbsMessage(message);
      assert.notEqual(translated.key, "wbs.server_error_unknown", message);
      const root = new URL("../../../packages/i18n/src/locales/", import.meta.url);
      for (const locale of readdirSync(root, { withFileTypes: true }).filter((item) => item.isDirectory())) {
        const json = JSON.parse(readFileSync(new URL(`${locale.name}/work-item.json`, root), "utf8"));
        assert.ok(json.wbs[translated.key.slice(4)], `${locale.name}: ${message}`);
        if (locale.name === "zh-CN") assert.match(json.wbs[translated.key.slice(4)], /[\u4e00-\u9fff]/);
      }
    }
  }
});
