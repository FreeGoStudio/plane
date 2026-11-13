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
