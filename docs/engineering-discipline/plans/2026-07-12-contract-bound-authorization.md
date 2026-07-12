# M3 Contract-Bound Authorization 실행 계획

## 실행 결정

M3는 authorization v2의 발급·검증 kernel까지만 구현한다. 실제 driver mutation을 실행하는 v2 경로는 만들지 않는다.

- 현재 `SiteReadOnlyContract`는 항상 `mutation_enabled=false`, `live_enabled=false`, `allowed_capabilities=()`이다.
- 따라서 `authorize_execution_v2(..., mode="fill_only")`와 `mode="submit"`은 모두 fail-closed 한다.
- M3 positive path는 `ReviewDecisionV2`, `AuthorizationCandidateV2`, legacy classification, canonical digest/HMAC payload 생성까지만 검증한다.
- `ExecutionAuthorizationV2` 검증은 테스트가 명시적으로 만든 합성 signed fixture에만 사용한다. production site-intake는 enabled contract를 만들 수 없다.
- `validate_execution_candidate_v2`는 static gate와 read-only probe gate까지만 수행하고 `ValidatedExecutionCandidateV2`를 반환한다. `fill_and_verify`, `submit`을 호출하지 않는다.
- 기존 v1 `authorize_execution`, `execute_application`, fixture claim/adapter 실행 진입점은 `LEGACY_AUTHORIZATION_UNUSABLE`로 차단한다.
- live adapter, network, browser navigation, credential, PII, upload, click, submit은 추가하지 않는다.

## 계획 체크포인트와 baseline marker

현재 계획 파일은 untracked이므로 현재 working tree를 clean baseline으로 간주하지 않는다. 구현자는 다른 작업보다 먼저 이 계획 파일만 체크포인트 커밋하고, 그 커밋을 baseline marker에 기록한다. 특정 HEAD 값은 요구하지 않는다.

```powershell
git status --short
git add -- docs/engineering-discipline/plans/2026-07-12-contract-bound-authorization.md
git diff --cached --name-only
git commit -m "docs(plan): add M3 contract-bound authorization execution plan"
$baseline = git rev-parse HEAD
Set-Content -LiteralPath .git/career-pipeline-m3-baseline -Value $baseline -NoNewline
git status --porcelain=v1
```

기대 결과:

- 첫 명령에는 이 계획 파일만 untracked로 보인다.
- staged path는 이 계획 파일 하나뿐이다.
- baseline marker는 계획 체크포인트 커밋의 실제 HEAD를 기록한다.
- 마지막 status는 clean이다. clean이 아니면 구현을 시작하지 않는다.

그 다음 기준선 검증을 실행한다.

```powershell
python -m pytest --collect-only -q
python -m pytest -q
python -m pytest -q tests/test_application_execution.py tests/test_site_intake.py tests/test_form_adapter.py tests/test_jobkorea_jrs_adapter.py tests/test_saramin_applyin_adapter.py tests/test_application_package.py tests/test_cli.py
```

계획 시점 참고값은 전체 `476 collected / 471 passed, 5 skipped`, 집중 집합 `157 collected / 155 passed, 2 skipped`다. 실행 시 수치가 달라졌다면 marker HEAD의 실제 수치를 작업 기록에 다시 고정하고, 기존 실패가 있으면 M3 RED와 섞지 않는다.

## 파일 범위

구현 허용:

- `career_pipeline/application_execution.py`
- `career_pipeline/site_intake.py`
- `career_pipeline/form_adapter.py`
- `career_pipeline/models.py`
- `career_pipeline/adapters/jobkorea_jrs.py`
- `career_pipeline/adapters/saramin_applyin.py`
- `tests/test_application_execution.py`
- `tests/test_site_intake.py`
- `tests/test_form_adapter.py`
- `tests/test_jobkorea_jrs_adapter.py`
- `tests/test_saramin_applyin_adapter.py`
- `tests/test_cli.py`

고정 제외:

- `career_pipeline/__main__.py`
- `career_pipeline/application_package.py`
- `career_pipeline/platform_catalog.py`
- `career_pipeline/readiness.py`
- CLI parser와 명령 옵션
- fixture HTML, 문서, production dependency, live/network/browser 구현

`tests/test_cli.py`는 기존 parser를 바꾸지 않고 legacy fail-closed 결과만 검증하기 위해 포함한다.

