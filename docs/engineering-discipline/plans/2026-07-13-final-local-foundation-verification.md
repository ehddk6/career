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
this plan from a new clean commit. A transient or environmental failure is not
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

### 1. Test-repeat policy for full pytest

This is a test-repeat policy only. M6/M7 define no lint, formatter, or new
static-style requirement.

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
install build tooling, dependencies, extras, or use an index/network. Use an
exact, detached Git worktree that is robust for Windows paths and Unicode
filenames. The worktree removal below is allowed only after its resolved path
is proven to be the exact generated temporary directory.

```powershell
$TempParent = (Resolve-Path -LiteralPath ([System.IO.Path]::GetTempPath())).Path
$RunRoot = [System.IO.Path]::GetFullPath((Join-Path $TempParent ('career-pipeline-m6-' + [guid]::NewGuid().ToString('N')))
$Worktree = [System.IO.Path]::GetFullPath((Join-Path $RunRoot 'worktree'))
$WheelDir = Join-Path $RunRoot 'wheel'
$Venv = Join-Path $RunRoot 'venv'
if (-not $Worktree.StartsWith($RunRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) { throw 'worktree path escaped generated temp root' }
if (Test-Path -LiteralPath $RunRoot) { throw 'generated temporary root already exists' }
New-Item -ItemType Directory -Force $RunRoot, $WheelDir | Out-Null
git worktree add --detach $Worktree $Head
if ($LASTEXITCODE -ne 0) { throw 'detached temporary worktree creation failed' }
$WorktreeResolved = (Resolve-Path -LiteralPath $Worktree).Path
$RunRootResolved = (Resolve-Path -LiteralPath $RunRoot).Path
if ($WorktreeResolved -ne (Join-Path $RunRootResolved 'worktree')) { throw 'resolved worktree path mismatch' }
Push-Location $WorktreeResolved
python -m pip wheel . --no-deps --no-build-isolation --wheel-dir $WheelDir
Pop-Location
if ($LASTEXITCODE -ne 0) { throw 'offline wheel build failed' }
$SmokePython = Join-Path $Venv 'Scripts\python.exe'
$Wheel = @(Get-ChildItem $WheelDir -Filter 'career_pipeline-*.whl' | Select-Object -First 1)
if ($Wheel.Count -ne 1) { throw 'expected exactly one career-pipeline wheel' }
python -c "import zipfile,sys; names=zipfile.ZipFile(sys.argv[1]).namelist(); assert 'career_pipeline/__init__.py' in names; assert any(name.endswith('.dist-info/METADATA') for name in names)" $Wheel[0].FullName
if ($LASTEXITCODE -ne 0) { throw 'wheel content inspection failed' }
python -m venv --system-site-packages $Venv
& $SmokePython -m pip install --no-deps --no-index $Wheel[0].FullName
if ($LASTEXITCODE -ne 0) { throw 'offline wheel install failed' }
& $SmokePython -c "import docx,pypdf,openpyxl,yaml; print(docx.__version__, pypdf.__version__, openpyxl.__version__, yaml.__version__)"
if ($LASTEXITCODE -ne 0) { throw 'inherited runtime dependency check failed' }
```

Record the wheel SHA-256 and inherited dependency versions. This is a clean
project installation with inherited, already-verified base runtime dependencies;
it is not dependency isolation or a resolver/lockfile verification. Record
that limitation verbatim. If a backend or inherited runtime prerequisite is
missing, stop as `environment_blocked`; do not download or install anything.

### 4. Clean temporary CLI smoke

Smoke artifacts stay under `$RunRoot`. The manifest records only logical names,
byte sizes, SHA-256 values, commands, exits, and sanitized result fields. It
must not record `$RunRoot`, a user path, raw fixture content, or raw output.

