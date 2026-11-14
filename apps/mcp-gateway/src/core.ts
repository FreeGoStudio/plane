// Copyright (c) 2023-present Plane Software, Inc. and contributors
// SPDX-License-Identifier: AGPL-3.0-only
// See the LICENSE file for details.
import https from "node:https";
import { z } from "zod";
import { Vault } from "./vault.js";
export class PlaneError extends Error {
  constructor(
    readonly status: number,
    readonly code: string
  ) {
    super(`Plane request failed: ${status} ${code}`);
  }
}
export type Transport = (
  url: URL,
  method: string,
  headers: Record<string, string>,
  body?: string
) => Promise<{ status: number; data: unknown }>;
/** Fixed HTTPS authority, no redirects or environment proxies, bounded responses. */
export function transport(ca?: string): Transport {
  return (url, method, headers, body) =>
    new Promise((resolve, reject) => {
      const req = https.request(url, { method, headers, ca, timeout: 20000 }, (res) => {
        const chunks: Buffer[] = [];
        let size = 0;
        res.on("data", (chunk: Buffer) => {
          size += chunk.length;
          if (size > 5 * 1024 * 1024) res.destroy(new Error("Response too large"));
          else chunks.push(chunk);
        });
        res.on("error", reject);
        res.on("end", () => {
          try {
            resolve({ status: res.statusCode ?? 503, data: JSON.parse(Buffer.concat(chunks).toString() || "{}") });
          } catch {
            // JSON parsing can fail before resolve is called.
            // eslint-disable-next-line promise/no-multiple-resolved
            reject(new Error("Invalid upstream response"));
          }
        });
      });
      req.on("timeout", () => req.destroy(new Error("Request timed out")));
      req.on("error", reject);
      req.end(body);
    });
}
const identitySchema = z.object({
  connection_id: z.string(),
  subject: z.string(),
  scope: z.string(),
  expires_at: z.number(),
});
const tokenSchema = z.object({ access_token: z.string(), expires_in: z.number() });
const projectSchema = z
  .object({ id: z.uuid(), workspace: z.string(), name: z.string(), identifier: z.string() })
  .passthrough();
