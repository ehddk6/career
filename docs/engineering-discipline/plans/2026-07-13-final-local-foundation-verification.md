# M6 + M7 Final Local Foundation Verification Plan

## Scope and non-goals

This is an execution-only plan for M6 (final local foundation checkpoint) and
M7 (integration verification). It adds no product capability. It must not fetch
a site, launch a browser, read credentials or real PII, upload, click, submit,
collect a receipt, push, create a PR, merge, deploy, or use a live application
surface.

The only claim eligible for PASS is that the committed repository satisfies its
local synthetic contracts. `external_only_blocked`, disabled live execution,
and `not_attempted` submission remain external boundaries.

M6 starts only from the clean M5 lineage containing `2d30f8b` (feature),
`72aa59c` (Windows lock correction), and `f1c3be9` (M5 checkpoint). Record the
resolved full SHAs; do not assume a branch name. Record historical foundation
baseline `809929c` without checking it out or resetting to it.

## Ownership

This planning change owns only this file. Future M6/M7 execution may create or
update only:

- `docs/engineering-discipline/harness/career-pipeline-completion/manifests/2026-07-13-m6-local-foundation.json`
- `docs/engineering-discipline/harness/career-pipeline-completion/checkpoints/M6-checkpoint.md`
- `docs/engineering-discipline/harness/career-pipeline-completion/reviews/2026-07-13-m7-integration-review.md`
- `docs/engineering-discipline/harness/career-pipeline-completion/manifests/2026-07-13-final-local-foundation-verification.json`
- `docs/engineering-discipline/harness/career-pipeline-completion/milestones/M6-final-checkpoint.md`
- `docs/engineering-discipline/harness/career-pipeline-completion/milestones/M7-integration-verification.md`
- `docs/engineering-discipline/harness/career-pipeline-completion/state.md`

Do not modify product code, tests, package configuration, M1–M5 checkpoints,
or previous reviews during normal M6/M7 execution. If verification exposes a
reproducible product defect, stop M6/M7. Make the smallest separate corrective
fix with a direct regression test and a separate `fix:` commit, then restart
this plan from a new clean commit. A flaky or environmental failure is not
authorization for a code change.

## Preflight: clean immutable target

Run from the repository root before writing M6 evidence:

```powershell
$ErrorActionPreference = 'Stop'
$Repo = (Get-Location).Path
$Head = (git rev-parse HEAD).Trim()
$Baseline = (git rev-parse 809929c^{commit}).Trim()
$M5Feature = (git rev-parse 2d30f8b^{commit}).Trim()
$M5LockFix = (git rev-parse 72aa59c^{commit}).Trim()
$M5Checkpoint = (git rev-parse f1c3be9^{commit}).Trim()
$M5Range = "${M5Checkpoint}..${Head}"
$Dirty = @(git status --porcelain=v1)
git diff --check
git diff --cached --check
git fsck --no-reflogs --no-progress
if ($Dirty.Count -ne 0) { throw 'M6 requires a clean working tree' }
git merge-base --is-ancestor $M5Checkpoint $Head
if ($LASTEXITCODE -ne 0) { throw 'HEAD does not contain the M5 checkpoint' }
```

The plan file and any unfinished M5 changes must be committed by their owners
before this gate. Do not hide changes with reset, checkout, stash, broad
staging, or untracked-file deletion. Record `HEAD`, all resolved commits,
`status_porcelain=[]`, and the `git fsck` result in the M6 manifest.

## M6 commands and acceptance rules

### 1. Repeated full pytest

Run once with skip reasons, then once more after a pass:

```powershell
python -m pytest -q -rs
python -m pytest -q
```

If either full run fails, retain its stdout/stderr hashes and classify it. A
Windows lock failure may be retried only after recording the exact failing node:

```powershell
python -m pytest -q <exact-failing-node>
python -m pytest -q <exact-failing-node>
python -m pytest -q <exact-failing-node>
```

Then restart the two-full-run sequence. Stop after three total full-suite
attempts or after any repeated/non-lock failure. A retry never deletes a failed
attempt from evidence.

For each `-rs` skip record node ID and reason. A skip saying symlink creation is
unavailable is `unverified_platform_capability`, never passed. Do not create a
junction, elevate privileges, or otherwise alter the host to eliminate it.

