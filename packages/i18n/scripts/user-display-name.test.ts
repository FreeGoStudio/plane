/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { getUserDisplayName } from "../src/user-display-name";
import { i18nInstance, initPromise } from "../src/core/instance";

test("display identity resolves name, localized full name, then email without mutating data", async () => {
  await initPromise;
  const user = { display_name: "  小张  ", first_name: " 三 ", last_name: " 张 ", email: " person@example.com " };
  const original = structuredClone(user);
  await i18nInstance.changeLanguage("zh-CN");
  assert.equal(getUserDisplayName(user), "小张");
  assert.deepEqual(user, original);
  assert.equal(getUserDisplayName({ ...user, display_name: "  " }), "张三");
  await i18nInstance.changeLanguage("en");
  assert.equal(getUserDisplayName({ ...user, display_name: "" }), "三 张");
  assert.equal(
    getUserDisplayName({ display_name: "", first_name: " ", last_name: null, email: user.email }),
    "person@example.com"
  );
  await i18nInstance.changeLanguage("zh-TW");
  assert.equal(getUserDisplayName({ first_name: "娜娜", last_name: "歐陽" }), "歐陽娜娜");
  assert.equal(getUserDisplayName({ first_name: "明" }), "明");
  assert.equal(getUserDisplayName({ last_name: "陳" }), "陳");
});

test("partial public member records use only supplied fields and never stringify missing data", async () => {
  await initPromise;
  await i18nInstance.changeLanguage("zh-CN");
  assert.equal(getUserDisplayName({ member__display_name: "公开昵称" }), "公开昵称");
  assert.equal(
    getUserDisplayName({ member__display_name: " ", member__first_name: "三", member__last_name: "张" }),
    "张三"
  );
  assert.equal(getUserDisplayName({ member__email: "public@example.com" }), "public@example.com");
  for (const user of [undefined, null, {}, { display_name: "", first_name: null, last_name: " " }]) {
    assert.equal(getUserDisplayName(user), "");
  }
});