## v2 계약

### `SiteReadOnlyContract` v2 exact fields

`career_pipeline/site_intake.py`의 frozen dataclass 필드와 순서를 다음으로 고정한다.

```text
site_id: str
platform_family: str
contract_id: str
contract_version: Literal[2]
observed_at: str
valid_until: str
exact_origin: str
allowed_path_patterns: tuple[str, ...]
fixture_sha256: str
schema_version: str
schema_sha256: str
adapter_id: str
adapter_contract_version: int
adapter_schema_sha256: str
page_steps: tuple[str, ...]
logical_fields: tuple[dict, ...]
form_selectors: tuple[str, ...]
form_actions: tuple[str, ...]
save_controls: tuple[str, ...]
next_controls: tuple[str, ...]
previous_controls: tuple[str, ...]
preview_controls: tuple[str, ...]
submit_controls: tuple[str, ...]
attachment_controls: tuple[str, ...]
iframe_origins: tuple[str, ...]
risk_markers: tuple[str, ...]
allowed_capabilities: tuple[Literal["fill_only", "submit"], ...]
mutation_enabled: bool
live_enabled: bool
manual_review_required: bool
validation_codes: tuple[str, ...]
```

site-intake builder는 `allowed_capabilities=()`, `mutation_enabled=False`, `live_enabled=False`만 생성한다. `valid_until`은 explicit timezone-aware 입력으로 받고 `valid_until > observed_at`을 요구한다. v1 registry envelope는 읽기 전용으로 유지하며 내부 v1 contract를 rewrite하지 않는다.

### canonical site contract digest API

`career_pipeline/application_execution.py`에 다음 API를 정의한다.

```python
def canonical_site_contract_sha256(contract: SiteReadOnlyContract) -> str: ...
```

이 함수는 `asdict(contract)`를 `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"))`로 UTF-8 직렬화한 뒤 lowercase SHA-256을 반환한다. 위 exact fields 전체가 digest 대상이다. secret, key, ledger state, runtime clock은 입력에 없다. `contract_version != 2`, missing/unknown field, invalid SHA/origin/time/capability 조합은 digest 전에 거부한다. 기존 `canonical_schema_sha256(schema)`는 변경하지 않는다.

### `ReviewDecisionV2` exact fields

`career_pipeline/application_execution.py`에 별도 frozen dataclass로 정의한다. 기존 v1 class에 optional field를 덧붙이지 않는다.

```text
schema_version: Literal[2]
review_id: str
package_id: str
package_sha256: str
posting_id: str
posting_sha256: str
profile_sha256: str
final_manifest_sha256: str
attachment_manifest_sha256: str
form_schema_sha256: str
site_contract_id: str
site_contract_sha256: str
site_contract_observed_at: str
site_contract_valid_until: str
exact_origin: str
adapter_id: str
adapter_contract_version: int
adapter_schema_sha256: str
allowed_capabilities: tuple[Literal["fill_only", "submit"], ...]
mutation_enabled: bool
live_enabled: bool
decision: Literal["approved", "rejected", "deferred"]
approver_id: str
decided_at: str
contract_version: Literal["controlled-execution-v2"]
key_id: str
signature_version: Literal["hmac-sha256-v2"]
integrity_sha256: str
```

`review_decision_v2_payload(review)`은 `integrity_sha256`만 제외한 위 필드를 선언 순서와 무관한 canonical JSON object로 반환한다.

### `AuthorizationCandidateV2` exact fields

read-only contract에서도 생성 가능한 unsigned local artifact다. mutation authority가 아니다.

```text
schema_version: Literal[2]
review_id: str
package_id: str
package_sha256: str
site_contract_id: str
site_contract_sha256: str
exact_origin: str
adapter_id: str
adapter_contract_version: int
adapter_schema_sha256: str
requested_mode: Literal["fill_only", "submit"]
requested_at: str
candidate_status: Literal["capability_disabled", "legacy_unusable", "eligible_for_external_review"]
reason_code: str
```

현재 production contract에서는 `candidate_status="capability_disabled"`만 가능하다. `eligible_for_external_review`는 합성 test fixture의 shape 검증에만 사용하며 issuance 성공을 뜻하지 않는다.

### `ExecutionAuthorizationV2` exact fields

