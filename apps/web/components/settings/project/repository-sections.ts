/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import type { Repository } from "@/services/repository.service";

export const repositorySections = ["documentation", "prototype", "development", "reference"] as const;
export type RepositorySection = (typeof repositorySections)[number];
export type RepositoryBindings = {
  revision: number;
  documentation_repository_id: string | null;
  prototype_repository_id: string | null;
};

export function repositorySection(row: Repository, bindings?: RepositoryBindings): RepositorySection {
  if (row.id === bindings?.documentation_repository_id) return "documentation";
  if (row.id === bindings?.prototype_repository_id) return "prototype";
  return repositorySections.includes(row.purpose as RepositorySection)
    ? (row.purpose as RepositorySection)
    : "reference";
}

/** Old repository/OAuth links still open the appropriate category. Explicit navigation wins. */
export function selectedRepositorySection(
  params: URLSearchParams,
  rows: Repository[] = [],
  bindings?: RepositoryBindings
): RepositorySection {
  const section = params.get("section");
  if (repositorySections.includes(section as RepositorySection)) return section as RepositorySection;
  const target = rows.find((row) => row.id === params.get("repository"));
  return target ? repositorySection(target, bindings) : "documentation";
}
