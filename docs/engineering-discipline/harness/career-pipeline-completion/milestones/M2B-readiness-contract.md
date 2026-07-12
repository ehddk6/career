# Milestone: Requirements and Readiness Contract

**ID:** M2B
**Status:** pending
**Dependencies:** M1
**Risk:** Medium
**Effort:** Medium

## Goal

Separate local implementation evidence, local actions, external inputs, live execution, and submission state in a versioned report.

## Success Criteria

- Requirements are classified as `implemented`, `locally_missing`, or `external_only` with code/test/artifact evidence.
- Report axes include local foundation, offline acceptance, external inputs, live execution, and submission.
- Evidence records source, artifact SHA/version, and freshness without converting test counts into readiness.
- Stable blocker codes cover origin, DOM, policy, credentials, MFA/CAPTCHA, PII authority, upload, click, submit, and receipt verification.

## Files Affected

- Create `career_pipeline/readiness.py`
- Create `tests/test_readiness.py`
- Create requirements trace document/schema

## User Value

The user can distinguish local completion from real application readiness.

## Abort Point

Yes; reject any design that collapses all states into one boolean.
