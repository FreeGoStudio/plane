/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import { API_BASE_URL } from "@plane/constants";
import { APIService } from "./api.service";

export type Repository = {
  id: string;
  instance_id: string;
  instance_name: string;
  provider: string;
  path: string;
  purpose: string;
  default_branch: string;
  enabled: boolean;
  credential_id: string | null;
  anonymous: boolean;
};
export type ConnectionInfo = {
  csrf_token: string;
  can_manage: boolean;
  hosts: { id: string; name: string; provider: string; oauth_available: boolean }[];
  credentials: {
    id: string;
    instance_id: string;
    label: string;
    external_actor_label: string;
    expires_at: string | null;
  }[];
};
export type RepositoryContent = {
  commit_sha: string;
  path: string;
  source_url: string;
  content?: string;
  entries?: { name: string; path: string; type: string }[];
  next_page?: number | null;
};
class RepositoryService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }
  async read<T>(path: string): Promise<T> {
    return this.get(path).then((r) => r.data);
  }
  async write<T = unknown>(
    path: string,
    method: "POST" | "DELETE" | "PATCH",
    csrf: string,
    data?: unknown
  ): Promise<T> {
    return this.request({ url: path, method, data, headers: { "X-CSRFToken": csrf } }).then((r) => r.data);
  }
}
export const repositoryService = new RepositoryService();
export const repositoryBase = (workspace: string, project: string) =>
  `/api/singularity/v1/workspaces/${encodeURIComponent(workspace)}/projects/${project}/`;
