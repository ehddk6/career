# Shared Safety Kernel Implementation Plan

> **Worker note:** Execute this plan task-by-task. Do not implement M2B readiness, M3 authorization-v2, M4 acceptance, CLI changes, or live adapters. Before every stage/commit, preserve unrelated work and stage only the exact pathspec listed in that task.

**Goal:** Extract one dependency-safe policy layer for exact HTTPS origins, workspace-confined paths, atomic persistence, exclusive locks, and read-only stale-lock diagnosis while preserving all existing public APIs and the repository's no-live/no-network boundary.

**Architecture:** Add leaf modules `origin_policy.py` and `path_policy.py`; neither may import application/package/site/CLI modules. Existing modules retain their public functions and domain-specific exception types, but delegate origin, confinement, atomic-write, and lock mechanics to the leaf modules. Lock files contain non-secret ownership metadata, are created with exclusive-create semantics, and are never removed merely because diagnosis considers them stale.

**Tech Stack:** Python 3.11+, standard library (`pathlib`, `urllib.parse`, `tempfile`, `os`, `stat`, `json`, `socket`, `uuid`, `datetime`, `contextlib`, `time`), pytest 8+; Windows/PowerShell and OneDrive-compatible filesystem behavior.

**Work Scope:**

- **In scope:** shared origin and path/persistence APIs; compatibility wrappers in `application_execution.py`; catalog dependency inversion; migration of existing execution-ledger, package-registry, and site-intake persistence/locks; focused negative tests for Windows paths, links, failed replace, stale locks, and concurrent writers.
- **Out of scope:** authorization schema v2 or site-contract bindings (M3); readiness schema/report (M2B); offline acceptance runner (M4); `__main__.py`/CLI path migration (M5); network/browser/live adapter work; changing artifact schemas; deleting or recovering stale locks; broad replacement of historical `write_text()` calls.

**Compatibility constraints:**

- Keep `career_pipeline.application_execution.normalize_origin(value: str) -> str` importable and preserve `ApplicationExecutionError` for all existing execution callers.
- Keep `write_json`, `write_state`, `write_application_package`, `register_application_package`, `persist_application_package`, `load_fixture_resource`, `persist_intake`, and every existing public call signature unchanged.
- Preserve current JSON formatting: UTF-8, `ensure_ascii=False`, two-space indent, `default=str`, and one trailing newline.
- Preserve current error substrings asserted by tests (`origin`, `workspace`, `symlink`, `lock timeout`, `could not acquire application registry lock`, `registry lock timeout`, and the existing fixture error codes).
- Do not add a production dependency. Do not perform network requests, browser launch/mutation, credential access, upload, click, or submit in new code/tests.

**Verification Strategy:**

- **Level:** integration and full test suite.
- **Focused baseline:** `python -m pytest -q tests/test_platform_catalog.py tests/test_application_execution.py tests/test_application_package.py tests/test_site_intake.py` currently reports `114 passed, 1 skipped`.
- **Full baseline:** `python -m pytest -q` currently reports `425 passed, 2 skipped`.
- **Final commands:** focused M2A suite, full pytest, `python -m compileall -q career_pipeline`, `git diff --check`, dependency/security scans, and a staged-file whitelist check.
- **What passing proves:** shared policies preserve existing artifact/API behavior, reject the required filesystem/origin escapes, serialize concurrent writers, leave prior files intact on replacement failure, and do not imply or invoke live readiness.

---

## Locked file map

### Create

- `career_pipeline/origin_policy.py` — dependency-free origin parsing and normalization.
- `career_pipeline/path_policy.py` — confinement, reparse-point detection, atomic writes, exclusive locking, and read-only lock diagnosis.
- `tests/test_origin_policy.py` — origin-policy unit and import-boundary tests.
- `tests/test_path_policy.py` — Windows path/link, atomic failure, stale-lock, and concurrency tests.

### Modify

