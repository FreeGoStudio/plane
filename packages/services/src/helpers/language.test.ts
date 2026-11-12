import { afterEach, describe, expect, it, vi } from "vitest";
import { getRequestLanguage } from "./language";

afterEach(() => vi.unstubAllGlobals());

describe("request language", () => {
  it("does not impose a browser preference on server-side requests", () => {
    expect(getRequestLanguage()).toBeUndefined();
  });
  it("reads the current saved preference on every request", () => {
    const getItem = vi.fn().mockReturnValueOnce("en").mockReturnValueOnce("zh-CN");
    vi.stubGlobal("window", { localStorage: { getItem } });
    expect(getRequestLanguage()).toBe("en");
    expect(getRequestLanguage()).toBe("zh-CN");
  });
  it("uses the document language when browser storage is unavailable", () => {
    vi.stubGlobal("window", {
      get localStorage() {
        throw new Error("storage blocked");
      },
    });
    vi.stubGlobal("document", { documentElement: { lang: "zh-CN" } });
    expect(getRequestLanguage()).toBe("zh-CN");
  });
});