type Project = z.infer<typeof projectSchema>;
const pageSchema = z.object({ results: z.array(projectSchema), next_offset: z.number().nullable() });
const recordSchema = z.record(z.string(), z.unknown());
/** Every business call rechecks the originating grant, then obtains a distinct audience token. */
export class Plane {
  constructor(
    readonly base: string,
    readonly secret: string,
    readonly vault: Vault,
    readonly send: Transport,
    readonly publicBase: string = base
  ) {
    const url = new URL(base);
    if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash)
      throw new Error("Invalid Plane authority");
  }
  async exchange(bearer: string, inspect = false) {
    let response;
    try {
      response = await this.send(
        new URL("/auth/singularity/exchange/", this.base),
        "POST",
        { "X-Gateway-Secret": this.secret, "Content-Type": "application/x-www-form-urlencoded" },
        new URLSearchParams({ subject_token: bearer, inspect: inspect ? "1" : "0" }).toString()
      );
    } catch {
      throw new PlaneError(503, "authorization_unavailable");
    }
    if (response.status !== 200) throw new PlaneError(response.status, "authorization_failed");
    return response.data;
  }
  async identity(bearer: string) {
    const result = identitySchema.safeParse(await this.exchange(bearer, true));
    if (!result.success || result.data.expires_at <= Date.now() / 1000) throw new PlaneError(401, "invalid_identity");
    return result.data;
  }
  async request(
    bearer: string,
    method: string,
    path: string,
    payload?: unknown,
    params: Record<string, string | number> = {}
  ): Promise<Record<string, unknown>> {
    const identity = await this.identity(bearer);
    const token = tokenSchema.parse(await this.exchange(bearer));
    if (!/^[a-zA-Z0-9%_./-]+$/.test(path) || path.includes("..") || path.startsWith("/"))
      throw new Error("Invalid resource path");
    const url = new URL("/api/singularity/v1/" + path, this.base);
    for (const [key, value] of Object.entries(params)) url.searchParams.set(key, String(value));
    let response;
    try {
      response = await this.send(
        url,
        method,
        { Authorization: `Bearer ${token.access_token}`, "Content-Type": "application/json" },
        payload === undefined ? undefined : JSON.stringify(payload)
      );
    } catch {
      this.vault.record(identity.connection_id, method, 503);
      throw new PlaneError(503, method === "POST" ? "outcome_unknown_retry_same_decision" : "unavailable");
    }
    this.vault.record(identity.connection_id, method, response.status);
    if (response.status >= 400 && /\/ai-repositories\//.test(path)) {
      const upstream = z
        .object({
          error: z.enum([
            "upstream_access_denied",
            "upstream_resource_invisible",
            "upstream_unavailable",
            "upstream_rate_limited",
            "file_too_large",
            "binary_file",
            "lfs_file",
          ]),
        })
        .safeParse(response.data);
      if (upstream.success) return { status: "read_failed", error: upstream.data.error };
    }
    if (response.status === 403 && /\/ai-repositories\//.test(path)) {
      const challenge = z
        .object({
          error: z.literal("repository_authorization_required"),
          status: z.literal("authorization_required"),
          authorization_url: z.url(),
          message: z.string(),
        })
        .safeParse(response.data);
      if (challenge.success && new URL(challenge.data.authorization_url).origin === new URL(this.publicBase).origin)
        return challenge.data;
    }
    if (response.status >= 300)
      throw new PlaneError(
        response.status,
        (
          {
            401: "reauthorize",
            402: "unsupported_capability",
            403: "permission_or_scope_denied",
            404: "not_found_or_invisible",
            409: "conflict",
            429: "rate_limited",
          } as Record<number, string>
        )[response.status] ?? "request_rejected"
      );
    return recordSchema.parse(response.data);
  }
  async resolve(
    bearer: string,
    reference: string,
    workspace?: string | null
  ): Promise<{ project?: Project; ambiguity?: Record<string, unknown> }> {
    const candidates: Project[] = [];
    let offset: number | null = 0;
    do {
      const page = pageSchema.parse(
        // Pagination requires the preceding response offset.
        // eslint-disable-next-line no-await-in-loop
        await this.request(bearer, "GET", "projects/", undefined, {
          search: reference,
          offset,
          ...(workspace ? { workspace } : {}),
        })
      );
      candidates.push(...page.results);
      if (page.next_offset !== null && page.next_offset <= offset) throw new PlaneError(503, "invalid_pagination");
      offset = page.next_offset;
    } while (offset !== null);
    const exact = candidates.filter((p) =>
      [p.id, p.name, p.identifier].some((v) => v.toLowerCase() === reference.toLowerCase())
    );
    const matches = exact.length ? exact : candidates;
    return matches.length === 1
      ? { project: matches[0] }
      : { ambiguity: { status: matches.length ? "ambiguous" : "not_found", candidates: matches } };
  }
}
const nullableString = z.string().nullable().optional();
const reference = z.string().min(1).max(255);
export const inputs = {
  list_project_repositories: z.object({ project_ref: reference, workspace: nullableString }).strict(),
  read_project_repository: z
    .object({
      project_ref: reference,
      workspace: nullableString,
      repository_id: z.uuid(),
      operation: z.enum(["tree", "file"]),
      path: z.string().max(1024).default(""),
      ref: z.string().max(255).default(""),
      page: z.number().int().min(1).max(10000).default(1),
    })
    .strict(),
  list_accessible_projects: z
    .object({ workspace: nullableString, search: z.string().default(""), offset: z.number().int().min(0).default(0) })
    .strict(),
  search_work_items: z
    .object({
      project_ref: reference,
      keyword: z.string().default(""),
      workspace: nullableString,
      offset: z.number().int().min(0).default(0),
    })
    .strict(),
  get_work_item: z.object({ project_ref: reference, item_id: z.uuid(), workspace: nullableString }).strict(),
  get_my_capabilities: z
    .object({ project_ref: reference, item_id: z.uuid().nullable().optional(), workspace: nullableString })
    .strict(),
  save_discussion_result: z
    .object({
      intent: z.enum(["prepare_create", "prepare_update", "commit"]),
      project_ref: reference.nullable().optional(),
      title: z.string().min(1).max(255).nullable().optional(),
      description_markdown: z.string().max(50000).nullable().optional(),
      decision_id: z.uuid().nullable().optional(),
      existing_work_item_id: z.uuid().nullable().optional(),
      expected_updated_at: nullableString,
      workspace: nullableString,
      work_item_type: nullableString,
      append: z.boolean().default(true),
    })
    .strict(),
};
const projectPath = (p: Project) => `workspaces/${encodeURIComponent(p.workspace)}/projects/${p.id}/`;
/** Dispatch the original five tools. Authentication is captured per HTTP request, never in args. */
export async function invoke(
  plane: Plane,
  bearer: string,
  name: string,
  args: unknown
): Promise<Record<string, unknown>> {
  if (name === "list_project_repositories") {
    const a = inputs.list_project_repositories.parse(args);
    const r = await plane.resolve(bearer, a.project_ref, a.workspace);
    return r.ambiguity ?? plane.request(bearer, "GET", projectPath(r.project!) + "ai-repositories/");
  }
  if (name === "read_project_repository") {
    const a = inputs.read_project_repository.parse(args);
    const r = await plane.resolve(bearer, a.project_ref, a.workspace);
    return (
      r.ambiguity ??
      plane.request(
        bearer,
        "GET",
        projectPath(r.project!) + `ai-repositories/${a.repository_id}/${a.operation}/`,
        undefined,
        { path: a.path, ref: a.ref, page: a.page }
      )
    );
  }
  if (name === "list_accessible_projects") {
    const a = inputs.list_accessible_projects.parse(args);
    return plane.request(bearer, "GET", "projects/", undefined, {
      search: a.search,
      offset: a.offset,
      ...(a.workspace ? { workspace: a.workspace } : {}),
    });
  }
  if (name === "save_discussion_result") {
    const a = inputs.save_discussion_result.parse(args),
      identity = await plane.identity(bearer);
    if (a.intent === "commit") {
      if (
        !a.decision_id ||
        Object.entries(a).some(([k, v]) => !["intent", "decision_id", "append"].includes(k) && v != null)
      )
        throw new Error("Commit takes only the prepared decision_id");
      const pending = z
        .object({ path: z.string(), payload: recordSchema })
        .parse(plane.vault.decision(identity.connection_id, a.decision_id));
      return plane.request(bearer, "POST", pending.path, { ...pending.payload, decision_id: a.decision_id });
    }
    if (a.decision_id || !a.project_ref) throw new Error("Prepare requires a project and no decision ID");
    if (a.intent === "prepare_update" && (!a.existing_work_item_id || !a.expected_updated_at))
      throw new Error("Updates require an item and read version");
    if (a.intent === "prepare_create" && (a.existing_work_item_id || a.expected_updated_at || !a.title))
      throw new Error("Create requires title and no existing item");
    if (a.title !== null && a.title !== undefined && !a.title.trim()) throw new Error("Empty title");
    if (a.title == null && a.description_markdown == null) throw new Error("No explicit content");
    const resolved = await plane.resolve(bearer, a.project_ref, a.workspace);
    if (resolved.ambiguity) return resolved.ambiguity;
    const project = resolved.project!,
      path = projectPath(project) + "work-items/" + (a.existing_work_item_id ? `${a.existing_work_item_id}/` : "");
    if (a.existing_work_item_id) await plane.request(bearer, "GET", path);
    const payload: Record<string, unknown> = { append: a.append };
    for (const key of ["title", "description_markdown", "expected_updated_at", "work_item_type"] as const)
      if (a[key] != null) payload[key] = a[key];
    const pending = { path, payload, prepared_by: "plane" };
    let id = plane.vault.prepared(identity.connection_id, pending);
    if (!id) {
      const draft = await plane.request(bearer, "POST", path + "prepare/", payload);
      id = plane.vault.prepare(identity.connection_id, pending, z.uuid().parse(draft.decision_id));
    }
    return {
      status: "prepared",
      decision_id: id,
      project,
      message: "No work item has been written. Commit this decision only for explicit user archive instructions.",
    };
  }
  if (name === "search_work_items") {
    const a = inputs.search_work_items.parse(args),
      r = await plane.resolve(bearer, a.project_ref, a.workspace);
    return (
      r.ambiguity ??
      plane.request(bearer, "GET", projectPath(r.project!) + "work-items/", undefined, {
        search: a.keyword,
        offset: a.offset,
      })
    );
  }
  if (name === "get_work_item") {
    const a = inputs.get_work_item.parse(args),
      r = await plane.resolve(bearer, a.project_ref, a.workspace);
    return r.ambiguity ?? plane.request(bearer, "GET", projectPath(r.project!) + `work-items/${a.item_id}/`);
  }
  if (name === "get_my_capabilities") {
    const a = inputs.get_my_capabilities.parse(args),
      r = await plane.resolve(bearer, a.project_ref, a.workspace);
    return (
      r.ambiguity ??
      plane.request(
        bearer,
        "GET",
        projectPath(r.project!) + (a.item_id ? `work-items/${a.item_id}/` : "") + "capabilities/"
      )
    );
  }
  throw new Error("Unknown tool");
}