```text
schema_version: Literal[2]
authorization_id: str
review_id: str
package_id: str
package_sha256: str
posting_id: str
posting_sha256: str
profile_sha256: str
final_manifest_sha256: str
attachment_manifest_sha256: str
form_schema_sha256: str
site_contract_id: str
site_contract_sha256: str
site_contract_observed_at: str
site_contract_valid_until: str
exact_origin: str
adapter_id: str
adapter_contract_version: int
adapter_schema_sha256: str
allowed_capabilities: tuple[Literal["fill_only", "submit"], ...]
mode: Literal["fill_only", "submit"]
approver_id: str
authorized_at: str
expires_at: str
nonce: str
contract_version: Literal["controlled-execution-v2"]
key_id: str
signature_version: Literal["hmac-sha256-v2"]
integrity_sha256: str
```

`execution_authorization_v2_payload(auth)`은 `integrity_sha256`만 제외한다. HMAC payload에는 package/review/site-contract/origin/adapter/schema/capability/time/nonce와 `key_id`, `signature_version`가 모두 들어간다.

`key_id`는 `authorize_execution_v2` 호출자가 제공하는 외부 non-secret identifier다. signing key에서 derive하거나 hash하지 않는다. `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`만 허용하고 secret은 dataclass, payload, JSON, error, ledger event에 저장하지 않는다.

## exact v2 입력 경로

```python
def approve_application_v2(
    package,
    dry_run_result,
    site_contract: SiteReadOnlyContract,
    *,
    decision,
    decided_at,
    approver_id,
    key_id,
    signing_key,
) -> ReviewDecisionV2: ...

def build_authorization_candidate_v2(
    package,
    review: ReviewDecisionV2,
    site_contract: SiteReadOnlyContract,
    *,
    adapter_id,
    adapter_contract_version,
    adapter_schema_sha256,
    allowed_origin,
    mode,
    requested_at,
) -> AuthorizationCandidateV2: ...

def authorize_execution_v2(
    package,
    review: ReviewDecisionV2,
    site_contract: SiteReadOnlyContract,
    *,
    adapter_id,
    adapter_contract_version,
    adapter_schema_sha256,
    allowed_origin,
    mode,
    authorized_at,
    expires_at,
    approver_id,
    key_id,
    signing_key,
) -> ExecutionAuthorizationV2: ...
```

`authorize_execution_v2` keyword inputs의 adapter lineage와 `key_id`는 생략할 수 없다. 이 값은 site contract와 review의 값에 exact-match 해야 한다. current read-only contract는 capability gate에서 항상 `FILL_AUTHORITY_DISABLED` 또는 `SUBMIT_AUTHORITY_DISABLED`로 실패한다.

## two-stage execution validation gate

`validate_execution_candidate_v2`는 mutation을 실행하지 않는다.

```python
def validate_execution_candidate_v2(
    package,
    review: ReviewDecisionV2,
    authorization: ExecutionAuthorizationV2,
    site_contract: SiteReadOnlyContract,
    driver,
    *,
    executed_at,
    ledger_path,
    key_id,
    signing_key,
) -> ValidatedExecutionCandidateV2: ...
```

### Stage A: driver probe 전

다음을 모두 먼저 검사한다.

- exact v2 class/schema/contract/signature version
- caller `key_id`와 artifact `key_id` 일치 및 HMAC
- package/review/site-contract/adapter/schema digest와 ID binding
- missing/modified evidence
- `executed_at < authorized_at`인 pre-issuance
- authorization expiry
- `executed_at > site_contract_valid_until`인 stale contract
- ledger integrity, revocation, reuse, duplicate state
- mode가 `allowed_capabilities`에 있고 mutation/live flags가 true인지

이 실패들의 테스트 기대값은 `probe_calls == []`, `mutation_calls == []`이다.

### Stage B: read-only live probe

Stage A 통과 후 아래 순서로만 호출한다.

1. `driver.current_origin()`
2. `driver.form_action_origin()`
3. `driver.current_form_schema_sha256()`

정확한 기대값:

- current origin mismatch: `probe_calls == ["current_origin"]`
- form action origin mismatch: `probe_calls == ["current_origin", "form_action_origin"]`
- schema mismatch: `probe_calls == ["current_origin", "form_action_origin", "current_form_schema_sha256"]`
- 모두 일치: 위 3개 probe 후 `ValidatedExecutionCandidateV2` 반환
- 모든 경우 `mutation_calls == []`