### 2. Compile and repository gates

```powershell
python -m compileall -q career_pipeline
git diff --check
git diff --cached --check
git status --porcelain=v1
git diff --name-only $M5Range
```

All commands must exit zero and the final status output must be empty.

### 3. Existing-backend offline build and install

Use only `setuptools.build_meta` already declared in `pyproject.toml`. Do not
install build tooling, dependencies, extras, or use an index/network. Build a
`git archive` copy so the repository remains clean.

```powershell
$RunRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('career-pipeline-m6-' + [guid]::NewGuid().ToString('N'))
$Source = Join-Path $RunRoot 'source'
$WheelDir = Join-Path $RunRoot 'wheel'
$Venv = Join-Path $RunRoot 'venv'
New-Item -ItemType Directory -Force $Source, $WheelDir | Out-Null
git archive --format=tar $Head | tar -xf - -C $Source
Push-Location $Source
python -m pip wheel --no-deps --no-build-isolation --wheel-dir $WheelDir .
Pop-Location
python -m venv $Venv
$SmokePython = Join-Path $Venv 'Scripts\python.exe'
$Wheel = @(Get-ChildItem $WheelDir -Filter 'career_pipeline-*.whl' | Select-Object -First 1)
if ($Wheel.Count -ne 1) { throw 'expected exactly one career-pipeline wheel' }
& $SmokePython -m pip install --no-deps --no-index $Wheel[0].FullName
if ($LASTEXITCODE -ne 0) { throw 'offline wheel install failed' }
```

Record the wheel SHA-256. If an already-installed backend prerequisite is
missing, stop as `environment_blocked`; do not download or install anything.

### 4. Clean temporary CLI smoke

Smoke artifacts stay under `$RunRoot`. The manifest records only logical names,
byte sizes, SHA-256 values, commands, exits, and sanitized result fields. It
must not record `$RunRoot`, a user path, raw fixture content, or raw output.

```powershell
$Smoke = Join-Path $RunRoot 'smoke'
New-Item -ItemType Directory -Force $Smoke | Out-Null
$EvidenceSha = (Get-FileHash (Join-Path $Repo 'tests\test_offline_acceptance.py') -Algorithm SHA256).Hash.ToLowerInvariant()
Push-Location $Smoke
& $SmokePython -c "import career_pipeline; print(career_pipeline.__name__)" *> import.txt
if ($LASTEXITCODE -ne 0) { throw 'import smoke failed' }
& $SmokePython -m career_pipeline --help *> help.txt
if ($LASTEXITCODE -ne 0) { throw 'help smoke failed' }
& $SmokePython -m career_pipeline offline-acceptance --workspace synthetic --at 2026-07-13T12:00:00+09:00 --site-valid-until 2026-07-13T13:00:00+09:00 --test-evidence-sha256 $EvidenceSha --format json --output offline.json *> offline.stdout
if ($LASTEXITCODE -ne 3) { throw 'offline-acceptance must exit 3' }
& $SmokePython -m career_pipeline status --input offline.json --format json *> status.stdout
if ($LASTEXITCODE -ne 3) { throw 'status of the positive envelope must exit 3' }
& $SmokePython -m career_pipeline status --input missing.json --format json *> invalid.stdout
if ($LASTEXITCODE -ne 4) { throw 'status missing input must exit 4' }
& $SmokePython -m career_pipeline unsupported-command *> argparse.stderr
if ($LASTEXITCODE -ne 2) { throw 'argparse invalid command must exit 2' }
Pop-Location
```

Parse `offline.json` and `status.stdout` as UTF-8 JSON. Require canonical key
order and one final newline. Required outcomes are:

| artifact | required result |
| --- | --- |
| `offline.json` | `command=offline-acceptance`, `outcome=external_only_blocked`, `local_status=complete`, `offline_acceptance_status=passed`, `external_inputs_status=blocked`, `live_execution_status=disabled`, `submission_status=not_attempted`, exit `3` |
| `status.stdout` | `command=status`, `kind=status`, `acceptance=null`, `outcome=external_only_blocked`, exit `3` |
| `invalid.stdout` | `outcome=invalid_input`, `error_code=INVALID_INPUT`, exit `4` |
| `argparse.stderr` | no JSON contract; exit `2` |

