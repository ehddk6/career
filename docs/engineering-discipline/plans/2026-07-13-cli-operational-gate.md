# M5 Unified CLI and Operational Gate Execution Plan

## Scope and truthful outcome

M5 exposes the existing M4 local synthetic boundary through read-only CLI
commands. It does not add live application execution. A successful M5 command
can say that local synthetic acceptance is complete; it must continue to say
that live execution is disabled and submission was not attempted.

M5 never fetches a site, launches a browser, reads credentials, reads real PII,
uploads a file, clicks a control, submits an application, or collects a
receipt. It uses only the clean synthetic fixture already constructed by
`run_offline_acceptance`; the CLI must not expose M4's custom fixture HTML or
sensitive-fixture scenario.

The current baseline is `528 passed, 5 skipped`. The M4 checkpoint and final
review are both PASS; M5 starts from that state and must preserve its verified
test-evidence and fail-closed boundaries.

## Locked implementation scope

Only these files may change during M5 implementation:

- `career_pipeline/__main__.py`
- `career_pipeline/platform_catalog.py`
- `tests/test_cli.py`
- `docs/career-pipeline-usage.md`
- `docs/application-execution.md`
- `docs/site-intake.md`
- `.agents/skills/career-pipeline/SKILL.md`
- `docs/engineering-discipline/plans/2026-07-13-cli-operational-gate.md`

Do not change `career_pipeline/offline_acceptance.py`, `career_pipeline/readiness.py`,
adapter modules, `__main__` legacy command behavior, package configuration, M4
tests, fixtures, checkpoint/review files, baseline marker, or any user worktree
change. `pyproject.toml` needs no entry-point change: the supported surface
remains `python -m career_pipeline`.

No staging, commit, push, PR, reset, checkout, marker action, or external write
is authorized while writing this plan. Commits are listed only as the future
post-GREEN implementation sequence.

## Existing contracts to preserve

- `career_pipeline.__main__.build_parser()` uses top-level subcommands and
  legacy application subcommands; existing parser shapes and return codes stay
  unchanged.
- M4 public execution stays in `run_offline_acceptance`,
  `offline_acceptance_to_dict`, `readiness_report_to_dict`, and
  `readiness_report_from_dict`. M5 consumes these contracts without changing
  their schema versions or constructing live authority.
- Existing readiness schema remains `career-pipeline-readiness-v1` with the
  five ordered axes. `EXTERNAL_ONLY` blockers are evidence of an external
  boundary, not a local acceptance failure.
- `CATALOG` and `FIXTURE_ADAPTER_REGISTRY` remain the sources of truth. Current
  application-family entries have `live_enabled=false` and no live adapter.
  M5 must remove the CLI handler's hard-coded fixture adapter list in favor of
  registry-derived values.
- Existing `application platform`, `application adapter`, `application
  site-intake`, `fill-fixture`, and legacy review/authorize commands remain
  compatible. M5 neither broadens their authority nor documents them as live
  capabilities.

## Public CLI contract

Add two top-level commands. Both commands use only deterministic explicit
inputs; they never read a clock, environment variable, credential store, or
user profile.

```text
career-pipeline offline-acceptance
  --workspace PATH (required)
  --at ISO-8601-with-timezone (required)
  --site-valid-until ISO-8601-with-timezone (required)
  --test-evidence-sha256 LOWERCASE_SHA256 (required)
  --format {human,json} (default: human)
  --output PATH (optional)

career-pipeline status
  --input PATH (required)
  --format {human,json} (default: human)
```

`offline-acceptance` maps `--at` to every M4 timestamp except
`site_valid_until`, which maps to `--site-valid-until`. It supplies only an
internal, domain-separated public synthetic signing value to satisfy M4's
HMAC test fixture; it is not a user credential, is never accepted as an option,
and is never emitted. The command forwards the supplied test SHA unchanged to
`AcceptanceInputs.test_evidence_sha256`.

`--workspace` is an explicit local synthetic-artifact directory. It is not
included in stdout, JSON, human summaries, or errors. `--output`, when given,
writes the exact UTF-8 JSON bytes printed to stdout; it does not cause the path
to be printed. The command exposes no `--fixture-html`, `--fixture-scenario`,
signing-key, browser, URL-fetch, credential, PII, attachment, upload, click, or
submit option.

`status` accepts either a M5 offline-acceptance JSON envelope or a bare valid
`career-pipeline-readiness-v1` document. It validates the embedded/bare
readiness payload with `readiness_report_from_dict` before deriving status. It
does not run a new acceptance flow, mutate the input file, or echo its path.

### Machine JSON envelopes

