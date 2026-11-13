# Singularity personal MCP gateway

This service uses a personal Plane OAuth grant, never a Plane administrator API
key. It exposes exactly five tools. GitLab provisioning, shared ChatGPT grants,
automatic archiving, deletion and workers are outside this release.

## Sign in

Use a separate OS user/Codex credential store per person. The shared model
account is not your Plane identity.

```powershell
codex mcp add singularity --url https://localhost:8444/mcp --oauth-client-id singularity-codex --oauth-resource https://localhost:8444/mcp
codex mcp login singularity --scopes projects:read,workitems:read,workitems:write
```

Register the **exact** callback URI emitted by your installed Codex version in
`SINGULARITY_REDIRECT_URIS`; configure a stable callback port in the personal
Codex configuration. No redirect wildcard, disabled TLS check, or global token
is accepted. For local verification use a separate `CODEX_HOME`, not another
person's saved session.

The browser opens Plane consent. If not logged in, use the login link, then
return to consent. Check the displayed account before allowing access. Manage
and revoke connections at `/auth/singularity/connections/` on the HTTPS origin.

## Archiving protocol

1. Resolve a unique visible project; search for existing work items if needed.
2. Call `save_discussion_result` with `prepare_create` and explicit content, or
   `prepare_update` with an exact item ID and its last-read `updated_at`.
3. Commit only the returned `decision_id`. Preparing does not write Plane.
4. On transport failure retry the **same ID**; Plane returns its atomic receipt.
   Never claim creation until receiving a successful result.

Identical prepared content within one personal connection reuses its decision
ID. This intentionally prevents accidental repeated archiving of the same
summary. A revised decision requires changed content. Updates append by default;
replacement requires explicitly setting `append=false`. Unspecified fields are
omitted. Similar titles do not identify an update target.

Configure each project's existing initial state and optional type-to-label
mapping in `SINGULARITY_PROJECT_CONFIG`, keyed by project UUID. Without explicit
configuration, only an existing state named `待整理` is accepted. No state or label
is created automatically. Result IDs are authoritative; a link is omitted until
the deployed frontend route is verified.

## Validation

Plane: `pytest plane/tests/contract/api/test_singularity.py` in the isolated API
test stack. Gateway: `uv run --group test python -m unittest discover -s tests -v`.
Never run test fixtures against an existing business database.

See `docs/plane-capability-matrix.md`, `docs/architecture.md`, and
`docs/implementation-plan.md` in this application for scope and rollout details.
