# Milestone: Deterministic Offline Acceptance

**ID:** M4
**Status:** completed
**Dependencies:** M3
**Risk:** Medium-High
**Effort:** Large

## Goal

Prove the complete local application flow with synthetic data and zero external side effects.

## Success Criteria

- Synthetic posting/profile/eligibility/final artifact/package/intake/review/fill-only authorization/fixture validation reaches `awaiting_final_confirmation`.
- Repeated runs preserve deterministic IDs and lineage except explicit clock fields.
- Network, browser, credentials, real PII, upload, click, and submit call counts remain zero.
- Positive and critical fail-closed paths are exercised.
- Result JSON reports both local completion and external/live blockers.

## Files Affected

- Create `career_pipeline/offline_acceptance.py`
- Create `tests/test_offline_acceptance.py`
- Add synthetic acceptance fixtures

## User Value

One repeatable run proves the local product instead of isolated unit features.

## Abort Point

Yes; external requirements must become blockers, never hidden live workarounds.