All successful `--format json` output is one UTF-8 JSON object and nothing
else. `offline-acceptance --output` writes byte-identical JSON plus a final
newline, while stdout uses the same object plus a final newline.

```json
{
  "schema_version": "career-pipeline-cli-offline-acceptance-v1",
  "command": "offline-acceptance",
  "classification": {
    "local_state": "complete",
    "external_state": "external_only_blocked",
    "exit_code": 3
  },
  "acceptance": { "...": "offline_acceptance_to_dict result" }
}
```

`acceptance` is the existing sanitized serializer result. It must contain no
signing key/fingerprint, private fields, fixture HTML, fixture path, sensitive
fixture value, user path, name, email, phone, credential, or URL query value.

```json
{
  "schema_version": "career-pipeline-cli-status-v1",
  "command": "status",
  "classification": {
    "local_state": "complete | unsafe",
    "external_state": "clear | external_only_blocked | not_assessed",
    "exit_code": 0
  },
  "readiness": { "...": "readiness_report_to_dict result" }
}
```

For an invalid input, `--format json` prints exactly
`{"schema_version":"career-pipeline-cli-error-v1","command":"status","error_code":"INVALID_INPUT"}`
and returns 4. The human error is a fixed `invalid status input` message; it
must not include the raw exception, input path, file content, or sensitive
value.

### Human summaries and exit codes

Human output is fixed, one value per line, and never includes paths or raw
evidence values:

```text
local: complete
offline acceptance: passed
external inputs: blocked
live execution: disabled
submission: not attempted
outcome: external_only_blocked (exit 3)
```

Use one pure internal classifier for both commands:

| classification | condition | exit |
| --- | --- | --- |
| `local_complete` | local foundation is `complete`, offline acceptance is `passed`, and no local requirement is `locally_missing` | 0 when no external-only blocker remains |
| `local_unsafe` | M4 blocked outcome, malformed/missing local axes, failed/not-run offline acceptance, incomplete foundation, or a local missing requirement | 2 |
| `external_only_blocked` | local complete, with only `EXTERNAL_ONLY` blocker records remaining | 3 |
| `invalid_input` | parser/readiness/envelope validation failure | 4 |

The normal M4 positive result is deliberately `external_only_blocked` and exits
3. This is not a local failure: the JSON and human summary still show local
complete, while external inputs remain blocked, live execution disabled, and
submission not attempted. A bare fully-clear readiness fixture exits 0 only to
verify the mapping; M5 does not claim that such a live-ready report was produced
by M4.

## Registry-derived platform and adapter CLI behavior

Add `list_fixture_adapters()` to `platform_catalog.py`. It returns a sorted,
unique tuple by traversing validated `CATALOG` entries with a
`fixture_adapter_id`, verifies each value agrees with
`FIXTURE_ADAPTER_REGISTRY`, and rejects any live-enabled/live-adapter entry.

Use this function in `__main__.py` for:

- parser choices for `application adapter {show,schema,validate}` and
  `application fill-fixture --adapter`;
- `application adapter list` JSON output;
- adapter module dispatch through a closed mapping keyed by the registry-derived
  adapter ID.

Keep the two existing fixture adapters and their current commands/output
compatible. The listing must show only fixture adapter IDs and must not add a
live adapter, actual execution origin, or mutation command.

## Implementation sequence

1. Add the 12 M5 CLI tests below to `tests/test_cli.py` first. Reuse clean
   temporary directories, a deterministic timezone-aware timestamp, a real SHA
   of `tests/test_offline_acceptance.py`, and locally generated valid readiness
   JSON. Never use a real user profile, credentials, actual site HTML, or a
   fixture containing personal data.
2. Extend `build_parser()` with `offline-acceptance` and `status`; do not change
   existing parser arguments, defaults, command names, or compatibility aliases.
3. In `__main__.py`, add small pure helpers for: M5 synthetic input construction,
   sanitized JSON rendering, envelope unwrapping, readiness classification, and
   human summary rendering. Route only the two new commands through a dedicated
   exception boundary that produces the fixed error contract. Existing command
   exception behavior remains untouched.
4. Implement `list_fixture_adapters()` and use it in existing adapter parser and
   dispatch code. Do not import `application_execution` into the catalog and do
   not change adapter behavior.
5. Update the three user documents and the career-pipeline skill together:
   show both M5 commands, `--format`, expected exit 3 for M4's external-only
   block, and the explicit no-live boundary. Remove or correct any wording that
   suggests submit/live application execution is currently available.
6. Run RED, then implement until GREEN. Stop immediately if an implementation
   needs a live URL fetch, browser/page object, credential, real PII, upload,
   click, submit, receipt collection, `__main__` live adapter, or a change
   outside the locked files.

