// Copyright (c) 2023-present Plane Software, Inc. and contributors
// SPDX-License-Identifier: AGPL-3.0-only
// See the LICENSE file for details.
import test from "node:test";
import assert from "node:assert/strict";
import {
  actionOptions,
  needsChoice,
  choicesComplete,
} from "../components/issues/issue-detail-widgets/sub-issues/wbs-update.ts";

const change = { id: "T1", target_id: "child", action: "update", task: { title: "New requirement" } };
test("started tasks require an explicit selection; unstarted tasks use the proposed action", () => {
  assert.equal(needsChoice(change, { stage: "started" }), true);
  assert.equal(needsChoice(change, { stage: "unstarted" }), false);
  assert.equal(choicesComplete([change], [{ id: "child", stage: "started" }], {}), false);
  assert.equal(choicesComplete([change], [{ id: "child", stage: "started" }], { T1: "append" }), true);
});
test("completed work cannot be overwritten or cancelled", () => {
  assert.deepEqual(actionOptions(change, { stage: "completed" }), ["append"]);
  assert.equal(choicesComplete([change], [{ id: "child", stage: "completed" }], { T1: "update" }), false);
});
test("cancellation can be replaced with explicit reviewed task content", () => {
  assert.deepEqual(actionOptions({ ...change, action: "cancel", task: null }, { stage: "started" }), [
    "keep",
    "update",
    "append",
    "cancel",
  ]);
  assert.equal(needsChoice({ ...change, action: "keep" }, { stage: "started" }), false);
});