- `career_pipeline/state.py` — retain JSON serialization and delegate the durable replacement to `atomic_write_text`.
- `career_pipeline/platform_catalog.py` — import origin policy directly, eliminating its dependency on execution code.
- `career_pipeline/application_execution.py` — retain compatibility wrappers/domain errors; delegate origin parsing, lock acquisition, and atomic persistence.
- `career_pipeline/application_package.py` — retain domain APIs/errors; delegate confinement/link checks and registry locks.
- `career_pipeline/site_intake.py` — retain URL/fixture semantics and error codes; delegate fixture confinement/link checks and registry locks.
- `tests/test_platform_catalog.py` — prove the dependency inversion and unchanged catalog behavior.
- `tests/test_application_execution.py` — prove compatibility error mapping and shared lock behavior.
- `tests/test_application_package.py` — prove Windows escape/link rejection and registry concurrency after migration.
- `tests/test_site_intake.py` — prove common lock behavior without weakening fixture/registry contracts.

### Explicitly do not modify

- `career_pipeline/__main__.py`, adapters, model/schema files, `career_pipeline/readiness.py`, `career_pipeline/offline_acceptance.py`, any M2B/M3/M4/M5 files, harness state/milestone/review files, and unrelated tests.
- The existing `_phase4_path()` remains in `__main__.py` for now. Its callers are already workspace-confined; replacing that public CLI boundary is deferred to M5 to avoid cross-worker conflict.

## Public API and types to freeze

### `career_pipeline.origin_policy`

| Symbol | Exact declaration |
|---|---|
| Error | `class OriginPolicyError(ValueError)` |
| Bare origin | `def normalize_origin(value: str) -> str` |
| URL-to-origin | `def origin_from_url(value: str) -> str` |

- Both functions require a credential-free `https` URL, reject control characters and wildcard hosts, IDNA-normalize and case-fold the host, remove one terminal dot, validate the port, bracket IPv6 literals, and return `https://<host>:<effective-port>`.
- `normalize_origin()` additionally rejects path other than `""` or `"/"`, query, and fragment.
- `origin_from_url()` permits path/query/fragment but never includes them in the returned origin.
- Default port is always rendered as `:443`, preserving current authorization/catalog values.
- Do not add platform-family classification, sensitive-query policy, network resolution, or public-suffix logic to this module.

### `career_pipeline.path_policy`

```python
from dataclasses import dataclass
from typing import Literal

class PathPolicyError(ValueError):
    """Base error for shared filesystem policy."""

class PathConfinementError(PathPolicyError):
    """A candidate cannot be proven to remain under its root."""

class PathLinkError(PathConfinementError):
    """A candidate or existing ancestor is a symlink or reparse point."""

class LockAcquisitionError(PathPolicyError):
    """A lock cannot be safely acquired or released."""

@dataclass(frozen=True)
class LockOwner:
    schema_version: int
    owner_token: str
    pid: int
    hostname: str
    created_at: str

@dataclass(frozen=True)
class LockDiagnosis:
    status: Literal["absent", "held", "stale_suspected", "malformed"]
    lock_path: str
    age_seconds: float | None
    owner: LockOwner | None
```

| Function | Exact signature |
|---|---|
| Confinement | `confine_path(root: Path, candidate: str | Path, *, must_exist: bool = True, require_file: bool = False, reject_links: bool = True) -> Path` |
| Atomic bytes | `atomic_write_bytes(path: Path, data: bytes) -> None` |
| Atomic text | `atomic_write_text(path: Path, data: str, *, encoding: str = "utf-8") -> None` |
| Lock diagnosis | `diagnose_lock(lock_path: Path, *, stale_after_seconds: float = 300.0, now: datetime | None = None) -> LockDiagnosis` |
| Lock acquisition | `exclusive_lock(lock_path: Path, *, timeout_seconds: float = 5.0, poll_interval_seconds: float = 0.05, stale_after_seconds: float = 300.0) -> AbstractContextManager[LockOwner]` |

Contract details:

- `confine_path()` resolves `root` strictly, accepts relative paths or absolute paths already inside the root, and rejects drive-relative (`C:foo`), foreign-drive, UNC (`\\server\share` and `//server/share`), rooted-without-drive (`\foo`), and resolved `..` escapes. It walks every existing component from the root to the candidate and rejects symbolic links and Windows reparse points/junctions. Use `Path.is_symlink()`, `Path.is_junction()` when available, and Windows `stat.FILE_ATTRIBUTE_REPARSE_POINT` from `os.lstat()` as the Python 3.11 fallback. For `must_exist=False`, validate all existing ancestors and the target if it already exists. `require_file=True` requires a regular, non-link file. Raise `PathLinkError` only when that link/reparse inspection identifies the candidate or an existing ancestor; raise plain `PathConfinementError` for all other confinement failures.
- `atomic_write_bytes()` creates the parent directory, rejects a link/reparse-point destination, writes a unique temporary file in the destination directory, flushes and best-effort `fsync`s it, then commits with one `os.replace()`. On any error it removes only its own temporary file and leaves the prior destination bytes unchanged. `atomic_write_text()` only encodes then delegates. No cross-directory temp file is allowed.
- `exclusive_lock()` creates the lock with mode `"x"`, writes one JSON `LockOwner` record, flushes/best-effort-fsyncs, and yields that owner. Existing locks are never deleted during acquisition, including malformed or stale-suspected locks. Timeout raises `LockAcquisitionError` containing the diagnosis status but no secrets. On release, reread the metadata and unlink only if `owner_token` still matches; otherwise preserve the file and raise `LockAcquisitionError`.
- `diagnose_lock()` is read-only: it never creates, updates, renames, or deletes. A valid owner older than the threshold is `stale_suspected`; recent valid metadata is `held`; absent is `absent`; invalid UTF-8/JSON/schema/timestamp is `malformed`. Age is based on timezone-aware `created_at`, clamped to at least zero. It does not probe/kill a PID and does not claim that a process is dead.
- Lock metadata contains no command line, username, workspace path, package data, PII, key, or secret. `owner_token` is `uuid.uuid4().hex`; `created_at` is UTC ISO-8601; `pid` and hostname are diagnostic only.

---

## Task 1: Extract exact-origin policy and invert the catalog dependency

**Dependencies:** None. Do not run in parallel with Task 3 because both modify `application_execution.py` and its tests.

- [ ] **Step 0: Capture the exact implementation baseline after planning artifacts are committed.**

  ```powershell
  if (git status --porcelain=v1) { throw "M2A requires a clean baseline" }
  Set-Content -LiteralPath .git/career-pipeline-m2a-baseline -Value (git rev-parse HEAD) -NoNewline
  ```

  This local `.git` marker is never staged. Final range checks read it so every implementation and optional fix commit is included without assuming a fixed commit count.

**Files:**

- Create: `career_pipeline/origin_policy.py`
- Create: `tests/test_origin_policy.py`
- Modify: `career_pipeline/platform_catalog.py`
- Modify: `career_pipeline/application_execution.py`
- Modify: `tests/test_platform_catalog.py`
- Modify: `tests/test_application_execution.py`

- [ ] **Step 1: Add the RED origin contract tests.**

  In `tests/test_origin_policy.py`, add these exact tests:

  - `test_normalize_origin_canonicalizes_https_host_idna_ipv6_and_port`
  - `test_normalize_origin_rejects_non_bare_or_unsafe_values`
  - `test_origin_from_url_discards_path_query_and_fragment`
  - `test_origin_policy_has_no_execution_or_site_dependencies`

  Cover at minimum: uppercase/trailing-dot host, explicit/default port, an IDNA hostname, bracketed IPv6, HTTP, credentials, wildcard, control character, invalid port, path/query/fragment rejection in `normalize_origin()`, and path/query/fragment acceptance in `origin_from_url()`. The dependency test must parse `origin_policy.py` with `ast` and assert imports do not include `application_execution`, `platform_catalog`, `site_intake`, `application_package`, or `__main__`.

  In `tests/test_platform_catalog.py`, add `test_platform_catalog_imports_origin_policy_not_execution_policy`, parse imports with `ast`, and assert `career_pipeline.origin_policy` is present while `career_pipeline.application_execution` is absent.

  In `tests/test_application_execution.py`, add `test_normalize_origin_compatibility_wrapper_preserves_public_error_type`; import `normalize_origin`, assert the canonical value remains `https://jobs.example.or.kr:443`, and assert an HTTP URL raises `ApplicationExecutionError` rather than `OriginPolicyError`.

