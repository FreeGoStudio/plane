/* eslint-disable no-await-in-loop -- Language-switch tests must exercise shared locale state sequentially. */
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { i18nInstance, initPromise } from "../src/core/instance";
import { translate } from "../src/core/translate";
import { getStateDisplayName } from "../src/state-display-name";

test("built-in names follow Chinese UI and restore English without mutating states", async () => {
  await initPromise;
  const states = [
    { name: "Backlog", group: "backlog" },
    { name: "Todo", group: "unstarted" },
    { name: "In Progress", group: "started" },
    { name: "Done", group: "completed" },
    { name: "Cancelled", group: "cancelled" },
  ];
  const original = structuredClone(states);
  for (const currentLocale of ["zh-CN", "en", "zh-TW", "zh-CN"] as const) {
    await i18nInstance.changeLanguage(currentLocale);
    const names = states.map((state) => getStateDisplayName(state, { t: translate, currentLocale }));
    if (currentLocale === "zh-CN") {
      assert.deepEqual(names, ["待办", "未开始", "进行中", "已完成", "已取消"]);
    } else if (currentLocale === "en") {
      assert.deepEqual(
        names,
        states.map((state) => state.name)
      );
    } else {
      assert.deepEqual(
        names,
        states.map((state) => translate(`workspace_projects.state.${state.group}`))
      );
      assert.notDeepEqual(
        names,
        states.map((state) => state.name)
      );
    }
  }
  assert.deepEqual(states, original);
});

test("renamed states, mismatched groups and unknown states retain their names", () => {
  for (const state of [
    { name: "待评审", group: "started" },
    { name: "Review", group: "started" },
    { name: "Done", group: "started" },
    { name: "done", group: "completed" },
    { name: "Custom", group: "custom" },
  ]) {
    assert.equal(getStateDisplayName(state, { t: translate, currentLocale: "zh-CN" }), state.name);
  }
});
