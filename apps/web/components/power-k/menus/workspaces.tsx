/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import React from "react";
// plane imports
import { WorkspaceAvatar } from "@makeplane/propel/components/workspace-avatar";
import type { IWorkspace } from "@plane/types";
import { getFileURL } from "@plane/utils";
// local imports
import { PowerKMenuBuilder } from "./builder";

type Props = {
  workspaces: IWorkspace[];
  onSelect: (workspace: IWorkspace) => void;
};

export function PowerKWorkspacesMenu({ workspaces, onSelect }: Props) {
  const { t } = useTranslation();

  return (
    <PowerKMenuBuilder
      items={workspaces}
      getKey={(workspace) => workspace.id}
      getIconNode={(workspace) => (
        <WorkspaceAvatar size="sm" src={getFileURL(workspace.logo_url ?? "")} alt={workspace.name} />
      )}
      getValue={(workspace) => workspace.name}
      getLabel={(workspace) => workspace.name}
      onSelect={onSelect}
      emptyText={t("web_ui.no_workspaces_found")}
    />
  );
}