- [ ] **Step 2: Run RED tests and record the expected failures.**

  Run:

  ```powershell
  python -m pytest -q tests/test_origin_policy.py
  ```

  Expected: collection ERROR with `ModuleNotFoundError: No module named 'career_pipeline.origin_policy'`.

  Then run:

  ```powershell
  python -m pytest -q tests/test_platform_catalog.py::test_platform_catalog_imports_origin_policy_not_execution_policy tests/test_application_execution.py::test_normalize_origin_compatibility_wrapper_preserves_public_error_type
  ```

  Expected: the catalog import-boundary test FAILs because it currently imports `.application_execution`; the compatibility test may already pass and is a characterization guard, not evidence to skip the RED module test.

- [ ] **Step 3: Implement `origin_policy.py` exactly to the frozen API.**

  Use one private parser such as `_normalized_origin(value: str, *, require_bare: bool) -> str`; both public functions call it. Catch `ValueError`/`UnicodeError` from `urlsplit`, `hostname`, IDNA conversion, and `parsed.port`, then raise `OriginPolicyError` with value-free messages. Do not echo the input URL because it can contain sensitive query/fragment data.

- [ ] **Step 4: Migrate the catalog and preserve execution compatibility.**

  - In `platform_catalog.py`, replace the execution import with `from .origin_policy import OriginPolicyError, normalize_origin`; translate `OriginPolicyError` to the existing `PlatformCatalogError("invalid public origin")`.
  - In `application_execution.py`, import the two policy functions under private aliases. Keep local public `normalize_origin(value: str) -> str` and private `_origin_from_url(value: str, *, bare: bool) -> str`; both delegate and translate `OriginPolicyError` to `ApplicationExecutionError` with the policy message. Do not change authorization payloads, signatures, HMAC inputs, IDs, or executor behavior.

- [ ] **Step 5: Run GREEN and focused regression tests.**

  ```powershell
  python -m pytest -q tests/test_origin_policy.py tests/test_platform_catalog.py tests/test_application_execution.py
  ```

  Expected: all PASS; existing authorization `allowed_origin` remains explicitly ported and all origin-escape tests still block before `fill_and_verify()`.

- [ ] **Step 6: Stage only Task 1 and commit.**

  ```powershell
  git add -- career_pipeline/origin_policy.py career_pipeline/platform_catalog.py career_pipeline/application_execution.py tests/test_origin_policy.py tests/test_platform_catalog.py tests/test_application_execution.py
  git diff --cached --name-only
  git commit -m "refactor: centralize exact origin policy"
  ```

  The staged list must contain exactly those six files. If another worker modified one of them after Task 1 began, stop and reconcile rather than overwriting or reverting their work.

## Task 2: Add confined paths, atomic writes, and read-only lock diagnosis

**Dependencies:** Task 1 may run independently at first, but complete Task 1 before staging if another worker has touched shared files. Task 2 itself does not modify Task 1 files except through later Task 3.

**Files:**

- Create: `career_pipeline/path_policy.py`
- Create: `tests/test_path_policy.py`
- Modify: `career_pipeline/state.py`

