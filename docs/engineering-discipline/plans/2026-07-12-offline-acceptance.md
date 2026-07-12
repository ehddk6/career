# M4 Deterministic Offline Acceptance 실행 계획

## 목표와 정직한 완료 정의

M4는 synthetic `tmp_path` workspace에서 **structured posting → confirmed profile → eligibility → 이미 검증된 final-artifact 입력 → package → site intake → v2 review → disabled authorization candidate → readiness report**를 연결한다. `finalize_run` 전체 합성 파이프라인이나 실제 지원·fill·submit 성공을 증명하는 milestone이 아니다.

정상 결과는 다음 상태여야 한다.

- local acceptance: `awaiting_external_live_enablement`
- candidate: `AuthorizationCandidateV2(candidate_status="capability_disabled", reason_code="FILL_AUTHORITY_DISABLED")`
- live execution: `disabled`
- submission: `not_attempted`

현재 `SiteReadOnlyContract`는 `allowed_capabilities=()`, `mutation_enabled=False`, `live_enabled=False`이므로 `authorize_execution_v2(..., mode="fill_only")`는 evidence용으로 `FILL_AUTHORITY_DISABLED`를 반환해야 한다. M4는 authorization artifact, fill receipt, mutation call을 만들지 않는다.

실제 network, browser/page, credential, real PII, upload, click, submit, receipt collection, live adapter, CLI parser/`__main__.py` 변경은 금지한다.

## M4 구현 소유 파일

구현 단계의 locked scope는 다음 네 파일이다.

- `career_pipeline/offline_acceptance.py` (신규)
- `career_pipeline/application_execution.py` (M4 schema-lineage corrective change만)
- `tests/test_offline_acceptance.py` (신규)
- `tests/test_application_execution.py` (M4 schema-lineage corrective tests만)

계획 작성 단계에서는 `docs/engineering-discipline/plans/2026-07-12-offline-acceptance.md`만 수정한다. `__main__.py`, `site_intake.py`, posting parser/loader, finalize/orchestrator, adapters, readiness schema, fixture HTML, dependency 설정은 수정하지 않는다.

## 입력 계약과 결정성

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

def run_offline_acceptance(
    *, workspace: Path, inputs: AcceptanceInputs,
) -> OfflineAcceptanceResult: ...

