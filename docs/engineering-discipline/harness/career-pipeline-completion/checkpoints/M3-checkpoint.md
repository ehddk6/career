# M3 Checkpoint: Contract-Bound Authorization

**Status:** completed
**Commit:** `42f8b0f`
**Independent validation:** PASS

## Delivered

- Version 2 review, authorization candidate, and authorization contracts bind package, reviewed site contract digest, exact origin, adapter lineage, schema lineage, capabilities, non-secret key ID, and signature version.
- Current read-only, live-disabled, mutation-disabled contracts cannot issue `fill_only` or `submit` authority.
- Legacy version 1 authorization is never auto-upgraded and execution entry points fail with `LEGACY_AUTHORIZATION_UNUSABLE`.
- Static integrity, time, ledger, revocation, reuse, package, contract, and adapter failures stop before driver probes.
- Live origin and schema mismatches use read-only probes only and stop before every mutation callback.

## Verification

- M3 contract tests: `41 passed`
- Focused regression: `197 passed, 2 skipped`
- Full suite: `513 passed, 5 skipped`
- Collected tests: `518`
- Duplicate/shadowed test definitions: `0`
- `python -m compileall -q career_pipeline`: passed
- Commit-range `git diff --check`: passed
- Sensitive literal and forbidden live/network scans: no matches

## Boundary

No live adapter, network request, browser launch, credentials, real PII, upload, click, submit, or receipt collection was introduced. The final review-only agent hit a usage limit after the separate independent implementation validator had passed; M7 will repeat the isolated review.
