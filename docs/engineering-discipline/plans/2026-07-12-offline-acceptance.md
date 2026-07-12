# M4 Deterministic Offline Acceptance Execution Plan

## Scope and truthful outcome

M4 proves an offline synthetic integration boundary only:

```text
structured PostingRecord -> confirmed profile -> eligible decision
-> verified final-artifact fixture input -> ApplicationPackage
-> SiteReadOnlyContract -> ReviewDecisionV2
-> disabled AuthorizationCandidateV2 -> ProjectReadinessReport
```

It does not call `finalize_run`, does not prove a full synthesis pipeline, and does not fill, upload, click, submit, collect a receipt, or create `ExecutionAuthorizationV2` for the production intake contract. The successful M4 result is exactly:

- `local_status="awaiting_external_live_enablement"`
- candidate `candidate_status="capability_disabled"`, `reason_code="FILL_AUTHORITY_DISABLED"`
- `live_status="disabled"`
- `submission_status="not_attempted"`

Network, browser/page, credential, real PII, live adapter, upload, click, submit, receipt collection, `__main__.py`, CLI parser, and CLI options are out of scope.

## Locked implementation scope

Only these files may change during M4 implementation:

- `career_pipeline/offline_acceptance.py` (new)
- `career_pipeline/application_execution.py`
- `career_pipeline/site_intake.py`
- `tests/test_offline_acceptance.py` (new)
- `tests/test_application_execution.py`
- `tests/test_site_intake.py`

This planning turn changes only this plan file. No staging, commit, push, PR, reset, or baseline-marker action is authorized.

## Explicit inputs and deterministic public API

```python
@dataclass(frozen=True)
class AcceptanceInputs:
    posting_retrieved_at: str
    profile_generated_at: str
    eligibility_evaluated_at: str
    final_artifact_generated_at: str
    package_created_at: str
    site_observed_at: str
    site_valid_until: str
    review_decided_at: str
    candidate_requested_at: str
    report_generated_at: str
    signing_key: bytes
    key_id: str

@dataclass(frozen=True)
class OfflineCallCounters:
    network: int
    browser: int
    credential: int
    pii: int
    upload: int
    click: int
    submit: int

@dataclass(frozen=True)
class OfflineAcceptanceResult:
    schema_version: Literal["career-pipeline-offline-acceptance-v1"]
    run_id: str
    posting_id: str
    profile_id: str
    eligibility_decision_id: str
    final_manifest_sha256: str
    package_id: str
    package_sha256: str
    site_contract_id: str
    site_contract_sha256: str
    review_id: str
    authorization_candidate: AuthorizationCandidateV2
    local_status: Literal["awaiting_external_live_enablement"]
    live_status: Literal["disabled"]
    submission_status: Literal["not_attempted"]
    readiness_report: ProjectReadinessReport
    readiness_sha256: str
    counters: OfflineCallCounters

def run_offline_acceptance(*, workspace: Path, inputs: AcceptanceInputs) -> OfflineAcceptanceResult: ...
def offline_acceptance_to_dict(result: OfflineAcceptanceResult) -> dict[str, Any]: ...
```

Every public timestamp comes from `AcceptanceInputs` and must be timezone-aware. `site_valid_until > site_observed_at` is required. The runner, its fixture writer, and every acceptance artifact must not read `datetime.now`, `time.time`, environment variables, or monkeypatched clock state.

The determinism test uses identical `AcceptanceInputs`, signing key, and `key_id` in two different output roots. The public canonical projection and result SHA must be byte-identical. Absolute paths and raw timestamps are not public result fields.

Never serialize the signing key, derived key fingerprint, private fields, HTML fixture body, applicant name/email/phone, or sensitive URL value.

## Posting, profile, eligibility, and final-artifact boundary

Do not use `posting.txt`, `load_posting_source`, or the posting parser for the eligible M4 positive path. The current local loader accepts only PDF/DOCX and reads its retrieved timestamp from an internal clock. Parser output that contains a `manual_review` rule must remain manual-review; it cannot support an eligible claim.

Create a structured `PostingRecord` and `EligibilityRule` directly, then call `validate_posting_record` and `evaluate_eligibility`.

- `source_status="verified_domain"`, `status="active"`, explicit `retrieved_at`, fixed lower-case `body_sha256`.
- At least one required `parse_status="parsed"` education or experience rule is satisfied by the confirmed synthetic profile.
- No manual-review required rule, no empty required-rule set, no unsatisfied preferred rule.
- `evaluate_eligibility(..., evaluated_at=inputs.eligibility_evaluated_at)` must return `eligible` with `human_review_required=False`.

Create an `ExperienceLedger` containing confirmed synthetic experience only, use `applicant_profile_from_ledger(..., generated_at=inputs.profile_generated_at)`, validate it, and calculate the profile SHA from canonical ledger bytes.