def offline_acceptance_to_dict(result: OfflineAcceptanceResult) -> dict[str, Any]: ...
```

모든 public timestamp는 `AcceptanceInputs`의 timezone-aware ISO-8601 값만 사용한다. runner, synthetic artifact writer, posting/profile/package/site/review/readiness 생성 중 `datetime.now`, `time.time`, 환경변수, monkeypatch clock은 사용하지 않는다. `site_valid_until > site_observed_at`을 검증한다.

결정성 test는 **동일한 `AcceptanceInputs`와 signing key/key_id**를 두 output root에 주입한다. output path만 다르다. 두 결과에서 canonical projection 및 SHA가 byte-identical이어야 한다. path-dependent field, raw timestamps, workspace absolute path는 public result에 넣지 않는다. 별도 validation test가 각 timestamp를 바꾸면 해당 time-bearing artifact만 변하고, stable lineage ID/digest가 내부 clock에 의존하지 않음을 확인한다.

`OfflineAcceptanceResult`와 dict에는 signing key/key fingerprint, raw private fields, HTML, applicant name/email/phone, sensitive query value를 저장하거나 반환하지 않는다.

## 정확한 data 경로

### Posting/profile/eligibility

`posting.txt`와 `load_posting_source`를 사용하지 않는다. 현재 local loader는 PDF/DOCX만 허용하고 retrieved time도 내부 clock을 사용한다. Parser 결과가 `manual_review` rule을 만들 수 있으므로 M4 eligible positive path의 근거로 사용하지 않는다.

positive acceptance는 `career_pipeline.models.PostingRecord`과 `EligibilityRule`을 직접, 구조적으로 생성하고 `validate_posting_record`를 통과시킨다.

- `PostingRecord.source_status="verified_domain"`, `status="active"`, explicit `retrieved_at`, active deadline, fixed `body_sha256`를 사용한다.
- `required_rules`에는 profile이 만족하는 parse_status=`"parsed"` education 또는 experience rule 하나 이상만 넣는다. `preferred_rules=()`이며 manual-review rule과 자연어 fallback을 넣지 않는다.
- `ExperienceLedger`에는 confirmed synthetic experience만 만들고 `applicant_profile_from_ledger(..., generated_at=inputs.profile_generated_at)`와 `validate_applicant_profile`을 사용한다.
- `evaluate_eligibility(..., evaluated_at=inputs.eligibility_evaluated_at)`의 결과는 정확히 `eligible`, `human_review_required=False`여야 한다.

parser/loader 자체의 offline behavior는 M4 acceptance에 포함하지 않는다. 이후 parser integration milestone은 parser output이 `manual_review`이면 acceptance가 `manual_review_expected`로 멈추는 별도 목표로 다룬다.

### Final artifact/package

M4는 `finalize_run`을 호출하지 않는다. 현재 v2 finalize는 `00_채용공고분석.json`, `02_확정경험원장.json`, `03_경험직무매칭.json`, research/document/draft/run state 등 다수의 기존 synthesis artifact를 요구하고 내부 state write 흐름을 가진다. M4가 이 구조를 일부만 흉내 내고 full pipeline 성공이라고 주장해서는 안 된다.

대신 M4 test helper `_write_verified_final_artifact_fixture(workspace, inputs)`가 `build_application_package`가 실제로 검증하는 최소 **verified final-artifact input boundary**를 만든다.

- explicit `run.json`의 `status="complete"`, `questions`, `final_artifact` shape
- canonical `draft_final.json` answers
- final manifest file과 manifest SHA
- `ApplicationPackage` loader가 읽는 answer/final artifact SHA binding

helper는 existing `tests/test_application_package.py`의 artifact shape를 그대로 재사용·축소하되, production helper로 승격하지 않는다. M4 결과와 evidence에는 `final_artifact_fixture_verified`를 기록하고 `finalize_run` 또는 “full pipeline completed”라는 표현을 쓰지 않는다.

`build_application_package(..., created_at=inputs.package_created_at)`는 실제 package validation을 수행해야 하며 `validation_status="ready_for_review"`를 요구한다.

## M4 schema-lineage corrective change

현재 `approve_application_v2`는 `dry_run_result.form_schema_sha256 == site_contract.schema_sha256`을 요구한다. 이는 read-only intake의 canonical page schema SHA와 adapter form schema SHA를 같은 것으로 취급해 form adapter가 실제로 같은 schema를 관측했다고 거짓 주장하게 만든다.

M4는 다음 좁은 production correction을 `application_execution.py`에 적용한다.

1. `approve_application_v2` approved branch는 `dry_run_result.form_schema_sha256 == site_contract.adapter_schema_sha256`를 검증한다.
2. `_v2_bindings`, `ReviewDecisionV2.form_schema_sha256`, `ExecutionAuthorizationV2.form_schema_sha256`의 form binding은 `site_contract.adapter_schema_sha256`을 사용한다.
3. `site_contract.schema_sha256`은 `canonical_site_contract_sha256` 안에 남는 canonical page/site contract lineage이며, form-adapter schema를 대체하지 않는다.
4. package/review/site-contract digest, exact origin, adapter ID/version, allowed capabilities, disabled issuance 규칙은 변경하지 않는다.

`tests/test_application_execution.py`에 아래 두 M4 node를 추가한다.

- `test_m4_approval_binds_dry_result_to_adapter_schema_not_site_schema`
- `test_m4_approval_rejects_dry_result_that_misses_adapter_schema`

첫 test는 서로 다른 valid SHA-256인 `schema_sha256`와 `adapter_schema_sha256`를 가진 signed fixture를 사용해 approve 성공·각 lineage field 보존을 확인한다. 둘째 test는 adapter SHA만 불일치시켜 fail-closed를 확인한다. 두 test 모두 driver/mutation call은 0이다.

## Site intake, review, candidate, readiness 흐름

1. `tmp_path/intake/safe.html`에 test가 직접 작성한 de-identified single-page HTML을 둔다. static fixture와 actual URL은 사용하지 않는다.
2. `build_site_intake(..., created_at=inputs.site_observed_at, valid_until=inputs.site_valid_until, known_structure={login/mfa/captcha/iframe/popup/redirect:"none", attachment:"unsupported"})`를 호출한다.
3. resulting v2 contract의 `allowed_capabilities == ()`, `mutation_enabled is False`, `live_enabled is False` 및 `canonical_site_contract_sha256`를 확인한다.
4. read-only fixture driver는 discovery/schema observation만 제공한다. mutation method가 없고 all call counters가 0이다. M4 corrective lineage rule에 맞춰 dry result form SHA는 `contract.adapter_schema_sha256`이다.
5. `approve_application_v2`로 approved `ReviewDecisionV2`를 만든다.
6. `build_authorization_candidate_v2(..., mode="fill_only")`로 disabled candidate를 만든다. 이어 `authorize_execution_v2`가 `FILL_AUTHORITY_DISABLED`로 실패함을 evidence에만 기록한다. returned result에는 `ExecutionAuthorizationV2`를 넣지 않는다.
7. `build_readiness_report`와 `validate_readiness_report`로 다음 다섯 축을 만든다.

| axis | status | 근거 |
| --- | --- | --- |
| `local_foundation` | `complete` | structured posting/profile/eligibility/final-artifact input/package/site/review code+test evidence |
| `offline_acceptance` | `passed` | M4 runner/test/artifact evidence |
| `external_inputs` | `blocked` | `ORIGIN_UNCONFIRMED`, `DOM_UNVERIFIED`, `AUTOMATION_POLICY_UNCONFIRMED`, `CREDENTIALS_UNAVAILABLE`, `PII_TRANSMISSION_UNAUTHORIZED` |
| `live_execution` | `disabled` | `UPLOAD_NOT_AUTHORIZED`, `CLICK_NOT_AUTHORIZED`, `SUBMIT_NOT_AUTHORIZED` |
| `submission` | `not_attempted` | `RECEIPT_UNVERIFIED` |

모든 external/live/submission item은 `EXTERNAL_ONLY` requirement와 일치하는 blocker record를 가져야 한다. local/offline item은 `IMPLEMENTED`이며 CODE와 TEST evidence를 모두 가져야 한다.

## Negative matrix와 zero-side-effect assertions

각 test는 synthetic workspace만 사용하고 아래 counter tuple을 정확히 확인한다.

```text
(network, browser, credential, pii, upload, click, submit) == (0, 0, 0, 0, 0, 0, 0)
```

| case | setup | expected boundary |
| --- | --- | --- |
| sensitive fixture | password/token sentinel HTML | `blocked_sensitive_fixture`, no contract, sentinel redacted |
| stale digest | package/final/site digest change | review/candidate binding failure before issuance |
| revoked | M3 enabled signed fixture ledger revoke | validation static gate; probe 0/mutation 0 |
| expired | enabled signed fixture explicit expired clock | static gate; probe 0/mutation 0 |
| reused | enabled signed fixture signed ledger `used_at` | static gate; probe 0/mutation 0 |
| origin mismatch | enabled signed fixture read-only probe returns other origin | `probe_calls == ["current_origin"]`, mutation 0 |
| unknown structure | synthetic known_structure MFA/CAPTCHA/iframe/popup unknown | manual review, no contract, no driver |

enabled signed fixtures exist only inside tests for M3 validation-kernel regression. They are not output by `run_offline_acceptance` and never imply live authority.

## Tests, RED/GREEN, exact counts

M4 adds exactly 15 nodes: 13 in `tests/test_offline_acceptance.py` and the two schema-lineage nodes in `tests/test_application_execution.py` named above.

`tests/test_offline_acceptance.py` exact 13 nodes:

1. `test_offline_acceptance_reaches_external_live_disabled_boundary` — zero counters도 함께 검증
2. `test_offline_acceptance_uses_structured_eligible_posting_and_synthetic_temp_workspace`
3. `test_offline_acceptance_result_has_exact_schema_and_redacts_private_values`
4. `test_offline_acceptance_builds_valid_readiness_report`
5. `test_offline_acceptance_is_deterministic_for_identical_inputs_across_roots`
6. `test_offline_acceptance_candidate_records_disabled_issuance_evidence`
7. `test_offline_acceptance_sensitive_fixture_fails_closed`
8. `test_offline_acceptance_stale_digest_fails_before_issuance`
9. `test_offline_acceptance_static_kernel_negative[revoked]`
10. `test_offline_acceptance_static_kernel_negative[expired]`
11. `test_offline_acceptance_static_kernel_negative[reused]`
12. `test_offline_acceptance_origin_mismatch_is_probe_only`
13. `test_offline_acceptance_unknown_structure_blocks_contract`

The static negative function is parameterized into exactly three nodes; each parameter value must mutate actual fixture/ledger setup, not just a test label.

RED sequence is intentionally skeleton-first to avoid import-collection ambiguity.

1. Add `offline_acceptance.py` with the declared dataclasses, exact public function signatures, and bodies raising `NotImplementedError`. Add the two `application_execution` lineage tests and 13 offline tests.
2. `--collect-only` must collect 15 nodes successfully.
3. Run the 15 nodes: expected **15 failed**—13 `NotImplementedError` failures and 2 schema-lineage assertion failures. Import errors, missing nodes, skips, or xfails are invalid RED.
4. Implement the schema-lineage correction, deterministic runner, fixture writer, negative matrix and readiness construction. Re-run: expected **15 passed**.

```powershell
python -m pytest --collect-only -q tests/test_offline_acceptance.py tests/test_application_execution.py -k "offline_acceptance or m4_approval"
python -m pytest -q tests/test_offline_acceptance.py tests/test_application_execution.py -k "offline_acceptance or m4_approval"
python -m pytest -q tests/test_application_execution.py tests/test_site_intake.py tests/test_form_adapter.py tests/test_jobkorea_jrs_adapter.py tests/test_saramin_applyin_adapter.py tests/test_application_package.py tests/test_readiness.py
python -m pytest -q
python -m compileall -q career_pipeline
git diff --check
```

Current checkpoint baseline is `513 passed, 5 skipped`. M4 adds exactly 15 nodes, so GREEN full-suite expectation is **`528 passed, 5 skipped`**. The listed focused regression baseline is `197 passed, 2 skipped`; it gains the 15 M4 nodes when run with the M4 test file, so expected combined focused result is **`212 passed, 2 skipped`**.

## Static gates and commits

```powershell
git diff --name-only
git diff --check
git diff --unified=0 -- career_pipeline tests | Select-String -Pattern '^\+.*(requests|httpx|urllib\.request|socket|selenium|playwright|page\.goto|page\.click|page\.press|set_input_files|upload|submit)'
rg -n "datetime\.now|time\.time|os\.environ|dotenv|keyring" career_pipeline/offline_acceptance.py tests/test_offline_acceptance.py
```

Expected: only the four locked implementation/test files change; no forbidden live API additions; runner has no internal clock or environment read. Sensitive literal scans may occur only in negative-test sentinel construction and must be asserted absent from public result/serialized output.

Commit sequence after GREEN only:

1. `test(acceptance): specify deterministic offline acceptance and schema lineage`
2. `feat(acceptance): add deterministic offline acceptance boundary`

Before each commit use `git diff --cached --name-only`. Never use `git add .`, amend, reset/checkout, force push, PR, merge, baseline-marker deletion, or changes outside the four M4 implementation files. This planning task stages and commits nothing.

Stop if an implementation step needs a live URL fetch, browser/page, secret/credential, real PII, attachment upload, click, submit, `__main__.py` change, or mutation authority under the current read-only site contract.
