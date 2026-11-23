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
2. Fixed-version OCR / Hatchet delivery / authenticated events / reconciliation: implemented;
   13 execution/event contracts passed serially. Native real small-diff probe passed using
   gpt-6.1-sol with openai-responses: exit 0, complete manifest, one finding, 2026-11-23.
   OCR 1.14.1 Linux amd64 SHA256:
   7d31862a1b9c6f9cea02141673f7b814071d2f36f1a9e6ce2f14d39d959229f4.
   Two test processes initially shared a DB; those conflicting runs are discarded.
   All following tests run serially. End-to-end GitLab/Hatchet deployment remains pending.
3. Human decisions / UI / shared completion gate on all mutation paths: implemented.
   Evidence: 56 gate/WBS/document-review regression tests passed; the final scoped
   association/session/gate suite passed 18 tests; two process tests and one rendered
   report test passed. Web type checking and changed-file lint/format passed.
   Independent review found and regression-tested null-default-state bypass and stale
   model acceptance; State-before-Issue lock ordering is now shared by model and queryset writes.
   New translation keys match across all locales. Global sync-check still reports the
   pre-existing 886 missing keys in other locales; these are outside this change.
   Chinese Native report revalidated with OCR's explicit language configuration.
4. Private deployment / real model compatibility / end-to-end / regressions: pending.

Pre-flight: all units consume the association's current run and immutable version fingerprint.
Runs have independent execution status and append-only human decisions. Issue row locking
serializes association, decision, rerun and completion changes. GitLab verification is a
point-in-time observation; later commits preserve completed status and mark stale evidence.

Ruling: use an isolated native worktree; the other existing code-review worktree has no
attachment to this chat and is left untouched. Tests use new isolated containers without
published ports. Production services remain unchanged until deployment validation.
