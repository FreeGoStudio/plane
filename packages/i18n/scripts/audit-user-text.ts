import fs from "node:fs";
import path from "node:path";
import * as ts from "typescript";

// Candidates require human review: brands, examples and technical identifiers are not translation defects.
const root = path.resolve(import.meta.dirname, "../../..");
const roots = ["apps/web", "apps/admin", "apps/space", "packages/editor/src", "packages/blocks/src"];
const skip = new Set(["node_modules", "dist", "build", ".react-router", ".turbo", "assets", "public", "__tests__"]);
const attributes = new Set(["title", "label", "description", "placeholder", "alt", "aria-label", "tooltip", "trigger"]);
const properties = new Set(["title", "label", "description", "placeholder", "message"]);
const candidates: { file: string; line: number; kind: string; text: string }[] = [];

function scan(directory: string) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    if (skip.has(entry.name)) continue;
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      scan(filename);
      continue;
    }
    if (!/\.[jt]sx?$/.test(filename) || /\.(test|spec)\./.test(filename)) continue;
    const source = ts.createSourceFile(filename, fs.readFileSync(filename, "utf8"), ts.ScriptTarget.Latest, true);
    function visit(node: ts.Node) {
      let text: string | undefined;
      let kind = "";
      if (ts.isJsxText(node)) {
        text = node.text;
        kind = "jsx-text";
      } else if (
        ts.isStringLiteral(node) &&
        ts.isJsxAttribute(node.parent) &&
        attributes.has(node.parent.name.getText(source))
      ) {
        text = node.text;
        kind = "jsx-attribute";
      } else if (
        ts.isStringLiteral(node) &&
        ts.isPropertyAssignment(node.parent) &&
        properties.has(node.parent.name.getText(source))
      ) {
        text = node.text;
        kind = "display-property";
      }
      text = text?.trim().replace(/\s+/g, " ");
      if (text && /[A-Za-z]{2}/.test(text) && !/[\u4e00-\u9fff]/.test(text)) {
        candidates.push({
          file: path.relative(root, filename).replaceAll("\\", "/"),
          line: source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1,
          kind,
          text,
        });
      }
      ts.forEachChild(node, visit);
    }
    visit(source);
  }
}

for (const directory of roots) scan(path.join(root, directory));
candidates.sort((a, b) => a.file.localeCompare(b.file) || a.line - b.line);
const output = path.join(root, "docs/localization/english-candidates.json");
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(
  output,
  JSON.stringify(
    {
      description:
        "Static review candidates, not a translation completeness score. Excludes dynamic text, backend messages, email templates and user data.",
      candidates,
    },
    null,
    2
  ) + "\n"
);
for (const directory of roots)
  console.log(`${directory}: ${candidates.filter((item) => item.file.startsWith(directory + "/")).length}`);