- [ ] **Step 1: Add the RED path/persistence tests.**

  Add these exact tests to `tests/test_path_policy.py`:

  - `test_confine_path_accepts_relative_and_absolute_paths_inside_root`
  - `test_confine_path_rejects_parent_drive_relative_foreign_drive_unc_and_rooted_escapes`
  - `test_confine_path_rejects_symlinks_when_supported`
  - `test_atomic_write_text_preserves_existing_destination_on_replace_failure`
  - `test_atomic_write_text_rejects_link_destination_and_cleans_temporary_files`
  - `test_diagnose_lock_is_read_only_and_marks_old_valid_owner_stale_suspected`
  - `test_diagnose_lock_reports_malformed_without_deleting_it`
  - `test_exclusive_lock_never_reclaims_stale_or_uncertain_lock`
  - `test_exclusive_lock_serializes_concurrent_atomic_json_writers`
  - `test_state_write_json_preserves_format_and_uses_atomic_replace`

  Test mechanics are fixed as follows:

  - Parameterize Windows escape strings with `..\outside.json`, `C:relative.json`, `C:\outside.json`, `\\server\share\outside.json`, `\rooted\outside.json`, and `//server/share/outside.json`. Build the foreign-drive case from a drive different from `tmp_path.drive`; skip only that one assertion if no alternative drive syntax can be represented.
  - For link coverage, create `directory_link.symlink_to(outside_directory, target_is_directory=True)` and `file_link.symlink_to(outside_file)` into/outside `tmp_path`; call `pytest.skip("symlink creation unavailable")` only on `OSError`. Junction/reparse rejection remains an implementation requirement exercised by the same private detector when such a path is encountered, but the test suite must not invoke `cmd`, require Administrator rights, or create machine-global links.
  - For replacement failure, write sentinel bytes, monkeypatch `career_pipeline.path_policy.os.replace` to raise `OSError("simulated replace failure")`, assert sentinel bytes remain, and assert no `.<name>.*.tmp` remains.
  - For stale diagnosis, write a valid `LockOwner` JSON with an old UTC timestamp, snapshot bytes and `stat()` before/after `diagnose_lock`, assert `stale_suspected`, and assert bytes, size, and `st_mtime_ns` are unchanged.
  - For no-reclaim, call `exclusive_lock(lock_path, timeout_seconds=0.02, poll_interval_seconds=0.001, stale_after_seconds=0)` and assert `LockAcquisitionError` plus the original lock bytes still present.
  - For concurrency, use `ThreadPoolExecutor(max_workers=8)` and 32 workers. Each worker acquires the same lock, reads a counter JSON (or starts at zero), writes incremented JSON through `atomic_write_text`, and exits. Assert final count `32`, valid JSON, no lock, and no temp files. Do not use network/process spawning.

- [ ] **Step 2: Run RED and record the expected failure.**

  ```powershell
  python -m pytest -q tests/test_path_policy.py
  ```

  Expected: collection ERROR with `ModuleNotFoundError: No module named 'career_pipeline.path_policy'`.

- [ ] **Step 3: Implement path/link confinement.**

  Implement the frozen `confine_path()` contract and a private `_is_link_or_reparse(path: Path) -> bool`. Validate raw Windows forms with `PureWindowsPath` before joining. Resolve and compare paths using `Path.resolve()`/`relative_to()` on the current platform; reject `OSError` and `ValueError` as plain `PathConfinementError` with no sensitive candidate value. Walk existing lexical components before final resolution so a symlink/junction cannot disappear from inspection after `resolve()`, and raise `PathLinkError` exactly when that helper returns true.

- [ ] **Step 4: Implement atomic text/byte replacement.**

  Create temporary files only with `tempfile.NamedTemporaryFile(delete=False, dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")`. Flush and best-effort `os.fsync`; close before `os.replace` for Windows. In `finally`, unlink only the temporary path created by this invocation. Never unlink or truncate the destination on failure.

- [ ] **Step 5: Implement lock ownership and diagnosis.**

  Serialize `LockOwner` as compact UTF-8 JSON with a trailing newline. Validate schema/version/types and timezone-aware UTC timestamp when reading. Acquisition loops only on `FileExistsError`; other filesystem errors propagate as `LockAcquisitionError`. On timeout call `diagnose_lock()` only to enrich the error category; do not mutate the lock. Release requires the same `owner_token` before unlink.

- [ ] **Step 6: Migrate `state.write_json()` without changing its public contract.**

  Keep JSON serialization in `state.py`, remove its local tempfile/replace implementation, and call `atomic_write_text(path, data)`. Keep parent creation behavior in the atomic helper. Do not change `write_state()` mutation/history behavior.

- [ ] **Step 7: Run GREEN and state regressions.**

  ```powershell
  python -m pytest -q tests/test_path_policy.py tests/test_phase1.py
  ```

  Expected: all PASS, except link/junction cases may report a platform-capability skip; `test_state_write_json_preserves_format_and_uses_atomic_replace` must not skip.

- [ ] **Step 8: Stage only Task 2 and commit.**

  ```powershell
  git add -- career_pipeline/path_policy.py career_pipeline/state.py tests/test_path_policy.py
  git diff --cached --name-only
  git commit -m "feat: add confined atomic persistence policy"
  ```

  The staged list must contain exactly those three files.

