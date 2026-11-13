# Delivery and rollback

Historical delivery scope (completed before the expanded plan): Plane personal OAuth, five MCP tools, real archive/update,
isolated tests, then local deployment. No GitLab, shared ChatGPT or worker work.

The user subsequently approved company GitLab provisioning/SSO, personal tokens
and multi-repository access. Current incremental scope and evidence are tracked
in [unified-platform-delivery.md](unified-platform-delivery.md). The exclusions
above describe the historical delivery only, not the expanded authorization.

1. Add grant/code/token/receipt/audit tables through generated migration 0127.
2. Add OAuth consent/revocation and custom `/api/singularity/v1/` endpoints.
3. Add the separately deployed gateway and encrypted private vault.
4. Run A01–A14, OAuth/security, concurrency and legacy authentication regressions.
5. Commit only this change, build immutable sources, back up deployment/database,
   migrate and deploy locally; verify HTTPS and real personal-client flow.

Feature flag: `SINGULARITY_ENABLED=0` by default. Configuration includes fixed
issuer/resource, exact Codex callback URIs, shared exchange secret and per-project
existing-state mappings. Runtime secrets and evidence stay outside source control.

Rollback: disable the new entrypoint and restore previous API/worker images.
Leave the additive tables in place. Do not restore an older business database
just to roll back code. Keep gateway vault, receipts and audit data for recovery.

The original frontend and business projects are retained. The existing local
8088 deployment stays available; a loopback-only HTTPS proxy supplies the MCP
and authorization origin. No public network policy changes are authorized.

Delivery evidence distinguishes implementation, automated validation and actual
client acceptance. Missing interactive login or certificate trust is reported
as pending, not silently replaced with mocked acceptance.

## P4 Plane-owned preparation

Prepare via `POST .../work-items/prepare/` (or the item UUID's `/prepare/`) using
only explicit content and, for updates, the previously read version. Plane returns
202 with a server-generated decision UUID and content digest, bound to the current
grant, project and target. No work item or discussion body is stored at preparation.
A write request without a decision ID also prepares only. Unknown IDs, changed
content, different connections or projects cannot commit. Successful saves retain
receipt/work-item atomicity and current permission checks on every replay.

The Gateway retains encrypted pending content but uses Plane's decision ID. Existing
committed decisions can still replay. Legacy Gateway-only pending IDs must be
prepared again; deploy API and Gateway together. Work-item results include the
native `/{workspace}/browse/{identifier}-{sequence}/` link using configured WEB_URL.
Native App/public PATCH row locks are preserved, not replaced.

Validation: 21 Plane OAuth/work-item contracts and 6 Gateway SDK contracts pass,
including server-owned preparation, no early write, arbitrary-ID rejection,
actor/project/content binding, concurrent commit/restart replay and native-edit
conflicts. API/Gateway lint passed. Live deployment and two-user OAuth/PAT plus native Codex acceptance passed on 2026-11-13; see unified-platform-delivery.md.
