# Milestone: Contract-Bound Authorization

**ID:** M3
**Status:** completed
**Dependencies:** M2A, M2B
**Risk:** High
**Effort:** Medium-Large

## Goal

Bind reviews and authorizations to a reviewed site contract, adapter, exact origin, schema lineage, and package evidence.

## Success Criteria

- Authorization v2 signs package/review/site contract/adapter/origin/schema/capability bindings.
- Missing, modified, stale, expired, revoked, reused, pre-issuance, or origin-mismatched evidence is rejected before driver calls.
- Contracts with disabled live or mutation capability cannot issue or execute submit authority.
- Legacy authorization is not auto-upgraded; non-secret key ID and signature version are recorded without the secret.

## Files Affected

- `career_pipeline/application_execution.py`
- Related package/form adapter contracts
- `tests/test_application_execution.py` and adapter tests

## User Value

Authorization cannot be replayed against another site, form, or package.

## Abort Point

Yes. Stop if stale authorization can reach any mutation callback.
