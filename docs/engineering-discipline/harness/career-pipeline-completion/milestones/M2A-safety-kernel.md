# Milestone: Shared Safety Kernel

**ID:** M2A
**Status:** executing
**Dependencies:** M1
**Risk:** Medium
**Effort:** Medium-Large

## Goal

Provide one dependency-safe policy layer for exact origins, confined paths, atomic persistence, and lock diagnostics.

## Success Criteria

- Origin normalization is independent of execution code and platform catalog no longer imports execution policy.
- New authorization, registry, acceptance, and readiness artifacts use common atomic/path policy APIs.
- Negative tests cover Windows escapes, symlinks where supported, write failure, stale lock diagnosis, and concurrent writers.
- Lock diagnosis is read-only and never deletes an uncertain lock automatically.

## Files Affected

- Create `career_pipeline/origin_policy.py`
- Create `career_pipeline/path_policy.py`
- Modify `career_pipeline/state.py`, `career_pipeline/platform_catalog.py`
- Add dedicated tests

## User Value

Security behavior remains consistent across Windows and OneDrive paths.

## Abort Point

Yes; limit migration to new security-sensitive paths if compatibility would break.