## Exact M5 test contract

M5 adds exactly 12 collected nodes, all in `tests/test_cli.py`:

1. `test_m5_parser_exposes_status_and_offline_acceptance_commands`
2. `test_m5_offline_acceptance_json_envelope_and_external_blocked_exit`
3. `test_m5_offline_acceptance_human_summary_is_machine_safe`
4. `test_m5_offline_acceptance_writes_same_json_without_path_echo`
5. `test_m5_status_reads_offline_envelope_as_external_only_blocked`
6. `test_m5_status_returns_zero_for_complete_readiness_fixture`
7. `test_m5_status_returns_two_for_local_unsafe_readiness_fixture`
8. `test_m5_status_rejects_invalid_input_with_exit_four`
9. `test_m5_status_human_summary_never_claims_submission`
10. `test_m5_adapter_list_is_registry_derived_and_fixture_only`
11. `test_m5_product_surface_redacts_sensitive_values_and_absolute_paths`
12. `test_m5_existing_commands_remain_compatible_when_new_top_level_commands_are_added`

The compatibility test must parse and execute existing safe parser paths as
part of its assertion, then parse the new commands; it is not a wrapper or a
duplicate assertion. The product-surface test must inspect new command output
and added source regions for secret/PII/user-absolute-path/dangerous API leaks.
Sensitive literals are allowed only in the negative test input construction and
must be absent from captured output and JSON.

RED is test-first:

```powershell
python -m pytest --collect-only -q tests/test_cli.py -k "m5_"
# 12 tests collected
python -m pytest -q tests/test_cli.py -k "m5_"
# RED: 12 failed
```

All 12 fail before implementation because neither new top-level command nor
registry-derived adapter behavior exists. Missing nodes, imports, skips, xfails,
shadow tests, or duplicate test definitions invalidate RED. GREEN is:

```powershell
python -m pytest -q tests/test_cli.py -k "m5_"
# GREEN: 12 passed
python -m pytest -q tests/test_cli.py
# GREEN: 23 passed
```

With the current baseline, the full-suite GREEN expectation is `540 passed, 5
skipped` (528 prior passes plus 12 M5 nodes). If the baseline changes before M5
implementation, record the new pre-RED count and adjust only this arithmetic;
do not silently change the 12-node M5 contract.

## Verification commands and static gates

```powershell
python -m pytest -q tests/test_cli.py -k "m5_"
python -m pytest -q tests/test_cli.py tests/test_offline_acceptance.py tests/test_readiness.py tests/test_platform_catalog.py
python -m pytest -q
python -m compileall -q career_pipeline
git diff --check
git diff --name-only
```

Expected focused result after GREEN: `tests/test_cli.py` has 23 passes; the
combined focused command must have no failures. Expected full result: `540
passed, 5 skipped` unless the recorded pre-RED baseline changed.

Run these additional gates over added diff lines and new command output:

```powershell
git diff --unified=0 -- career_pipeline tests docs .agents | Select-String -Pattern '^[+].*(requests|httpx|urllib\.request|socket|selenium|playwright|page\.goto|page\.click|page\.press|set_input_files|upload|submit)'
git diff --unified=0 -- career_pipeline/__main__.py career_pipeline/platform_catalog.py tests/test_cli.py docs .agents | Select-String -Pattern '^[+].*(os\.environ|dotenv|keyring|CAREER_.*KEY|password|token|secret|full_name|email|phone|C:\\Users|/home/)'
git diff --unified=0 -- career_pipeline/__main__.py career_pipeline/platform_catalog.py tests/test_cli.py | Select-String -Pattern '^[+].*(datetime\.now|time\.time|os\.environ|dotenv|keyring)'
```

The first scan may match prose that explicitly says a live action is unsupported;
review every match and reject any new executable live/mutation call. The second
scan permits only deliberately constructed negative-test literals, never a
serializer, human formatter, command option, or documentation example. Scanning
only added lines avoids treating existing legacy compatibility code as an M5
regression. Verify captured JSON/human output contains none of those values or
an absolute path.

Finally inspect parser compatibility, the derived adapter list, envelope key
sets, exit mapping, exact zero M4 counters, and documentation/skill examples.
Do not use browser, network, credentials, real PII, upload, click, or submit as
part of verification.

## Future commit sequence after GREEN

1. `test(cli): specify operational readiness gate`
2. `feat(cli): expose offline operational gate`

Before each future commit, inspect `git diff --cached --name-only`; use explicit
paths only, never `git add .`. Do not amend, reset, force-push, create a PR, or
touch the baseline marker.
