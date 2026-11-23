# Plane OCR integration — 2026-11-23

Authority: the user's original five-section specification and explicit answers in this chat.
Implement the four accepted delivery units in order; do not expand repository management,
GitLab merge policy, WBS, document review or the workbench.

Confirmed: project service identity from controlled deployment files; fixed exclusion rules
with visible coverage; revoked reviewer permission invalidates acceptance; manual rerun
immediately invalidates acceptance. Native OCR only, Chinese, Responses protocol, two slots,
30 minutes per attempt, at most three transient attempts. Human session required to decide.

## Acceptance units and evidence ledger

1. Associations / four persistent record types / API / audit: implemented and automatically verified.
   Evidence: four new contracts and eleven WBS regressions passed; Ruff passed;
   generated migration 0141 applied to isolated PostgreSQL; migration drift check clean.
2. Fixed-version OCR / Hatchet delivery / authenticated events / reconciliation: pending.
3. Human decisions / UI / shared completion gate on all mutation paths: pending.
4. Private deployment / real model compatibility / end-to-end / regressions: pending.

Pre-flight: all units consume the association's current run and immutable version fingerprint.
Runs have independent execution status and append-only human decisions. Issue row locking
serializes association, decision, rerun and completion changes. GitLab verification is a
point-in-time observation; later commits preserve completed status and mark stale evidence.

Ruling: use an isolated native worktree; the other existing code-review worktree has no
attachment to this chat and is left untouched. Tests use new isolated containers without
published ports. Production services remain unchanged until deployment validation.
