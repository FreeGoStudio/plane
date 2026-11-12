import { setLanguage } from "@plane/i18n";
import { describe, expect, it } from "vitest";
import { EFileError, isFileValid } from "../../helpers/file";
import { getSlashCommandFilteredSections } from "../slash-commands/command-items-list";

describe("editor localization", () => {
  it("searches Chinese labels and English aliases without changing command identifiers", async () => {
    const options = getSlashCommandFilteredSections({ disabledExtensions: [], flaggedExtensions: [] });
    await setLanguage("en");
    const english = options({ query: "" }).flatMap((section) => section.items.map((item) => item.key));
    await setLanguage("zh-CN");
    expect(options({ query: "" }).flatMap((section) => section.items.map((item) => item.key))).toEqual(english);
    expect(
      options({ query: "标题" })
        .flatMap((section) => section.items)
        .some((item) => item.commandKey === "h1")
    ).toBe(true);
    expect(
      options({ query: "paragraph" })
        .flatMap((section) => section.items)
        .some((item) => item.commandKey === "text")
    ).toBe(true);
  });

  it("localizes validation while retaining error codes and file names", async () => {
    const file = new File(["original"], "用户内容.txt", { type: "text/plain" });
    const errors: [EFileError, string][] = [];
    const check = () =>
      isFileValid({
        file,
        acceptedMimeTypes: ["image/png"],
        maxFileSize: 1024,
        onError: (code, message) => errors.push([code, message]),
      });
    await setLanguage("zh-CN");
    expect(check()).toBe(false);
    expect(errors.pop()).toEqual([EFileError.INVALID_FILE_TYPE, "文件类型无效。"]);
    await setLanguage("en");
    expect(check()).toBe(false);
    expect(errors.pop()).toEqual([EFileError.INVALID_FILE_TYPE, "Invalid file type."]);
    expect(file.name).toBe("用户内容.txt");
  });
});
