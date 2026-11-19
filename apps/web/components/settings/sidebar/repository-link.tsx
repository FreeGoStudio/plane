/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import useSWR from "swr";
import { useLocation, useSearchParams } from "react-router";
import { List } from "@makeplane/propel/components/list";
import { PagesOutline, ViewsOutline, ModuleOutline, LabelsOutline } from "@makeplane/propel/icons";
import { SettingsSidebarItem } from "./item";
import { SettingsSidebarSectionHeading } from "./section-heading";
import { repositorySections, selectedRepositorySection, type RepositoryBindings } from "../project/repository-sections";
import { repositoryBase, repositoryService, type Repository } from "@/services/repository.service";
import { API_BASE_URL } from "@plane/constants";
import { useTranslation } from "@plane/i18n";

/** Probe the session feature endpoint without retaining repository or credential data. */
async function repositoryFeatureAvailable(url: string): Promise<boolean> {
  const response = await fetch(url, { credentials: "include" });
  return response.ok;
}

/** Group project repository settings by purpose when repository access is enabled. */
export function RepositorySettingsLink(props: { workspaceSlug?: string; projectId?: string }) {
  const { t } = useTranslation();
  const { data: enabled } = useSWR(`${API_BASE_URL}/api/singularity/v1/repository-hosts/`, repositoryFeatureAvailable, {
    shouldRetryOnError: false,
  });
  const [params] = useSearchParams();
  const { pathname } = useLocation();
  const base = props.workspaceSlug && props.projectId ? repositoryBase(props.workspaceSlug, props.projectId) : null;
  const resolveTarget =
    enabled &&
    base &&
    params.has("repository") &&
    !repositorySections.some((section) => section === params.get("section"));
  const { data: rows } = useSWR<Repository[]>(resolveTarget ? base + "repositories/" : null, (url: string) =>
    repositoryService.read<Repository[]>(url)
  );
  const { data: bindings } = useSWR<RepositoryBindings>(
    resolveTarget ? base + "repository-bindings/" : null,
    (url: string) => repositoryService.read<RepositoryBindings>(url)
  );
  if (!enabled) return null;
  const project = props.workspaceSlug && props.projectId;
  if (!project) return null;
  const path = `/${encodeURIComponent(props.workspaceSlug!)}/settings/projects/${encodeURIComponent(props.projectId!)}/repositories/`;
  const selected = selectedRepositorySection(params, rows, bindings);
  const icons = {
    documentation: PagesOutline,
    prototype: ViewsOutline,
    development: ModuleOutline,
    reference: LabelsOutline,
  };
  return (
    <div className="shrink-0 py-3">
      <SettingsSidebarSectionHeading>{t("singularity_settings.repositories")}</SettingsSidebarSectionHeading>
      <List gap="px" aria-label={t("singularity_settings.repositories")}>
        {repositorySections.map((section) => (
          <SettingsSidebarItem
            key={section}
            as="link"
            href={`${path}?section=${section}`}
            isActive={pathname === path && selected === section}
            icon={icons[section]}
            label={t(`repository_ui.sections.${section}`)}
          />
        ))}
      </List>
    </div>
  );
}
