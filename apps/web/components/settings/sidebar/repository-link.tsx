/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import useSWR from "swr";
import { Link } from "react-router";
import { API_BASE_URL } from "@plane/constants";
import { useTranslation } from "@plane/i18n";

/** Probe the session feature endpoint without retaining repository or credential data. */
async function repositoryFeatureAvailable(url: string): Promise<boolean> {
  const response = await fetch(url, { credentials: "include" });
  return response.ok;
}

/** Navigate to the server-owned configuration UI only when repository access is enabled. */
export function RepositorySettingsLink(props: { workspaceSlug?: string; projectId?: string }) {
  const { t } = useTranslation();
  const { data: enabled } = useSWR(`${API_BASE_URL}/api/singularity/v1/repository-hosts/`, repositoryFeatureAvailable, {
    shouldRetryOnError: false,
  });
  if (!enabled) return null;
  const project = props.workspaceSlug && props.projectId;
  if (!project) return null;
  const path = `/${encodeURIComponent(props.workspaceSlug!)}/settings/projects/${encodeURIComponent(props.projectId!)}/repositories/`;
  return (
    <Link to={path} className="text-sm block rounded-sm px-3 py-2 text-secondary hover:bg-layer-2 hover:text-primary">
      {t(project ? "singularity_settings.repositories" : "singularity_settings.repository_access")}
    </Link>
  );
}
