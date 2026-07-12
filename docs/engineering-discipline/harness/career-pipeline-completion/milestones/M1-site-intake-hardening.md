# Milestone: Phase 6.5 Fail-Closed Hardening

**ID:** M1
**Status:** completed
**Dependencies:** baseline `809929c`
**Risk:** Medium-High
**Effort:** Medium

## Goal

Ensure site intake never treats unknown or structurally ambiguous evidence as a verified contract candidate.

## Success Criteria

- Every unknown/review-required login, MFA, CAPTCHA, iframe, popup, redirect, and attachment status produces a stable validation code and cannot become `read_only_contract_ready`.
- `base`, `formaction`, nested form, malformed HTML, sensitive URL metadata, and schema ambiguity are covered by adversarial tests.
- Intake identity reflects validation result and canonical lineage so changed review evidence cannot reuse a stale registry record.
- Every generated contract keeps `mutation_enabled=false` and `live_enabled=false`.

## Files Affected

- `career_pipeline/site_intake.py`
- `tests/test_site_intake.py`

## User Value

Static parsing success can no longer be confused with live-site safety.

## Abort Point

Yes. Do not continue if unknown or schema-drift input can still become ready.
