import { act, cleanup, render } from "@testing-library/react";
import { expect, it } from "vitest";
import { LocalizedText, setLanguage, TranslationProvider } from "@plane/i18n";
import en from "../../../i18n/src/locales/en/common.json";
import zh from "../../../i18n/src/locales/zh-CN/common.json";

const tags = (text: string) => [...text.matchAll(/<([a-z]+)(?:\s*\/?)>/g)].map((match) => match[1]).sort();

it("keeps activity sentence slots and links intact in both languages", async () => {
  for (const key of Object.keys(en.work_item_activity) as (keyof typeof en.work_item_activity)[]) {
    expect(tags(zh.work_item_activity[key])).toEqual(tags(en.work_item_activity[key]));
  }
  for (const locale of ["zh-CN", "en"] as const) {
    // The shared locale must change sequentially before rendering each set of messages.
    // oxlint-disable-next-line no-await-in-loop
    await act(() => setLanguage(locale));
    for (const key of Object.keys(en.work_item_activity)) {
      const { container } = render(
        <LocalizedText
          messageKey={`work_item_activity.${key}`}
          components={{
            value: <a href="/original-value">{"Original <b>value</b>"}</a>,
            issue: <a href="/original-issue">ORIGINAL-123</a>,
          }}
        />,
        { wrapper: TranslationProvider }
      );
      expect(container.textContent).not.toContain("work_item_activity.");
      expect(container.textContent).not.toMatch(/<\/?(?:value|issue)/);
      if (locale === "zh-CN") expect(container.textContent).toMatch(/[\u4e00-\u9fff]/);
      for (const link of container.querySelectorAll("a"))
        expect(["/original-value", "/original-issue"]).toContain(link.getAttribute("href"));
      expect(container.querySelector("b")).toBeNull();
      cleanup();
    }
  }
});