```powershell
$Smoke = [System.IO.Path]::GetFullPath((Join-Path $RunRootResolved 'smoke'))
New-Item -ItemType Directory -Force $Smoke | Out-Null
$SmokeResolved = (Resolve-Path -LiteralPath $Smoke).Path
$EvidenceSha = (Get-FileHash (Join-Path $Repo 'tests\test_offline_acceptance.py') -Algorithm SHA256).Hash.ToLowerInvariant()
$SyntheticWorkspace = [System.IO.Path]::GetFullPath((Join-Path $SmokeResolved 'synthetic'))
$OfflineOutput = [System.IO.Path]::GetFullPath((Join-Path $SmokeResolved 'offline.json'))
Push-Location $SmokeResolved
& $SmokePython -c "import career_pipeline; print(career_pipeline.__name__)" *> import.txt
if ($LASTEXITCODE -ne 0) { throw 'import smoke failed' }
& $SmokePython -m career_pipeline --help *> help.txt
if ($LASTEXITCODE -ne 0) { throw 'help smoke failed' }
& $SmokePython -m career_pipeline offline-acceptance --workspace $SyntheticWorkspace --at 2026-07-13T12:00:00+09:00 --site-valid-until 2026-07-13T13:00:00+09:00 --test-evidence-sha256 $EvidenceSha --format json --output $OfflineOutput *> offline.stdout
if ($LASTEXITCODE -ne 3) { throw 'offline-acceptance must exit 3' }
& $SmokePython -m career_pipeline status --input offline.json --format json *> status.stdout
if ($LASTEXITCODE -ne 3) { throw 'status of the positive envelope must exit 3' }
& $SmokePython -m career_pipeline status --input missing.json --format json *> invalid.stdout
if ($LASTEXITCODE -ne 4) { throw 'status missing input must exit 4' }
& $SmokePython -m career_pipeline unsupported-command *> argparse.stderr
if ($LASTEXITCODE -ne 2) { throw 'argparse invalid command must exit 2' }
Pop-Location
```

`--workspace` and `--output` above are resolved absolute paths. `status --input`
is intentionally the relative `offline.json`/`missing.json` because strict M5
status input rejects absolute paths; its current directory is the resolved
absolute `$SmokeResolved`. This is the only relative-path exception in the
smoke commands.

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
Do not recursively remove `$RunRoot` during verification. A leftover generated
temporary root is an environment observation, never a product change.

After the hash capture and before any optional deletion of the generated
temporary root, remove only the exact detached worktree. Do not run a recursive
delete over `$RunRoot` or a computed parent path:

```powershell
if ($WorktreeResolved -ne (Join-Path $RunRootResolved 'worktree')) { throw 'refuse to remove unexpected worktree' }
git worktree remove --force $WorktreeResolved
if ($LASTEXITCODE -ne 0) { throw 'detached temporary worktree removal failed' }
if (Test-Path -LiteralPath $WorktreeResolved) { throw 'worktree path still exists after removal' }
git worktree list --porcelain
```

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

Every scan match has exactly one of these classifications:

- `allowed_negative`: a counter, negative test assertion, parser rejection, or
  documentation sentence that explicitly denies a live action.
- `existing_required_transport`: only the existing official-source transport in
  `career_pipeline/posting_loader.py`: imports at lines 7 and 9–11, the
  injected `Transport` contract, `_default_transport`, and the URL branch of
  `load_posting_source` at lines 159–205. It is permitted only after the
  reviewer confirms its public-HTTPS and official-domain guards remain intact.
- `forbidden`: every other new executable network/browser/mutation/credential
  access, including any such call reachable from `run_m5_command`,
  `run_m5_offline_acceptance`, `run_m5_status`, or helpers whose name starts
  `_m5_`.

Run this additional reachability check. It must print `m5 paths clear` and has
no allowed exception:

```powershell
@'
import ast
from pathlib import Path
tree = ast.parse(Path('career_pipeline/__main__.py').read_text(encoding='utf-8'))
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and (node.name.startswith('_m5_') or node.name in {'run_m5_command', 'run_m5_offline_acceptance', 'run_m5_status'}):
        names = {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}
        assert 'load_posting_source' not in names, node.name
print('m5 paths clear')
'@ | python -
```

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
  "security_scans": [{"id": "string", "matches": [{"file": "repo-relative", "line": 1, "classification": "allowed_negative|existing_required_transport|forbidden", "detail": "string"}], "passed": true}],
  "docs_skill_contract": {"files": [{"path": "repo-relative", "sha256": "lowercase SHA-256"}], "passed": true},
  "symlink_checks": {"status": "passed|unverified_platform_capability", "skips": [{"node": "string", "reason": "string"}]},
  "external_blockers": ["ORIGIN_UNCONFIRMED", "DOM_UNVERIFIED", "AUTOMATION_POLICY_UNCONFIRMED", "CREDENTIALS_UNAVAILABLE", "MFA_REQUIRED", "CAPTCHA_PRESENT", "PII_TRANSMISSION_UNAUTHORIZED", "UPLOAD_NOT_AUTHORIZED", "CLICK_NOT_AUTHORIZED", "SUBMIT_NOT_AUTHORIZED", "RECEIPT_UNVERIFIED"],
  "working_tree": {"clean_before": true, "clean_after": true, "status_porcelain": []},
  "limitations": ["string"],
  "verdict": "pass|fail|blocked"
}
```

No field may contain an absolute path, user name, raw output, secret, PII, raw
HTML, or external URL query/fragment. The M6 checkpoint must link to this
manifest and its SHA-256, summarize both full-suite runs, identify unverified
symlink capability, record the inherited-runtime-dependencies limitation, and
restate external blockers.

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

### Manifest validation rules

The M6 top-level key set is exactly `schema_version`, `generated_at`,
`repository`, `commands`, `test_runs`, `artifacts`, `smoke`,
`security_scans`, `docs_skill_contract`, `symlink_checks`,
`external_blockers`, `working_tree`, `limitations`, and `verdict`.

| field | required type and rule |
| --- | --- |
| `schema_version`, `generated_at`, `verdict` | string; schema exactly `career-pipeline-final-local-foundation-v1`, timestamp timezone-aware, verdict one of `pass`, `fail`, `blocked` |
| `repository` | object with exactly five non-empty full 40-hex SHA strings shown in the schema |
| `commands` | array; every object has exactly `id`, `argv`, `cwd`, `expected_exit`, `observed_exit`, `outcome`, `stdout_sha256`, `stderr_sha256`; argv is string array, exits are integers, cwd is `repo` or `temporary` |
| `test_runs` | array of exact objects shown; counts are non-negative integers, node is string or null, stdout hash is lowercase SHA-256 |
| `artifacts` | array of exact logical-name/SHA/byte objects; bytes is a non-negative integer and logical names contain no path separator |
| `smoke` | exact object shown; integer exits must be `0`, `0`, `3`, `3`, `4`, `2` in the named order and `public_output_safe=true` |
| `security_scans` | array; `classification` is only `allowed_negative`, `existing_required_transport`, or `forbidden`; a PASS manifest contains no `forbidden` match |
| `docs_skill_contract` | exact object; every path is repository-relative and every SHA is lowercase 64-hex |
| `symlink_checks` | exact object; status only `passed` or `unverified_platform_capability`, and every skip has a node and reason string |
| `external_blockers` | sorted unique string array containing exactly the 11 listed blocker codes |
| `working_tree` | exact object; both booleans true and `status_porcelain=[]` |
| `limitations` | string array; must include the inherited-runtime-dependencies limitation when `--system-site-packages` is used |

## Exact predecessor checklist for M7

The fresh reviewer validates every row against the final tree; it does not
accept an undocumented replacement commit or inferred result.

| milestone | required commits and checkpoint | review verdict | full-suite evidence | security/boundary evidence |
| --- | --- | --- | --- | --- |
| M1 | `c663e1504f7d11e1b13573e2c9041fc7ab959800`; `checkpoints/M1-checkpoint.md` | `reviews/2026-07-12-site-intake-fail-closed-review.md`: PASS | `425 passed, 2 skipped` | read-only intake; mutation/live disabled; no browser/network/PII/mutation leak |
| M2 | `6b3d03d`, `b5b6db7`, `a92f366`, `3798f8b`, `20a288b`; `checkpoints/M2-checkpoint.md` | `2026-07-12-shared-safety-kernel-review.md` and `2026-07-12-readiness-contract-review.md`: PASS WITH REVIEWER LIMITATION (HTTP 429), therefore M7 must re-audit | `471 passed, 5 skipped` | shared path/origin confinement, versioned readiness axes, no live/browser/credential/PII/upload/click/submit |
| M3 | `42f8b0f`; `checkpoints/M3-checkpoint.md` | `2026-07-12-contract-bound-authorization-review.md`: PASS; final documentation-only reviewer hit a usage limit, therefore M7 must re-audit | `513 passed, 5 skipped` | V2 bindings, disabled contracts cannot authorize, legacy fail-closed, probes before mutation |
| M4 | `7f68329`; `checkpoints/M4-checkpoint.md` | `reviews/2026-07-13-offline-acceptance-review.md`: PASS | `528 passed, 5 skipped` | deterministic synthetic acceptance, zero network/browser/credential/PII/upload/click/submit counters, external blockers preserved |
| M5 | `2d30f8b`, `72aa59c`, `f1c3be9`; `checkpoints/M5-checkpoint.md` | `reviews/2026-07-13-cli-operational-gate-review.md`: PASS | `541 passed, 5 skipped`; Windows lock regression `10/10` | canonical CLI envelopes, exits `3/2/4/2`, strict confined status input, no secret/PII/absolute path/raw fixture/live capability |
| M6 | M6 evidence commit and `checkpoints/M6-checkpoint.md` | M6 manifest self-consistent; M7 is the independent verdict | two recorded M6 full runs, with every retry retained | clean tree, worktree wheel/install smoke, product/docs scans, symlink capability classified, external blockers unchanged |

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

The reviewer starts a new PowerShell session in the reviewed tree and executes
this transcript before writing any review artifact:

```powershell
$ErrorActionPreference = 'Stop'
$ReviewRepo = (Get-Location).Path
$ReviewHead = (git rev-parse HEAD).Trim()
$M6Manifest = 'docs/engineering-discipline/harness/career-pipeline-completion/manifests/2026-07-13-m6-local-foundation.json'
if (@(git status --porcelain=v1).Count -ne 0) { throw 'M7 requires a clean reviewed tree' }
if (-not (Test-Path -LiteralPath $M6Manifest)) { throw 'M6 manifest missing' }
python -m pytest -q -rs
if ($LASTEXITCODE -ne 0) { throw 'M7 full pytest failed' }
python -m compileall -q career_pipeline
if ($LASTEXITCODE -ne 0) { throw 'M7 compileall failed' }
git diff --check
if ($LASTEXITCODE -ne 0) { throw 'M7 diff check failed' }
```

Next, the reviewer executes the literal M6 sections **3**, **4**, and **5**
above unchanged after assigning `$Head = $ReviewHead` and `$Repo = $ReviewRepo`.
Those sections define the exact detached-worktree creation/removal, wheel
inspection, inherited-dependency limitation, resolved-absolute workspace
arguments, `0/0/3/3/4/2` smoke exits, and scan commands. The reviewer must not
reuse an M6 temporary root or M6 captured output.

M7 PASS requires all of the following: the reviewed tree is clean before and
after commands; full pytest, compileall, and diff check pass; every smoke exit
matches; the wheel contains the project package and metadata; the inherited
runtime-dependency limitation is recorded; no `forbidden` scan match exists;
every `existing_required_transport` match is confined to the exact
`posting_loader.py` allowlist and M5 reachability check prints `m5 paths clear`;
all four docs/skill files agree; M6 and final manifests validate their exact
schemas; and every predecessor row above is either `validated` or explicitly
`unverified_platform_capability` for a symlink-host limitation only.

The reviewer issues `PASS`, `FAIL`, or `BLOCKED` with direct evidence. A
symlink-creation skip remains `unverified_platform_capability`. M7 fails on a
regression, mismatched digest/ID/status, unrecorded test failure, dirty tree,
live capability, secret/PII/absolute-path leakage, or a claim that external
blockers were resolved locally. It must not implement a fix; a defect returns
to the separate corrective-fix path and restarts M6/M7.

On PASS, create the M7 Markdown review and final JSON manifest. Its top-level
key set is exactly `schema_version`, `generated_at`, `repository`, `commands`,
`test_runs`, `artifacts`, `smoke`, `security_scans`, `docs_skill_contract`,
`symlink_checks`, `external_blockers`, `working_tree`, `limitations`,
`m6_manifest_sha256`, `m7_reviewer`, `predecessor_checkpoints`, and
`final_verdict`. The first thirteen fields use the exact M6 types and rules
above; `final_verdict` is `pass`, `fail`, or `blocked`.

The final manifest must contain all keys, not a JSON merge or a pointer to
omitted M6 fields:

```json
{
  "schema_version": "career-pipeline-final-integration-verification-v1",
  "generated_at": "ISO-8601-with-timezone",
  "repository": {"baseline_commit": "full SHA", "m5_feature_commit": "full SHA", "m5_lock_fix_commit": "full SHA", "m5_checkpoint_commit": "full SHA", "verified_head": "full SHA"},
  "commands": [{"id": "string", "argv": ["string"], "cwd": "repo|temporary", "expected_exit": 0, "observed_exit": 0, "outcome": "passed|failed|skipped|environment_blocked", "stdout_sha256": "sha256-or-null", "stderr_sha256": "sha256-or-null"}],
  "test_runs": [{"attempt": 1, "kind": "full|targeted", "node": "node-or-null", "result": "passed|failed", "passed": 0, "failed": 0, "skipped": 0, "stdout_sha256": "sha256"}],
  "artifacts": [{"logical_name": "string", "sha256": "lowercase SHA-256", "bytes": 0}],
  "smoke": {"import_exit": 0, "help_exit": 0, "offline_acceptance_exit": 3, "status_exit": 3, "invalid_status_exit": 4, "argparse_exit": 2, "public_output_safe": true},
  "security_scans": [{"id": "string", "matches": [{"file": "repo-relative", "line": 1, "classification": "allowed_negative|existing_required_transport|forbidden", "detail": "string"}], "passed": true}],
  "docs_skill_contract": {"files": [{"path": "repo-relative", "sha256": "lowercase SHA-256"}], "passed": true},
  "symlink_checks": {"status": "passed|unverified_platform_capability", "skips": [{"node": "string", "reason": "string"}]},
  "external_blockers": ["sorted unique blocker codes"],
  "working_tree": {"clean_before": true, "clean_after": true, "status_porcelain": []},
  "limitations": ["string"],
  "m6_manifest_sha256": "lowercase SHA-256",
  "m7_reviewer": {"mode": "fresh_independent_final_tree_only", "commit": "full SHA", "verdict": "pass|fail|blocked", "commands_reexecuted": ["id"]},
  "predecessor_checkpoints": [{"id": "M1", "path": "repo-relative", "sha256": "lowercase SHA-256", "status": "validated|unverified_platform_capability"}],
  "final_verdict": "pass|fail|blocked"
}
```

`m6_manifest_sha256` is a lowercase 64-hex string. `m7_reviewer` has exactly
the four shown keys; its commit is the reviewed full SHA and its command IDs
must refer to entries in `commands`. `predecessor_checkpoints` contains exactly
M1, M2, M3, M4, M5, and M6 once each, in order; every path is repository-relative
and every status is `validated` or `unverified_platform_capability`.

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