M4 starts after finalization at a **verified final-artifact fixture input boundary**. It must not call `finalize_run`: current v2 finalize requires `00_채용공고분석.json`, `02_확정경험원장.json`, `03_경험직무매칭.json`, research/document/draft state and state-writing behavior. The M4 test helper `_write_verified_final_artifact_fixture(workspace, inputs)` creates only the existing `build_application_package` input shape: completed `run.json`, question state, canonical final answer JSON, final manifest, and matching SHA bindings. It reuses the existing `tests/test_application_package.py` shape without promoting a test helper to production. Evidence calls this `final_artifact_fixture_verified`, never “full pipeline complete”.

`build_application_package(..., created_at=inputs.package_created_at)` must produce `validation_status="ready_for_review"`.

## Adapter schema lineage producer

M4 separates the canonical page/site schema from the observed form-adapter schema without importing adapters inside `site_intake` and without a dependency cycle.

Add one optional input at the end of `build_site_intake`:

```python
def build_site_intake(
    *, ..., valid_until: str | None = None,
    adapter_schema_sha256: str | None = None,
) -> SiteIntakeResult: ...
```

- If supplied, `adapter_schema_sha256` must be a lower-case SHA-256 and is copied exactly to `SiteReadOnlyContract.adapter_schema_sha256`.
- If omitted, append `ADAPTER_SCHEMA_LINEAGE_UNVERIFIED`, require manual review, and return no contract. This fail-closed behavior applies to existing callers without changing CLI parser or `__main__.py`.
- `schema_sha256` remains the canonical page/site schema digest from parsed de-identified HTML. It is not required to equal the adapter digest.
- M4 computes the actual observed form digest using the existing read-only `FixtureFormDriver` plus `ReviewRequiredFormAdapter.probe_contract()`/`form_schema_sha256`, passes that digest explicitly to `build_site_intake`, then verifies it is recorded in the contract.

Add to `tests/test_site_intake.py`:

1. `test_m4_site_intake_records_explicit_adapter_schema_lineage`
2. `test_m4_site_intake_without_adapter_schema_lineage_fails_closed`

The first uses valid but intentionally distinct canonical page and observed adapter SHA values. The second asserts the exact validation code, manual review, and `contract is None`. Existing safe-contract callers in that test file are updated to supply an explicit digest.

## Application-execution schema correction

Current approval compares `dry_run_result.form_schema_sha256` with `site_contract.schema_sha256`. M4 changes the form binding only:

1. `approve_application_v2` approved path requires `dry_run_result.form_schema_sha256 == site_contract.adapter_schema_sha256`.
2. `_v2_bindings`, `ReviewDecisionV2.form_schema_sha256`, and `ExecutionAuthorizationV2.form_schema_sha256` bind the form digest to `adapter_schema_sha256`.
3. Canonical `site_contract.schema_sha256` remains part of the site contract digest and review/site binding separately.
4. Package binding, origin, adapter ID/version, key ID, HMAC, capabilities, and disabled issuance behavior remain unchanged.

Add to `tests/test_application_execution.py`:

1. `test_m4_approval_binds_dry_result_to_adapter_schema_not_site_schema`
2. `test_m4_approval_rejects_dry_result_that_misses_adapter_schema`

The success fixture has distinct valid page and adapter SHA values and asserts both are retained in their distinct lineage fields. The negative case changes only the dry-result adapter digest and fails before any driver or mutation call.

## Acceptance flow and readiness

1. Write de-identified safe HTML under `tmp_path`; do not use repository fixture HTML.
2. Compute the read-only observed form digest, pass it explicitly to `build_site_intake`, and assert v2 `allowed_capabilities == ()`, `mutation_enabled is False`, `live_enabled is False`.
3. Build the structured eligible posting/profile/decision, final-artifact fixture, and `ApplicationPackage`.
4. Call `approve_application_v2` with the actual adapter digest.
5. Call `build_authorization_candidate_v2(..., mode="fill_only")`, assert disabled candidate, then call `authorize_execution_v2` only to capture `FILL_AUTHORITY_DISABLED`; do not retain an authorization artifact.
6. Build and validate the readiness report:

| axis | required status |
| --- | --- |
| `local_foundation` | `complete` |
| `offline_acceptance` | `passed` |
| `external_inputs` | `blocked` |
| `live_execution` | `disabled` |
| `submission` | `not_attempted` |

Local/offline requirements are `IMPLEMENTED` with CODE and TEST evidence. External/live/submission requirements are `EXTERNAL_ONLY` with matching blocker records: `ORIGIN_UNCONFIRMED`, `DOM_UNVERIFIED`, `AUTOMATION_POLICY_UNCONFIRMED`, `CREDENTIALS_UNAVAILABLE`, `PII_TRANSMISSION_UNAUTHORIZED`, `UPLOAD_NOT_AUTHORIZED`, `CLICK_NOT_AUTHORIZED`, `SUBMIT_NOT_AUTHORIZED`, and `RECEIPT_UNVERIFIED`.

## Negative matrix and call counters

Every case asserts:

```text
(network, browser, credential, pii, upload, click, submit) == (0, 0, 0, 0, 0, 0, 0)
```

