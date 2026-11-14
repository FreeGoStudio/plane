/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import { ProjectRepositoriesSettings } from "@/components/settings/project/repositories";
import type { Route } from "./+types/page";
export default function RepositorySettingsPage({ params }: Route.ComponentProps) {
  return (
    <ProjectRepositoriesSettings
      key={`${params.workspaceSlug}/${params.projectId}`}
      workspaceSlug={params.workspaceSlug}
      projectId={params.projectId}
    />
  );
}
