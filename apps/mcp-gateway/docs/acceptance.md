# Acceptance — 2026-11-13

Implementation source: `2cf57c8aba` (Plane authorization and gateway).

## Automated

- 177 Plane tests passed: 20 personal delegation tests plus legacy authentication
  and external-API guest-visibility regressions. Includes native PATCH versus
  delegated version checking, concurrent duplicate creation, scopes, PKCE,
  refresh rotation, per-user isolation and revocation.
- Six gateway tests passed: exact tool surface, encrypted persistent vault,
  server-owned decision preparation, cross-connection rejection, ambiguous
  projects, arbitrary URL isolation and 401/402/403/404/409/429 handling.
- Ruff, migration drift and Git whitespace checks passed.

The initial expanded regression run lacked isolated service configuration.
After supplying test-only Redis, mail, S3 and RabbitMQ settings, all 177 passed;
no unrelated production functionality was changed to make those tests pass.

## Actual local services

- Source-built backend and gateway deployed; additive migration 0127 applied.
- Loopback HTTPS at `https://localhost:8444`; local CA installed in the current
  Windows user's trust store. Strict Python TLS and Windows HTTPS checks pass.
- Two fixture users completed actual Plane password login, OAuth consent and
  MCP initialization. Five tools discovered. Work-item create, read, append,
  replay and grant revocation passed; developer cannot discover private PAY.
- Plane records the corresponding real fixture user as each work-item actor.
- Gateway restart followed by replay of the same decision returns the same
  work item; the persistent vault and Plane receipt survive restart.
- Installed Codex completed `codex mcp login singularity --no-browser` against
  real consent. Its native app-server MCP client listed projects, prepared and
  created `MCPPOS-3`, then read it back. No model-generated success was substituted
  for the tool result. A separate test CODEX_HOME was used and logged out.
- The acceptance workspace was removed through its owner's native Plane API;
  both fixture users were disabled, all fixture grants revoked and saved test
  passwords removed. The isolated test containers were stopped.

Runtime evidence and configuration are private under
`D:/plane-ops/state/singularity`; pre-deployment database/configuration backup is
`D:/plane-ops/backups/20261113-115155-singularity`. No credentials are included here.

## Remaining user configuration / exclusions

Users must log in with their own Plane account and independent Codex credential
store. Each business project needs an existing 待整理 state or an explicitly
configured existing initial state. No business-project settings were guessed.

GitLab account provisioning, shared ChatGPT, auto-archiving and worker delegation
are not implemented. The gateway returns actual IDs/identifiers; frontend links
are deliberately omitted until a concrete route is verified.