`ValidatedExecutionCandidateV2`는 mutation 권한이나 execution receipt가 아니며, M4/M5가 후속 live contract를 정의하기 전까지 외부 blocker 상태다.

## legacy와 CLI 경계

- `ExecutionArtifactClassification` enum은 `review_v1`, `authorization_v1`, `review_v2`, `authorization_v2`, `unsupported` 다섯 값만 가진다.
- `classify_execution_artifact(value: Mapping[str, Any]) -> ExecutionArtifactClassification`은 JSON을 쓰거나 upgrade하지 않는 순수 함수이며 M3의 legacy positive path다.
- 기존 CLI parser와 `__main__.py`는 M5까지 변경하지 않는다.
- legacy `application review`는 기존 v1 review artifact를 생성할 수 있다.
- v1 review/auth artifact loader는 진단을 위해 JSON을 읽고 `legacy_v1`으로 분류할 수 있다.
- legacy `application authorize`, `fill-fixture`, `execute_application`, `claim_fixture_fill_authorization`, adapter run entrypoint는 mutation 전에 `LEGACY_AUTHORIZATION_UNUSABLE`로 실패한다.
- CLI `main()`은 기존 예외 처리로 exit code `4`와 정확한 안정 코드 `LEGACY_AUTHORIZATION_UNUSABLE`을 출력한다.
- CLI parser, option, success output shape 변경은 M5로 미룬다.

## RED/GREEN 작업 순서

모든 Task는 “테스트 파일 수정 → collection 성공 확인 → RED 실행 → 구현 → 동일 명령 GREEN” 순서다. 존재하지 않는 node, import error, collection error는 유효한 RED가 아니다.

### Task 1: site contract/digest

먼저 `tests/test_site_intake.py`에 다음 5 node를 추가한다.

1. `test_site_contract_v2_has_exact_lineage_capability_and_freshness_fields`
2. `test_site_intake_can_only_build_disabled_capability_contracts`
3. `test_canonical_site_contract_sha256_is_stable`
4. `test_canonical_site_contract_sha256_changes_for_each_security_binding`
5. `test_legacy_registry_contract_is_readable_but_not_v2_issuable`

```powershell
python -m pytest --collect-only -q tests/test_site_intake.py -k "site_contract_v2 or disabled_capability_contracts or canonical_site_contract_sha256 or legacy_registry_contract"
python -m pytest -q tests/test_site_intake.py -k "site_contract_v2 or disabled_capability_contracts or canonical_site_contract_sha256 or legacy_registry_contract"
```

기대: collection `5`, RED `5 failed`, GREEN `5 passed`.

### Task 2: v2 dataclass/payload/issuance

먼저 `tests/test_application_execution.py`에 다음 13 node를 추가한다.

- 단일 7 node: exact ReviewDecisionV2 fields, exact AuthorizationCandidateV2 fields, exact ExecutionAuthorizationV2 fields, review payload, authorization payload, external key_id preservation, candidate local artifact
- parameterized 2 node: legacy review/auth classification
- parameterized 2 node: disabled read-only issuance rejection (`fill_only`, `submit`)
- 단일 2 node: adapter lineage mismatch, key_id/signature tamper

고정 함수명:

```text
test_review_decision_v2_exact_fields
test_authorization_candidate_v2_exact_fields
test_execution_authorization_v2_exact_fields
test_review_v2_payload_binds_all_fields_except_integrity
test_authorization_v2_payload_binds_all_fields_except_integrity
test_key_id_is_external_non_secret_and_not_derived
test_read_only_contract_builds_local_disabled_candidate
test_legacy_artifact_classification[review]
test_legacy_artifact_classification[authorization]
test_read_only_contract_cannot_issue_v2_mutation_authority[fill_only]
test_read_only_contract_cannot_issue_v2_mutation_authority[submit]
test_authorize_v2_rejects_adapter_lineage_mismatch
test_authorize_v2_rejects_key_id_or_signature_tamper
```

