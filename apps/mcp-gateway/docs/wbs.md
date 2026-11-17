# Plane-owned WBS execution

User acceptance: Plane initiates WBS; Hatchet executes; the work-item page and MCP share the server workflow; only human approval creates children; validate on the private deployment without opening public access.

## Contract

- `start_wbs`: submit the saved work-item version, explicit confirmation and a stable request key. Plane freezes the description, criterion identifiers, existing children and configured WBS skill files in PostgreSQL. The response is a queued business run, not a generated draft.
- `get_wbs`: list runs or retrieve a specific draft and its digest.
- `review_wbs`: an explicit human decision bound to that digest. Approval validates current membership and unchanged source/children, then creates all children and the decision in one transaction. Repeating approval returns the same mappings. Rejecting requires a reason.
- Both browser sessions (CSRF protected) and delegated API callers use `/api/singularity/v1/workspaces/{slug}/projects/{project}/work-items/{issue}/wbs/` and `.../{run}/`.

The Hatchet `plane-wbs-generate` task receives only a business run UUID. A persisted dispatch timestamp handles unavailable dispatch and uncertain acknowledgements; execution leases and fencing prevent stale model results from replacing later attempts. Model output stays in Plane, not Hatchet task results. Three generation attempts are allowed. A process killed during execution becomes eligible after its lease expires; the dispatcher recovers undelivered work after six minutes.

## Current scope

This path uses an explicitly confirmed Plane text requirement; it does not require an old workbench prototype review. The legacy workbench flow is retained. Its coverage/reference/cycle and idempotency concepts are reused here with native Plane persistence. No old project mappings, approvals or drafts are migrated.

Existing children are supplied as reuse evidence. The first version does not automatically read project repositories and does not claim source inspection; unknown implementation details must remain questions or concrete investigation tasks. Generated tasks retain criteria, dependencies, scope, deliverables and acceptance text. Dependencies are recorded in the task description, not native blocking relations.

Normal writes require an active human workspace/project member (member or admin). MCP uses existing workitems read/write scopes. Generated output is data, rendered as text in the review UI and sanitized HTML in created children. No model tools or shell execution are enabled.

## Deployment

Install the locked Python dependencies, apply additive migration `db.0133_wbs_runs`, and run `python manage.py wbs_worker` with the normal Plane DB environment plus private Hatchet client configuration, `WBS_MODEL_KEY_FILE`, `WBS_MODEL` and `WBS_SKILL_DIR`. Only the worker receives the model key and Hatchet token. The API receives the read-only skill directory. No new host ports are required.

Validation on 2026-11-17: 24 focused backend contracts, 23 Gateway tests, frontend type/lint and migration checks passed. On the private deployment, the designated account submitted REPO-7 through native Codex MCP; Hatchet generated a real model draft, the desktop page explicitly approved it and created REPO-11. REPO-8 was submitted and rejected through the page with zero children. Worker restart and repeated MCP approval preserved the same child mapping. Strict-TLS Chrome reported no page JavaScript errors. Evidence and deployment/rollback details are in the operations repository `scripts/wbs-README.md`; this does not replace user product sign-off or claim mobile layout acceptance.
