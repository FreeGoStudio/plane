# Historical acceptance — 2026-11-13

This page records the original MCP delivery. For the expanded identity/repository
implementation and current evidence, see [unified-platform-delivery.md](unified-platform-delivery.md).
Historical exclusions and deployment state below do not describe the current release.

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

## Expanded-plan A01–A14 evidence map

Tests below live in `apps/api/plane/tests/contract/api/test_singularity.py` unless
noted. All are real isolated PostgreSQL contracts; upstream failures explicitly
mocked in Gateway tests are not represented as live GitLab/CE acceptance.

| Original criterion                         | Automated evidence                                                                                       | Real-instance evidence / remaining condition                                       |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| A01, A03 actor / allowed create            | test_a01_a03_real_actor_and_no_default_assignment                                                        | Two users OAuth/PAT and native Codex created real items                            |
| A02, A04 hidden project / forbidden update | test_a02_a04_hidden_project_and_guest_edit                                                               | Two-user project visibility; forbidden-update contract                             |
| A05 forged identity                        | test_a05_a11_a13_field_whitelist                                                                         | Contract, no model-supplied identity field                                         |
| A06 missing write scope                    | test_a06_missing_scope                                                                                   | PAT missing-scope call refused                                                     |
| A07 member removal                         | test_a07_removed_member                                                                                  | Plane removal contract; separate real upstream repository removal refused          |
| A08 concurrent decision                    | test_a08_concurrent_and_restart_replay                                                                   | Real Gateway restart then same-ID replay                                           |
| A09 human edit conflict                    | test_native_edit_serializes_before_delegated_version_check; test_a09_conflict_and_append_preserve_fields | PostgreSQL competing native/delegated updates, not a browser concurrency claim     |
| A10 revoked / upstream failure             | test_a10_revocation_and_inactive_user; Gateway error tests                                               | Real OAuth/PAT revocation; upstream errors mocked                                  |
| A11 unexposed member/delete tools          | Gateway test_exact_five_tools_and_no_delete; field whitelist                                             | Real client discovers exactly five tools                                           |
| A12 CE 402                                 | Gateway test_errors_include_402_without_fallback                                                         | Mock 402 only; native v2 permissions endpoint absent, not a live CE 402 acceptance |
| A13 SSRF / HTML                            | field whitelist / HTML tests; repository transport contracts                                             | Real hostile README rendered as text; hostile hosts mocked                         |
| A14 similar title                          | test_a13_html_cleaned_a14_similar_titles_do_not_overwrite                                                | Contract: separate decision creates separate item                                  |

Machine-readable contracts: [OpenAPI resource surface](openapi.json) and
[official-SDK MCP tools](mcp-tools.json). Regenerate tools with
`python export_schema.py` in the Gateway environment. The OpenAPI document is
maintained from the actual extension routes and serializers; it does not label
the extension as official Plane v2.