```powershell
python -m pytest --collect-only -q tests/test_application_execution.py -k "_v2_exact_fields or _v2_payload or key_id_is_external or local_disabled_candidate or legacy_artifact_classification or cannot_issue_v2_mutation_authority or adapter_lineage_mismatch or key_id_or_signature_tamper"
python -m pytest -q tests/test_application_execution.py -k "_v2_exact_fields or _v2_payload or key_id_is_external or local_disabled_candidate or legacy_artifact_classification or cannot_issue_v2_mutation_authority or adapter_lineage_mismatch or key_id_or_signature_tamper"
```

기대: collection `13`, RED `13 failed`, GREEN `13 passed`.

### Task 3: two-stage validation kernel

먼저 `tests/test_application_execution.py`에 정확히 15 node를 추가한다.

- Stage A 12 node: missing, modified, stale, pre-issuance, expired, revoked, reused, package mismatch, site-contract mismatch, adapter mismatch, HMAC/key mismatch, disabled capability
- Stage B 3 node: current origin, form-action origin, schema mismatch

각 Stage A node는 `probe_calls == []`와 `mutation_calls == []`를, Stage B node는 위 고정 probe 순서와 `mutation_calls == []`를 검사한다. 별도 1개 existing-or-new success node는 합성 signed enabled fixture로 3개 probe 후 `ValidatedExecutionCandidateV2` 반환과 mutation 0을 검사한다. 따라서 Task 3 총 node는 `16`이다.

```powershell
python -m pytest --collect-only -q tests/test_application_execution.py -k "stage_a_ or stage_b_ or validation_kernel_returns_candidate_without_mutation"
python -m pytest -q tests/test_application_execution.py -k "stage_a_ or stage_b_ or validation_kernel_returns_candidate_without_mutation"
```

기대: collection `16`, RED `16 failed`, GREEN `16 passed`.

### Task 4: form/adapter/CLI legacy boundary

먼저 아래 테스트를 추가한다.

- `tests/test_form_adapter.py`: 2 node
  - `test_form_schema_lineage_matches_site_contract_without_mutation`
  - `test_read_only_form_adapter_exposes_probe_only_contract`
- adapter test files: 2 node
  - `test_jobkorea_legacy_authorization_is_rejected_before_page_call`
  - `test_saramin_legacy_authorization_is_rejected_before_page_call`
- `tests/test_cli.py`: 3 node
  - `test_m3_cli_parser_shape_is_unchanged`
  - `test_m3_cli_legacy_authorize_fails_closed`
  - `test_m3_cli_legacy_fill_fixture_fails_closed`

```powershell
python -m pytest --collect-only -q tests/test_form_adapter.py tests/test_jobkorea_jrs_adapter.py tests/test_saramin_applyin_adapter.py tests/test_cli.py -k "site_contract_without_mutation or probe_only_contract or legacy_authorization_is_rejected_before_page_call or m3_cli_"
python -m pytest -q tests/test_form_adapter.py tests/test_jobkorea_jrs_adapter.py tests/test_saramin_applyin_adapter.py tests/test_cli.py -k "site_contract_without_mutation or probe_only_contract or legacy_authorization_is_rejected_before_page_call or m3_cli_"
```

기대: collection `7`, RED `7 failed`, GREEN `7 passed`. adapter page call은 0이고 CLI 두 실패는 exit `4`, 출력 `LEGACY_AUTHORIZATION_UNUSABLE`이다.

## migration compatibility

- v1 dataclass와 JSON reader는 diagnostic read/classification을 위해 유지한다.
- v1 authorization을 v2로 default-fill, auto-sign, rehash, rewrite하지 않는다.
- v1 registry/ledger artifact는 삭제하거나 migration write하지 않는다.
- package schema/SHA, application registry envelope, `canonical_schema_sha256`, `normalize_origin` wrapper는 유지한다.
- 기존 positive fixture mutation 테스트는 legacy success로 유지하지 않는다. 동일 node 수를 보존하면서 `LEGACY_AUTHORIZATION_UNUSABLE`, zero page/mutation calls로 기대를 최소 변경한다.
- public CLI parser는 유지하고 authorize/fill execution 기대만 stable fail-closed로 갱신한다.

## 커밋 계획

1. 계획 체크포인트
   - `docs(plan): add M3 contract-bound authorization execution plan`
   - 계획 파일 하나만 포함
2. RED 계약 테스트
   - `test(auth): specify M3 v2 authorization contract`
   - 허용된 test 파일만 포함
