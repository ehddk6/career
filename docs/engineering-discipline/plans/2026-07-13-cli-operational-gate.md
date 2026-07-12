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

### Exact machine JSON envelopes

For either command, every successful or domain-invalid `--format json` result
is exactly one UTF-8 JSON object with a trailing newline and this exact top-level
key set, in canonical `sort_keys=True` order:

```text
acceptance
artifact_sha256
blocker_codes
command
error_code
external_inputs_status
live_execution_status
local_status
message
offline_acceptance_status
outcome
readiness_sha256
schema_version
submission_status
```

The key values are constrained as follows:

| key | type and allowed values |
| --- | --- |
| `schema_version` | string: `career-pipeline-cli-status-v1` for `status`, `career-pipeline-cli-offline-acceptance-v1` for `offline-acceptance`, or `career-pipeline-cli-error-v1` only for a domain-invalid result |
| `command` | string: exactly `status` or `offline-acceptance` |
| `outcome` | string: `local_complete`, `local_unsafe`, `external_only_blocked`, or `invalid_input` |
| `local_status` | string: `complete` or `unsafe` |
| `offline_acceptance_status` | `passed`, `failed`, `not_run`, or `null` when not assessed |
| `external_inputs_status` | `ready`, `blocked`, or `null` when not assessed |
| `live_execution_status` | `disabled`, `review_required`, `authorized`, or `null` when not assessed |
| `submission_status` | `not_attempted`, `unverified`, `verified`, or `null` when not assessed |
| `blocker_codes` | list of unique strings, lexicographically sorted; `[]` when none/not assessed |
| `readiness_sha256` | lower-case 64-character SHA-256 string for a validated readiness report, otherwise `null` |
| `artifact_sha256` | lower-case 64-character final-manifest SHA-256 for positive offline acceptance, otherwise `null` |
| `acceptance` | the existing sanitized `offline_acceptance_to_dict` object for either offline outcome; `null` for `status` and every invalid result |
| `error_code` | `null` on non-error outcomes; exactly `INVALID_INPUT` for a domain-invalid result |
| `message` | `null` on non-error outcomes; exactly `invalid status input` or `invalid offline acceptance input` for the corresponding domain-invalid command |

The positive M4 `offline-acceptance` envelope has
`outcome="external_only_blocked"`, `local_status="complete"`, axis values
`passed/blocked/disabled/not_attempted`, its sorted readiness blocker codes,
non-null readiness and final-manifest SHA values, the sanitized positive
acceptance object, and `error_code=message=null`.

If the M4 API returns `OfflineAcceptanceBlockedResult`, the offline envelope
has `outcome="local_unsafe"`, `local_status="unsafe"`,
`offline_acceptance_status="failed"`, all three remaining axis fields `null`,
`blocker_codes=["blocked_sensitive_fixture"]`, both SHA fields `null`, the
sanitized blocked acceptance object, and `error_code=message=null`. M5 does not
provide a CLI option to intentionally produce this outcome; this branch is a
defensive serializer contract for the existing public M4 union type.

For `status`, `acceptance` and `artifact_sha256` are always `null`. A validated
bare/enveloped readiness report supplies the four axis fields, sorted blocker
codes, and its canonical `readiness_sha256`. A fully clear fixture produces
`local_complete`; a locally unsafe report produces `local_unsafe`; and a locally
complete report with only external-only blockers produces
`external_only_blocked`. A domain-invalid input uses the same 14-key shape with
all axis/SHA fields `null`, `blocker_codes=[]`, `acceptance=null`, and the fixed
error fields above. No envelope may include a path, raw fixture, signing
material, private field, name, email, phone, credential, URL query, or other
PII.

`offline-acceptance --output` is valid only with `--format json`. On success it
writes byte-identical canonical JSON plus a final newline to stdout and the
output file. It never prints the output path. Supplying `--output` with
`--format human` is a domain-invalid offline input (exit 4).

### Exact human summaries, streams, and exit codes

For non-error human results, stdout contains exactly these ten lines in this
order, each terminated by `\n`; stderr is empty:

```text
command: <status|offline-acceptance>
local: <complete|unsafe>
offline acceptance: <passed|failed|not_run|not_assessed>
external inputs: <ready|blocked|not_assessed>
live execution: <disabled|review_required|authorized|not_assessed>
submission: <not_attempted|unverified|verified|not_assessed>
blockers: <none|comma-separated sorted codes>
readiness sha256: <64-char SHA-256|none>
artifact sha256: <64-char SHA-256|none>
outcome: <local_complete|local_unsafe|external_only_blocked> (exit <0|2|3>)
```

The normal M4 positive output ends with `outcome: external_only_blocked (exit
3)` and still explicitly reports `local: complete`; it never claims live or
submission readiness.

For a domain-invalid human input, stdout is empty and stderr is exactly these
four lines, each terminated by `\n`:

```text
command: <status|offline-acceptance>
outcome: invalid_input (exit 4)
error: INVALID_INPUT
message: <invalid status input|invalid offline acceptance input>
```

For `--format json`, stdout is the exact JSON envelope described above and
stderr is empty, including domain-invalid results. The new command handlers
catch expected domain errors and never print a traceback. Invalid argparse
syntax (unknown option, missing required option, invalid choice) remains normal
argparse behavior: usage/error on stderr, no JSON guarantee, and exit 2. This
is distinct from a parsed command whose readiness/envelope/input validation
fails, which returns exit 4.

| command | reachable M5 outcome | exact exit |
| --- | --- | --- |
| `offline-acceptance` | positive M4 result: `external_only_blocked` | 3 |
| `offline-acceptance` | defensive `OfflineAcceptanceBlockedResult`: `local_unsafe` | 2 |
| `offline-acceptance` | parsed domain-invalid input, including `--output` with human format | 4 |
| `status` | validated fully-clear readiness fixture: `local_complete` | 0 |
| `status` | validated external-only-blocked readiness/envelope | 3 |
| `status` | validated locally unsafe readiness/envelope | 2 |
| `status` | parsed invalid input/envelope/readiness | 4 |

`offline-acceptance` intentionally has no exit-0 production path: M4 always
preserves external blockers. This prevents the CLI from treating local synthetic
acceptance as live/submission completion.

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

Its exact public shape is:

```python
def list_fixture_adapters() -> tuple[str, ...]: ...
```

For the current registry it must return exactly
`("jobkorea_jrs_fixture", "saramin_applyin_fixture")`. It calls
`validate_catalog(CATALOG)`, derives IDs only from `Platform.fixture_adapter_id`,
requires equality with the sorted unique values of
`FIXTURE_ADAPTER_REGISTRY`, and raises `PlatformCatalogError` for an empty,
duplicate, mismatched, live-enabled, or live-adapter entry. It neither imports
execution code nor returns platform objects, origins, paths, or capabilities.

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
The JSON tests assert exact top-level key sets and every value/null rule above
for positive, external-only blocked, local-unsafe, and invalid-input outcomes.
The human tests assert the exact ordered lines and stdout/stderr placement for
each of those outcomes. Sensitive literals are allowed only in negative test
input construction and must be absent from captured output and JSON.

Coverage is kept within the 12-node contract by making each named test exercise
the real formatter/command for all variants in its stated family: test 2 covers
positive and defensive-blocked offline JSON; test 3 covers their human summaries;
test 5 covers status external-only JSON; tests 6 and 7 cover status exits 0 and
2; test 8 covers JSON and human domain-invalid output for both commands; and
test 9 checks all successful status human line variants. These are multiple
assertions of distinct command outcomes, not parameterized node expansion or
wrapper tests.

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
