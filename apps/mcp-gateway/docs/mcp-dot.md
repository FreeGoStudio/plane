# MCP Django OAuth Toolkit cutover — 2026-11-14

## Implementation

Both MCP OAuth and company OIDC use Django OAuth Toolkit 3.4.1. MCP uses DOT's
OAuthLibMixin backend lifecycle, OAuthLibCore request handling, Application
registration and OAuth2Validator adapter. The underlying OAuthLib protocol engine
is provided through DOT, not an application-owned global Server instance.
The existing consent UI/session/CSRF and metadata URLs stay stable. OIDC keeps its
separate confidential RS256 validator, issuer and openid/profile/email scopes.

The adapter retains digest-only DelegationCode/DelegationToken storage, 600-second
access tokens, S256, rotating refresh with the original 30-day deadline, and
revocation of the original Delegation. No tokens are copied into DOT plaintext
code/token tables. The confidential audience exchange and restricted personal
access tokens retain their existing implementation. No schema migration or
conversion of existing grants, decisions, receipts or audit data is required.

Register explicitly before switching the API:

```sh
python manage.py register_mcp_oauth_client
```

This registers only `singularity-codex` as public authorization-code, using exact
`SINGULARITY_REDIRECT_URIS` configuration. Re-running identical registration is
safe. Conflicting existing registration fails without changing it. HTTP callbacks
must use literal loopback IPs and explicit ports; other callbacks require HTTPS.
Authorization requires the callback in both configuration and DOT registration.
Dynamic registration remains disabled. Client credentials, OIDC clients and
openid scope cannot be used at MCP endpoints.

Deployment: `D:/plane-ops/scripts/singularity-deploy.py --register-mcp-dot` registers
before replacing API containers. Code rollback may retain the additive Application
row and all delegation data. Disabling the feature and revoking grants is the
operational rollback when access should cease; do not delete account mappings,
receipts, work items or audits.

## Automated verification

64 PostgreSQL contract tests passed: MCP, PAT, DOT cutover, OIDC and company
accounts. Ruff passed and `makemigrations --check --dry-run` reported no changes.
New contracts cover absent/conflicting registrations, unsafe callbacks, legacy
codes and refresh records, scope escalation, issuer separation and revocation of
already-exchanged downstream tokens. Existing contracts cover user/permission
isolation, CSRF, PKCE/replay, the absolute refresh deadline, concurrent decisions
and native-editor conflicts. These are local automated contracts, not external
organization acceptance.

## Real local acceptance before commit

An API candidate used read-only source mounts on the existing loopback TLS route;
the original immutable API image stayed intact. `mcp-dot-cutover-check.py` obtained
codes and tokens from the old adapter, switched to DOT, exchanged the still-valid
old code, used old access, rotated old refresh and committed/replayed the same
prepared discussion. It switched back to the old adapter, refreshed DOT tokens
and replayed the same receipt, then returned to DOT and verified grant revocation.
No duplicate work item was created. TLS chain and hostname verification stayed on.

Two isolated users passed OAuth and PAT five-tool workflows, permission isolation,
create/update, replay after Gateway restart, missing-scope rejection and revocation.
The actual Codex CLI passed OAuth login and native MCP create/read, and separately
passed personal-token native MCP create/read. Evidence is private under
`D:/plane-ops/state/singularity/`: `dot-cutover-verification.json`,
`live-verification.json`, `personal-verification.json`, `codex-verification.json`
and `codex-personal-verification.json`. No secrets are included in this document.

Fixed-commit image rollout and post-rollout company SSO regression are recorded
in the delivery log after completion.

## External acceptance still pending

- A second independent customer GitLab instance and its authorized test users.
- Two-user access to an authorized private GitHub repository.
- Remote ChatGPT connectivity/OAuth/PAT under the current intentional network restrictions.
- Actual organization pilot, operational sign-off and remote deployment acceptance.

These conditions do not turn into additional implementation tasks. No public
ports, tunnels or access restrictions are changed for this cutover.