3. site contract와 v2 kernel
   - `feat(auth): bind authorization v2 to site contract lineage`
   - `application_execution.py`, `site_intake.py`, `form_adapter.py`, `models.py`
4. legacy adapter/CLI 경계
   - `fix(auth): reject legacy mutation authorization paths`
   - 두 adapter 파일과 관련 adapter/CLI tests

각 커밋 전에 `git diff --cached --name-only`를 확인한다. `git add .`, amend, reset/checkout, force push, PR, merge는 금지한다.

## 전체 검증과 예상 수치

신규 node는 Task 1 `5` + Task 2 `13` + Task 3 `16` + Task 4 `7` = 정확히 `41`개다. 기존 positive node를 negative로 바꾸는 작업은 node 수를 유지한다.

계획 시점 수치가 유지된 경우:

- 집중 집합: `198 collected / 196 passed, 2 skipped`
- 전체: `517 collected / 512 passed, 5 skipped`

```powershell
python -m pytest -q tests/test_application_execution.py tests/test_site_intake.py tests/test_form_adapter.py tests/test_jobkorea_jrs_adapter.py tests/test_saramin_applyin_adapter.py tests/test_application_package.py tests/test_cli.py
python -m pytest -q
python -m compileall -q career_pipeline
git diff --check
```

boundary scan:

```powershell
$baseline = Get-Content -LiteralPath .git/career-pipeline-m3-baseline -Raw
git diff --name-only "$baseline..HEAD"
git diff --check "$baseline..HEAD"
git diff --unified=0 "$baseline..HEAD" -- career_pipeline tests | Select-String -Pattern '^\+.*(requests|httpx|urllib\.request|socket|selenium|page\.goto|page\.click|page\.press|set_input_files)'
rg -n "mode=\"inspection\"|mode: Literal\[\"inspection\"" career_pipeline tests
git status --porcelain=v1
```

기대:

- commit range에는 계획 baseline 이후 허용 파일만 있다.
- diff check와 compileall은 exit `0`이다.
- 추가된 live/network/mutation API나 별도 inspection authorization mode는 없다.
- final working tree는 clean이다.
- 검증 완료 후에만 `Remove-Item -LiteralPath .git/career-pipeline-m3-baseline`로 marker를 제거한다.

## 자체 검토 체크리스트

- [ ] 계획 파일 체크포인트가 baseline marker보다 먼저다.
- [ ] 고정 HEAD 요구가 없다.
- [ ] Stage A 실패는 probe 0/mutation 0이다.
- [ ] Stage B는 current origin → form action → schema probe 순서이며 mutation 0이다.
- [ ] `canonical_site_contract_sha256(contract)` 위치·입력·canonicalization이 정확하다.
- [ ] `authorize_execution_v2`의 adapter lineage와 `key_id`가 필수 keyword input이다.
- [ ] `key_id`는 외부 non-secret 값이며 key에서 derive하지 않는다.
- [ ] 별도 inspection authorization mode를 도입하지 않았다.
- [ ] read-only contract는 fill/submit 발급이 모두 실패한다.
- [ ] M3는 validation candidate까지만 만들고 production driver mutation을 실행하지 않는다.
- [ ] legacy authorize/execute/fill은 `LEGACY_AUTHORIZATION_UNUSABLE`로 실패한다.
- [ ] `__main__.py`와 parser는 수정하지 않고 CLI fail-closed test만 갱신한다.
- [ ] 모든 RED는 test 추가와 collection 성공 뒤 assertion failure로 실행한다.
- [ ] code, network, fixture, dependency 범위가 확대되지 않는다.

## 중단 조건

- 계획 체크포인트 후 working tree가 clean하지 않다.
- Stage A가 driver probe를 호출하거나 Stage B가 mutation callback을 호출한다.
- read-only/live-disabled contract가 fill 또는 submit authority를 발급한다.
- v1 artifact가 auto-upgrade되거나 legacy mutation이 실행된다.
- CLI stable code를 위해 `__main__.py` 또는 parser 수정이 필요하다.
- v2 구현에 live adapter, network/browser, credential/PII, 새 dependency가 필요하다.
- 신규 test가 node-not-found/import/collection 오류로 RED가 된다.
- 허용 파일 밖 변경이나 unrelated test 감소가 발생한다.
