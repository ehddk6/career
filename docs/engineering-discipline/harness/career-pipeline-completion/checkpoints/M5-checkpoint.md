# M5 Checkpoint: CLI and Operational Gate

**Status:** completed
**Feature commit:** `2d30f8b`
**Windows lock correction:** `72aa59c`
**Independent validation:** PASS
**Final review:** PASS

## Delivered

- `offline-acceptance` and strict `status --input` commands provide canonical JSON and fixed human summaries.
- Exit codes distinguish local success, local unsafe input, external-only blockers, domain-invalid input, and argparse syntax errors.
- A successful local acceptance with external blockers exits `3`; it is not misreported as a local failure or live readiness.
- Fixture adapter choices derive from the platform registry.
- Usage documents and the career-pipeline skill describe the same no-live contract as the CLI.
- Strict status input validates confined files, size, schemas, counters, blocker consistency, digests, readiness evidence, and canonical exact origins.

## Verification

- M5 CLI tests: `12 passed`
- All CLI tests: `23 passed`
- Full suite after lock correction: `541 passed, 5 skipped`
- Transient Windows lock regression: `10/10` repeated passes
- `python -m compileall -q career_pipeline`: passed
- `git diff --check`: passed
- Subprocess smoke: exits `3`, `2`, `4`, and argparse `2` matched the contract
- Traceback, secret, PII, absolute-path, and raw-fixture leakage: none
- Live/network/browser/credential/upload/click/submit implementation: none

## Boundary

The CLI exposes deterministic synthetic local evidence only. External origin, production DOM, policy, credentials, MFA/CAPTCHA, PII authority, upload, click, submit, and receipt verification remain blockers.