## Task 3: Migrate security-sensitive existing persistence callers

**Dependencies:** Tasks 1 and 2 complete. Run serially because the three domain modules share the new lock/write contracts and `application_execution.py` was modified in Task 1.

**Files:**

- Modify: `career_pipeline/application_execution.py`
- Modify: `career_pipeline/application_package.py`
- Modify: `career_pipeline/site_intake.py`
- Modify: `tests/test_application_execution.py`
- Modify: `tests/test_application_package.py`
- Modify: `tests/test_site_intake.py`

- [ ] **Step 1: Add RED migration tests.**

  Add these exact tests:

  - `tests/test_application_execution.py::test_execution_ledger_preserves_stale_lock_and_maps_timeout_error`
  - `tests/test_application_execution.py::test_execution_ledger_concurrent_revocations_remain_valid_json`
  - `tests/test_application_package.py::test_package_paths_reject_windows_drive_relative_and_link_escape`
  - `tests/test_application_package.py::test_application_registry_concurrent_idempotent_writers_leave_valid_registry`
  - `tests/test_site_intake.py::test_intake_registry_preserves_stale_lock_and_maps_timeout_error`
  - `tests/test_site_intake.py::test_intake_registry_concurrent_idempotent_writers_leave_valid_registry`
  - `tests/test_site_intake.py::test_site_intake_exact_origin_matches_shared_origin_policy`

  For timeout tests, retain the real `path_policy.exclusive_lock`, then monkeypatch the symbol imported by each domain module with `lambda path, **_: real_exclusive_lock(path, timeout_seconds=0.02, poll_interval_seconds=0.001, stale_after_seconds=0)`. Precreate valid old lock metadata, assert the existing domain exception/message, and assert the lock remains byte-identical. For concurrent tests use 8 threads and 16 calls against one artifact; execution expects 16 valid revocation events, while package and intake idempotency each expect one entry/record and one creation event. Assert parseable schema-valid JSON and no remaining lock/temp files. For package Windows/link tests use the public `build_application_package()`/`persist_application_package()` paths, not private helpers.

- [ ] **Step 2: Run the seven migration contract tests.**

  ```powershell
  python -m pytest -q tests/test_application_execution.py::test_execution_ledger_preserves_stale_lock_and_maps_timeout_error tests/test_application_execution.py::test_execution_ledger_concurrent_revocations_remain_valid_json tests/test_application_package.py::test_package_paths_reject_windows_drive_relative_and_link_escape tests/test_application_package.py::test_application_registry_concurrent_idempotent_writers_leave_valid_registry tests/test_site_intake.py::test_intake_registry_preserves_stale_lock_and_maps_timeout_error tests/test_site_intake.py::test_intake_registry_concurrent_idempotent_writers_leave_valid_registry tests/test_site_intake.py::test_site_intake_exact_origin_matches_shared_origin_policy
  ```

  Expected before migration: FAIL because current empty lock files have no diagnosable owner metadata/common lock API; at least the stale-lock tests time out through old local loops and the shared-lock monkeypatch target is absent. If a Windows path characterization already rejects one case, retain it as compatibility evidence; the full RED set must still fail on shared-lock/concurrency assertions.

- [ ] **Step 3: Migrate `application_execution.py`.**

  - Keep private `_lock(path)` but implement it as a thin domain adapter over `exclusive_lock(path)`. Translate `LockAcquisitionError` to `ApplicationExecutionError("execution ledger lock timeout: <status>")`; do not expose owner token, hostname, or path.
  - Keep `_write_ledger()` and `write_workflow_artifact()` signatures. They continue through `state.write_json()`, which now provides common atomic replacement.
  - Do not change ledger schema/HMAC, event ordering, authorization claim/revoke/use semantics, or any public execution signature.