| case | exact boundary |
| --- | --- |
| sensitive fixture | password/token sentinel -> `blocked_sensitive_fixture`, no contract, sentinel absent from result |
| stale digest | modified package/final/site digest -> binding failure before issuance |
| revoked | enabled signed M3 test fixture + revoke -> static gate, probe 0/mutation 0 |
| expired | enabled signed fixture + explicit expired time -> static gate, probe 0/mutation 0 |
| reused | enabled signed fixture + signed ledger `used_at` -> static gate, probe 0/mutation 0 |
| origin mismatch | enabled signed fixture + read-only mismatched origin -> `probe_calls == ["current_origin"]`, mutation 0 |
| unknown structure | unknown MFA/CAPTCHA/iframe/popup -> manual review, no contract, no driver |

Enabled signed fixtures exist only in tests for M3 validation-kernel characterization; `run_offline_acceptance` never returns one and never implies live authority.

## Exact test count and RED/GREEN sequence

M4 adds exactly 15 nodes:

- 11 nodes in `tests/test_offline_acceptance.py`
- 2 nodes in `tests/test_application_execution.py`
- 2 nodes in `tests/test_site_intake.py`

The 11 offline nodes are:

1. `test_offline_acceptance_reaches_external_live_disabled_boundary`
2. `test_offline_acceptance_uses_structured_eligible_posting_and_synthetic_temp_workspace`
3. `test_offline_acceptance_builds_valid_readiness_report_and_disabled_candidate`
4. `test_offline_acceptance_is_deterministic_for_identical_inputs_across_roots`
5. `test_offline_acceptance_sensitive_fixture_fails_closed`
6. `test_offline_acceptance_stale_digest_fails_before_issuance`
7. `test_offline_acceptance_static_kernel_negative[revoked]`
8. `test_offline_acceptance_static_kernel_negative[expired]`
9. `test_offline_acceptance_static_kernel_negative[reused]`
10. `test_offline_acceptance_origin_mismatch_is_probe_only`
11. `test_offline_acceptance_unknown_structure_blocks_contract`

The static-negative function is parameterized into exactly three nodes and uses its parameter value to mutate real fixture/ledger setup.

RED is skeleton-first:

1. Create `offline_acceptance.py` with the declared dataclasses/signatures and `run_offline_acceptance`/serializer bodies raising `NotImplementedError`. Add 11 offline tests, 2 application-execution tests, and 2 site-intake tests.
2. Collect exactly 15 M4 nodes successfully.
3. RED expected result is **`5 passed, 10 failed`**, not “15 failed”: six runner-dependent offline nodes fail with `NotImplementedError`; the two application-execution and two site-intake corrective tests fail pre-fix. Existing M3 static negative (3), origin-mismatch (1), and unknown-structure (1) characterization nodes pass before M4 implementation. Import errors, missing nodes, skips, and xfails are invalid.
4. Implement the producer and approval corrections, then runner/readiness logic. GREEN is **`15 passed`**.

The following focused baseline was measured on the current tree, not inferred:

```powershell
python -m pytest --collect-only -q tests/test_application_execution.py tests/test_site_intake.py tests/test_form_adapter.py tests/test_jobkorea_jrs_adapter.py tests/test_saramin_applyin_adapter.py tests/test_application_package.py tests/test_readiness.py
# 202 tests collected
```

Commands and expected counts:

```powershell
python -m pytest --collect-only -q tests/test_offline_acceptance.py tests/test_application_execution.py tests/test_site_intake.py -k "offline_acceptance or m4_approval or m4_site_intake"
# 15 tests collected
python -m pytest -q tests/test_offline_acceptance.py tests/test_application_execution.py tests/test_site_intake.py -k "offline_acceptance or m4_approval or m4_site_intake"
# RED: 5 passed, 10 failed; GREEN: 15 passed
python -m pytest -q tests/test_application_execution.py tests/test_site_intake.py tests/test_form_adapter.py tests/test_jobkorea_jrs_adapter.py tests/test_saramin_applyin_adapter.py tests/test_application_package.py tests/test_readiness.py tests/test_offline_acceptance.py
# GREEN: 217 passed, 2 skipped
python -m pytest -q
# GREEN: 528 passed, 5 skipped
python -m compileall -q career_pipeline
git diff --check
```

## Static gates and commits

```powershell
git diff --name-only
git diff --check
git diff --unified=0 -- career_pipeline tests | Select-String -Pattern '^\+.*(requests|httpx|urllib\.request|socket|selenium|playwright|page\.goto|page\.click|page\.press|set_input_files|upload|submit)'
rg -n "datetime\.now|time\.time|os\.environ|dotenv|keyring" career_pipeline/offline_acceptance.py tests/test_offline_acceptance.py
```

Expected: only the six locked implementation/test files change; no forbidden live API additions; no runner clock/environment read. Sensitive literals may occur only in negative-test construction and must be absent from serialized public output.

After GREEN only, commit in two narrow steps:

1. `test(acceptance): specify offline acceptance schema lineage`
2. `feat(acceptance): add deterministic offline acceptance boundary`

Before each commit use `git diff --cached --name-only`. Never use `git add .`, amend, reset/checkout, force push, PR, merge, or marker deletion. Stop if any work needs a live URL fetch, browser/page, credential, real PII, upload, click, submit, `__main__.py` change, or mutation authority under a read-only contract.
