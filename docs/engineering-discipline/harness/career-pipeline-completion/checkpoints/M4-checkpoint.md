# M4 Checkpoint: Deterministic Offline Acceptance

**Status:** completed
**Commit:** `7f68329`
**Independent validation:** PASS
**Final review:** PASS

## Delivered

- Synthetic structured posting, profile, eligibility, verified final-artifact boundary, application package, site intake, version 2 review, disabled authorization candidate, and readiness evidence run in one offline workflow.
- Adapter schema lineage is explicit and separate from canonical site schema lineage.
- Identical explicit inputs produce identical public results and digests in different temporary roots.
- Sensitive fixtures and stale/revoked/expired/reused/origin/unknown-structure scenarios remain fail-closed.
- Readiness truthfully reports local acceptance while keeping external inputs blocked, live execution disabled, and submission not attempted.

## Verification

- M4 tests: `15 passed`
- Focused regression: `215 passed, 2 skipped`
- Full suite: `528 passed, 5 skipped`
- Collected tests: `533`
- `python -m compileall -q career_pipeline`: passed
- Commit-range `git diff --check`: passed
- Network/browser/credential/PII/upload/click/submit counters: all zero
- Test evidence SHA equals the actual test file SHA
- Duplicate/shadowed tests: zero

## Boundary

This checkpoint proves deterministic local synthetic acceptance only. It does not run `finalize_run`, access a live site, launch a browser, use credentials or real PII, upload files, click controls, submit an application, or verify a receipt.