- [ ] **Step 4: Migrate `application_package.py`.**

  - Retain private `_inside()` and `_safe_file()` as domain adapters so existing messages remain stable; delegate to `confine_path()` and translate `PathConfinementError` to `ApplicationPackageError(f"{label} must remain inside the workspace")` or the existing regular non-symlink message.
  - Replace `_application_lock()` internals with `exclusive_lock()` while retaining its signature and translating timeout/acquisition errors to `ApplicationPackageError("could not acquire application registry lock")`.
  - Revalidate `package_path`, registry path, private data, attachments, and package file under the registry lock before read/write to narrow TOCTOU. Keep package-first/registry-second ordering and existing rollback of only a newly created package. Do not attempt a multi-file transaction or remove an existing package on registry failure.
  - Continue writing through `write_json()`; do not change package/registry schemas or idempotency rules.

- [ ] **Step 5: Migrate `site_intake.py`.**

  - Keep raw fixture-name checks (`PureWindowsPath`, suffix, `..`) and existing `SiteIntakeError` codes. Delegate the final root confinement/regular-file/link checks to `confine_path(root, candidate, require_file=True)`. Catch `PathLinkError` first and map it to `FIXTURE_LINK_FORBIDDEN`; catch remaining `PathConfinementError` and map it to `FIXTURE_PATH_INVALID`, without echoing the path.
  - Import `origin_from_url` from `origin_policy.py` and use it for the ordinary exact HTTPS origin created by `validate_url_metadata()` after the existing stricter control-character, userinfo, IP-literal, IDNA, and sensitive-query checks. Translate `OriginPolicyError` to the existing value-free `SiteIntakeError` code. Preserve the deliberate `exact_origin=None` overrides for JobKorea JRS and Saramin Direct.
  - Keep private `_lock(path)` as an adapter over `exclusive_lock()` and translate acquisition failures to `SiteIntakeError("registry lock timeout")`.
  - Inside the lock, revalidate the registry destination is not a link/reparse point before load/write. Preserve expected-version and idempotent return behavior exactly.
  - Do not alter URL classification, fixture scanning, schema hashes, readiness codes, `mutation_enabled=False`, or `live_enabled=False`.

- [ ] **Step 6: Run migration GREEN tests.**

  ```powershell
  python -m pytest -q tests/test_application_execution.py tests/test_application_package.py tests/test_site_intake.py tests/test_path_policy.py
  ```

  Expected: all PASS except capability-based symlink/junction skips; concurrent files parse and stale locks remain untouched.

- [ ] **Step 7: Run the original focused M2A regression set.**

  ```powershell
  python -m pytest -q tests/test_platform_catalog.py tests/test_application_execution.py tests/test_application_package.py tests/test_site_intake.py
  ```

  Expected: at least the baseline `114 passed, 1 skipped` plus the newly added tests, with no new failure and no reduced pre-existing test count.

- [ ] **Step 8: Stage only Task 3 and commit.**

  ```powershell
  git add -- career_pipeline/application_execution.py career_pipeline/application_package.py career_pipeline/site_intake.py tests/test_application_execution.py tests/test_application_package.py tests/test_site_intake.py
  git diff --cached --name-only
  git commit -m "refactor: adopt shared safety kernel"
  ```

  The staged list must contain exactly those six files. Never use `git add .`, `git reset`, `git checkout --`, or any command that reverts another worker's changes.

## Task 4 (Final): Full verification, boundary audit, and handoff

**Dependencies:** Tasks 1-3 complete. This task is read-only except for an optional fix commit limited to the files in the locked file map.

**Files:** None unless a directly related failure requires a scoped fix.

- [ ] **Step 1: Run the complete focused safety suite.**

  ```powershell
  python -m pytest -q tests/test_origin_policy.py tests/test_path_policy.py tests/test_platform_catalog.py tests/test_application_execution.py tests/test_application_package.py tests/test_site_intake.py
  ```

  Expected: all PASS, with skips only for unavailable symlink/junction capability.

- [ ] **Step 2: Run full repository verification.**

  ```powershell
  python -m pytest -q
  python -m compileall -q career_pipeline
  git diff --check
  ```

  Expected: pytest exceeds the `425 passed, 2 skipped` baseline by the number of new non-skipped tests, with zero failures; compileall and diff check exit `0` with no output.

