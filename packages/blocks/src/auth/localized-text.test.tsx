import { act, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { LocalizedText, setLanguage, TranslationProvider } from "@plane/i18n";

it("reorders rich sentences without changing linked user content or URLs", async () => {
  await setLanguage("zh-CN");
  const { container } = render(
    <LocalizedText
      messageKey="work_item_activity.cycle_added"
      components={{ value: <a href="/workspace/project/cycle-original">{"原名 <b>English</b>"}</a> }}
    />,
    { wrapper: TranslationProvider }
  );
  expect(container.textContent).toBe("将此工作项加入周期 原名 <b>English</b>。");
  const link = screen.getByRole("link");
  expect(link.getAttribute("href")).toBe("/workspace/project/cycle-original");
  expect(link.querySelector("b")).toBeNull();
  await act(() => setLanguage("en"));
  expect(container.textContent).toBe("added this work item to cycle 原名 <b>English</b>.");
  expect(screen.getByRole("link").getAttribute("href")).toBe("/workspace/project/cycle-original");
});