Reject public strings containing raw HTML, sentinel values, signing material,
PII, absolute user/workspace paths, `file:` URLs, or query/fragment values. The
only path-like runtime exception is a readiness evidence `source` matching
`^(?:career_pipeline|tests|docs|\.agents)(?:/[A-Za-z0-9][A-Za-z0-9._-]*)+$`.
Remove `$RunRoot` only after recording sanitized hashes; a Windows cleanup
failure is an environment observation, never a product change.

### 5. Security, privacy, and documentation/skill scans

Run these exact scans and record every match with repository-relative file,
line, and classification:

```powershell
git diff --unified=0 $M5Range -- career_pipeline tests docs .agents pyproject.toml | Select-String -Pattern '^[+].*(requests|httpx|urllib\.request|socket|selenium|playwright|page\.goto|page\.click|page\.press|set_input_files|upload|submit)'
git diff --unified=0 $M5Range -- career_pipeline tests docs .agents pyproject.toml | Select-String -Pattern '^[+].*(os\.environ|dotenv|keyring|CAREER_.*KEY|password|token|secret|full_name|email|phone|C:\\Users|/home/)'
git diff --unified=0 $M5Range -- career_pipeline | Select-String -Pattern '^[+].*(datetime\.now|time\.time|os\.environ|dotenv|keyring)'
rg -n --glob '*.py' '(requests|httpx|urllib\.request|socket|selenium|playwright|page\.goto|page\.click|page\.press|set_input_files)' career_pipeline
rg -n -i '(live ready|submission ready|submit supported|credential|real pii|offline-acceptance|external_only_blocked)' docs .agents\skills\career-pipeline\SKILL.md
```

A counter name, negative assertion, or prose saying an action is unsupported is
allowed only if it cannot invoke that action or disclose a value. Any new
executable network/browser/mutation call, credential read, raw secret/PII,
absolute user path, or live/submission-ready claim fails M6.

Perform a consistency check on these four files:

- `docs/career-pipeline-usage.md`
- `docs/application-execution.md`
- `docs/site-intake.md`
- `.agents/skills/career-pipeline/SKILL.md`

Their M5 wording must preserve `offline-acceptance`, strict `status --input`,
normal exit `3`, `external_only_blocked`, disabled live execution, and
not-attempted submission. Record required-literal results and SHA-256 for every
file.

## M6 evidence schema and commit

Create `2026-07-13-m6-local-foundation.json` as sorted UTF-8 JSON with one final
newline and this exact shape:

```json
{
  "schema_version": "career-pipeline-final-local-foundation-v1",
  "generated_at": "ISO-8601-with-timezone",
  "repository": {"baseline_commit": "full SHA", "m5_feature_commit": "full SHA", "m5_lock_fix_commit": "full SHA", "m5_checkpoint_commit": "full SHA", "verified_head": "full SHA"},
  "commands": [{"id": "string", "argv": ["string"], "cwd": "repo|temporary", "expected_exit": 0, "observed_exit": 0, "outcome": "passed|failed|skipped|environment_blocked", "stdout_sha256": "sha256-or-null", "stderr_sha256": "sha256-or-null"}],
  "test_runs": [{"attempt": 1, "kind": "full|targeted", "node": "node-or-null", "result": "passed|failed", "passed": 0, "failed": 0, "skipped": 0, "stdout_sha256": "sha256"}],
  "artifacts": [{"logical_name": "string", "sha256": "lowercase SHA-256", "bytes": 0}],
  "smoke": {"import_exit": 0, "help_exit": 0, "offline_acceptance_exit": 3, "status_exit": 3, "invalid_status_exit": 4, "argparse_exit": 2, "public_output_safe": true},
  "security_scans": [{"id": "string", "matches": [{"file": "repo-relative", "line": 1, "classification": "allowed_negative|forbidden"}], "passed": true}],
  "docs_skill_contract": {"files": [{"path": "repo-relative", "sha256": "lowercase SHA-256"}], "passed": true},
  "symlink_checks": {"status": "passed|unverified_platform_capability", "skips": [{"node": "string", "reason": "string"}]},
  "external_blockers": ["ORIGIN_UNCONFIRMED", "DOM_UNVERIFIED", "AUTOMATION_POLICY_UNCONFIRMED", "CREDENTIALS_UNAVAILABLE", "MFA_REQUIRED", "CAPTCHA_PRESENT", "PII_TRANSMISSION_UNAUTHORIZED", "UPLOAD_NOT_AUTHORIZED", "CLICK_NOT_AUTHORIZED", "SUBMIT_NOT_AUTHORIZED", "RECEIPT_UNVERIFIED"],
  "working_tree": {"clean_before": true, "clean_after": true, "status_porcelain": []},
  "verdict": "pass|fail|blocked"
}
```