- [ ] **Step 3: Verify dependency direction and no-live/no-network boundaries.**

  ```powershell
  rg -n "application_execution" career_pipeline/origin_policy.py career_pipeline/path_policy.py career_pipeline/platform_catalog.py
  rg -n "urllib\.request|requests|httpx|socket\.|playwright|selenium|submit\(|click\(|upload" career_pipeline/origin_policy.py career_pipeline/path_policy.py tests/test_origin_policy.py tests/test_path_policy.py
  ```

  Expected: both commands return no matches. A nonzero `rg` exit code caused only by zero matches is success. The existing `execute_application()` submit code is outside these scan paths and must remain behaviorally unchanged.

- [ ] **Step 4: Audit lock and atomic-write invariants.**

  ```powershell
  rg -n "unlink|missing_ok|os\.replace|NamedTemporaryFile|open\(\"x\"|exclusive_lock|diagnose_lock" career_pipeline/path_policy.py career_pipeline/state.py career_pipeline/application_execution.py career_pipeline/application_package.py career_pipeline/site_intake.py
  ```

  Manually confirm from the matched lines:

  - no stale/malformed lock branch unlinks a lock;
  - only token-matching owner release unlinks a lock;
  - atomic failure cleanup targets only the invocation's temp file;
  - all migrated registry/ledger writes flow through `state.write_json()`;
  - no domain schema, public signature, or live flag changed.

- [ ] **Step 5: Verify commit/stage scope and preserve other workers' files.**

  ```powershell
  git status --short
  $m2aBaseline = Get-Content -LiteralPath .git/career-pipeline-m2a-baseline -Raw
  git diff --name-only "$m2aBaseline..HEAD"
  git diff --cached --name-only
  git diff --check "$m2aBaseline..HEAD"
  ```

  Expected implementation commit range contains only the 13 paths in the locked file map, excluding this plan file if it was committed separately by the planner. The staged area is empty. Unrelated modified/untracked files may remain and must not be altered, staged, or reported as M2A output.

- [ ] **Step 6: If a final scoped fix was necessary, commit it separately.**

  Stage only affected paths from the locked file map, verify `git diff --cached --name-only`, then:

  ```powershell
  git commit -m "fix: close shared safety kernel edge cases"
  ```

  Do not amend another worker's commit and do not force-push.

- [ ] **Step 7: Remove only the local baseline marker after every verification passes.**

  ```powershell
  Remove-Item -LiteralPath .git/career-pipeline-m2a-baseline
  ```

## Self-review checklist

- [ ] Every M2A success criterion maps to a task: dependency-safe origin policy (Task 1), common confinement/atomic APIs (Task 2), registry/authorization migration (Task 3), Windows/link/write/stale/concurrency negatives (Tasks 2-3), and read-only no-delete diagnosis (Task 2).
- [ ] Public APIs and existing domain exception types remain compatible; no artifact schema/HMAC/ID semantics change.
- [ ] Windows drive-relative, UNC, rooted, foreign-drive, symlink/reparse, OneDrive same-directory replace, and TOCTOU revalidation boundaries are explicit.
- [ ] Every RED test has an exact node name, command, and expected failure; every task has GREEN commands.
- [ ] The final task contains full pytest, compileall, diff, dependency, security, lock, and staged-file checks.
- [ ] Tasks that share files are serial; M2B/M3/M4/M5 files and `__main__.py` are excluded to prevent worker conflict.
- [ ] No placeholder, automatic stale-lock deletion, network/live behavior, new dependency, blanket stage, reset, or unrelated refactor is present.

## Abort conditions

Stop the migration and report the exact failing compatibility test without widening scope if any of the following occurs:

- a public CLI path or existing artifact reader would need a signature/schema change;
- Windows confinement cannot distinguish a legitimate inside-root absolute path from a drive-relative/UNC escape;
- an atomic replacement failure can corrupt or remove the prior destination;
- stale or malformed lock handling requires automatic deletion to make tests pass;
- concurrent writer tests produce invalid JSON, lost updates, or ownership-token mismatch;
- implementation would require network/live access, browser mutation, credentials, real PII, or a new production dependency;
- another worker has overlapping unstaged changes in a locked M2A file that cannot be reconciled without overwriting their work.
