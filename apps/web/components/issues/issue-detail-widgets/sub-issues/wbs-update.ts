// Copyright (c) 2023-present Plane Software, Inc. and contributors
// SPDX-License-Identifier: AGPL-3.0-only
// See the LICENSE file for details.

export type WbsTask = {
  id: string;
  title: string;
  role: string;
  criteria: string[];
  scope: string;
  deliverable: string;
  dependencies: string[];
  acceptance: string;
};
export type ChangeAction = "keep" | "create" | "update" | "cancel" | "append";
export type WbsChange = {
  id: string;
  target_id: string | null;
  action: ChangeAction;
  basis: string;
  impact: string;
  task: WbsTask | null;
};
export type WbsChild = { id: string; name: string; description_html: string; stage: string };

export function needsChoice(change: WbsChange, child?: WbsChild): boolean {
  return !!change.target_id && child?.stage !== "unstarted" && change.action !== "keep";
}
export function actionOptions(change: WbsChange, child?: WbsChild): ChangeAction[] {
  if (child?.stage === "completed") return ["append"];
  return change.task ? ["update", "append", "cancel"] : ["keep", "update", "append", "cancel"];
}
export function choicesComplete(
  changes: WbsChange[],
  children: WbsChild[],
  choices: Record<string, ChangeAction>,
  replacements: Record<string, WbsTask> = {}
): boolean {
  return changes.every((change) => {
    const child = children.find((item) => item.id === change.target_id);
    if (!needsChoice(change, child)) return true;
    if (!actionOptions(change, child).includes(choices[change.id])) return false;
    if (!change.task && ["update", "append"].includes(choices[change.id])) {
      const task = replacements[change.id];
      return (
        !!task &&
        [task.title, task.role, task.scope, task.deliverable, task.acceptance].every((value) => value.trim()) &&
        task.criteria.length > 0
      );
    }
    return true;
  });
}