No field may contain an absolute path, user name, raw output, secret, PII, raw
HTML, or external URL query/fragment. The M6 checkpoint must link to this
manifest and its SHA-256, summarize both full-suite runs, identify unverified
symlink capability, and restate external blockers.

Commit M6 evidence only after manifest and checkpoint agree:

```powershell
git add -- docs/engineering-discipline/harness/career-pipeline-completion/manifests/2026-07-13-m6-local-foundation.json docs/engineering-discipline/harness/career-pipeline-completion/checkpoints/M6-checkpoint.md docs/engineering-discipline/harness/career-pipeline-completion/milestones/M6-final-checkpoint.md docs/engineering-discipline/harness/career-pipeline-completion/state.md
git diff --cached --check
git diff --cached --name-only
git commit -m "docs: record M6 local foundation verification"
git status --porcelain=v1
```

The final status must be empty. Do not amend, push, create a PR, merge, or
deploy.

## M7 fresh independent integration review

Create a fresh reviewer after the M6 commit. The reviewer receives only this
plan and the final checked-out repository tree at the M6 commit. It receives no
prior chat history, conclusions, hidden temporary artifacts, or request to
trust M6; it may read the M6 manifest in the final tree.

The reviewer independently reruns:

1. clean-tree and manifest-hash verification;
2. `python -m pytest -q -rs`, `python -m compileall -q career_pipeline`, and
   `git diff --check`;
3. the exact existing-backend wheel/install/import/help/offline/status smoke
   and exit matrix above;
4. product-surface, output-redaction, and documentation/skill scans; and
5. predecessor M1–M6 checks for public schemas, IDs, SHA-256 bindings,
   confinement, zero counters, and the no-live boundary.

The reviewer issues `PASS`, `FAIL`, or `BLOCKED` with direct evidence. A
symlink-creation skip remains `unverified_platform_capability`. M7 fails on a
regression, mismatched digest/ID/status, unrecorded test failure, dirty tree,
live capability, secret/PII/absolute-path leakage, or a claim that external
blockers were resolved locally. It must not implement a fix; a defect returns
to the separate corrective-fix path and restarts M6/M7.

On PASS, create the M7 Markdown review and final JSON manifest. The final
manifest repeats the M6 evidence and adds:

```json
{
  "schema_version": "career-pipeline-final-integration-verification-v1",
  "m6_manifest_sha256": "lowercase SHA-256",
  "m7_reviewer": {"mode": "fresh_independent_final_tree_only", "commit": "full SHA", "verdict": "pass|fail|blocked", "commands_reexecuted": ["id"]},
  "predecessor_checkpoints": [{"id": "M1", "path": "repo-relative", "sha256": "lowercase SHA-256", "status": "validated|unverified_platform_capability"}],
  "final_verdict": "pass|fail|blocked"
}
```

Commit only final M7 evidence:

```powershell
git add -- docs/engineering-discipline/harness/career-pipeline-completion/reviews/2026-07-13-m7-integration-review.md docs/engineering-discipline/harness/career-pipeline-completion/manifests/2026-07-13-final-local-foundation-verification.json docs/engineering-discipline/harness/career-pipeline-completion/milestones/M7-integration-verification.md docs/engineering-discipline/harness/career-pipeline-completion/state.md
git diff --cached --check
git diff --cached --name-only
git commit -m "docs: record M7 integration verification"
git status --porcelain=v1
```

The final status must be empty. Stop there: no push, PR, merge, deployment,
live-site action, or submission is authorized.
