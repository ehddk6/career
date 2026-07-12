# Milestone: Unified CLI and Operational Gate

**ID:** M5
**Status:** pending
**Dependencies:** M4
**Risk:** Medium
**Effort:** Medium

## Goal

Expose readiness and offline acceptance through stable read-only CLI commands and accurate exit codes.

## Success Criteria

- Status/readiness and offline acceptance provide human summary plus versioned JSON.
- Exit codes distinguish local complete, unsafe/incomplete, and external-only blocked states.
- Existing public CLI remains compatible and platform/adapter information derives from registries.
- Product-surface secret, PII, absolute-path, network, and mutation scans pass.
- Documentation never presents submit as a currently supported live feature.

## Files Affected

- `career_pipeline/__main__.py`
- `tests/test_cli.py`
- `docs/career-pipeline-usage.md`, `docs/application-execution.md`
- `.agents/skills/career-pipeline/SKILL.md`

## User Value

One command accurately shows what works and what still needs external evidence.

## Abort Point

Yes; stop if CLI output implies live or submission readiness.
