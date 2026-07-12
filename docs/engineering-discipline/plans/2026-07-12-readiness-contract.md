# M2B Requirements and Readiness Contract 실행 계획

> **Worker note:** 이 계획은 M2B 전용이다. 체크박스 순서대로 실행하고, 같은 파일을 여러 단계에서 수정하므로 모든 작업은 직렬 수행한다. M2B 범위 밖 파일이 변경되었거나 기준선이 달라졌으면 구현을 시작하지 말고 작업 조정을 요청한다.

**Goal:** 로컬 구현 상태, 오프라인 acceptance, 외부 입력, live 실행, 제출 상태를 하나의 boolean으로 합치지 않는 `career-pipeline-readiness-v1` 계약과 요구사항 추적표를 구현한다.

**Architecture:** `career_pipeline/readiness.py`는 I/O가 없는 순수 도메인 계층으로 만든다. 문자열 enum, frozen dataclass, 엄격한 검증, 결정적 JSON 직렬화만 제공하고, 파일 저장·CLI·네트워크·브라우저·mutation 기능은 포함하지 않는다. `tests/test_readiness.py`가 계약과 fail-closed 불변식을 고정하며, `docs/engineering-discipline/harness/career-pipeline-completion/requirements-trace-v1.md`가 요구사항별 분류와 증거 위치를 추적한다.

**Tech Stack:** Python 3.11+, 표준 라이브러리 `dataclasses`, `datetime`, `enum`, `hashlib`, `json`, `re`; pytest.

**Work Scope:**

- **In scope:** `career_pipeline/readiness.py`, `tests/test_readiness.py`, `docs/engineering-discipline/harness/career-pipeline-completion/requirements-trace-v1.md`의 신규 생성과 이 세 파일만을 대상으로 한 테스트·문서·커밋.
- **Out of scope:** `career_pipeline/__main__.py`, `tests/test_cli.py`, 기존 model/site-intake/application-execution/application-package 코드 수정, persistence, CLI 노출, exit code, offline acceptance 실행기, authorization v2, live adapter, URL fetch, network, browser, credentials, 실제 PII, upload/click/submit/receipt 수집.

**Locked baseline:**

- Branch at planning time: `codex/phase6-5-site-intake-readonly`
- Commit: `6b127c974daf008341e03feb74052b74bb5e0d12`
- Full suite: `425 passed, 2 skipped`
- M2B adds exactly 14 tests; expected full suite after M2B: `439 passed, 2 skipped`
- `__main__.py` must remain byte-for-byte unchanged from `6b127c974daf008341e03feb74052b74bb5e0d12`.

**Verification Strategy:**

- **Level:** test-suite
- **Focused command:** `python -m pytest tests/test_readiness.py -q`
- **Full command:** `python -m pytest -q`
- **Static commands:** `python -m compileall -q career_pipeline`, `git diff --check`
- **What it validates:** 정확히 다섯 축이 분리되고, 요구사항 분류·증거·blocker가 엄격히 검증되며, aggregate test count가 readiness 입력으로 승격되지 않고, M2B가 live/network/CLI 표면을 만들지 않았음을 검증한다.

---

## 1. 조사 결과와 호환성 경계

- `career_pipeline/models.py`는 frozen dataclass와 `Literal`을 사용하고, application package는 `schema_version=1`, tuple 내부 표현, list JSON 표현을 사용한다.
- `career_pipeline/site_intake.py`는 `CONTRACT_VERSION=1`, exact HTTPS origin, fixture/schema SHA-256, `mutation_enabled=False`, `live_enabled=False`를 기록한다. 준비 상태도 live 권한을 뜻하지 않는다.
- `career_pipeline/application_execution.py`에는 현재 `fill_only`/`submit` 도메인 코드가 있지만 운영 live adapter/CLI가 없다. M2B는 이 코드를 호출하거나 권한을 발급하지 않고 현재 상태를 `disabled`/`not_attempted`로 표현할 수 있는 계약만 만든다.
- `career_pipeline/application_package.py`는 review-only package, artifact SHA-256, strict from/to-dict 관례를 제공한다. M2B는 package 내용을 재직렬화하지 않고 evidence source로만 참조한다.
- `career_pipeline/__main__.py`의 readiness CLI 연결은 M5 소유다. M2B에서 import, parser, command handler를 추가하지 않는다.
- `docs/site-intake.md`, `docs/application-execution.md`, `docs/career-pipeline-usage.md`의 no-live/no-network 문구를 유지한다. M2B는 이 문서들을 수정하지 않는다.
- 테스트 통과 수는 코드 건강성 증거일 뿐 readiness axis 상태가 아니다. report 및 evidence dataclass에 `test_count`, `passed_count`, `failed_count`, `skipped_count`, `coverage_percent` 필드를 두지 않는다.

## 2. 고정 공개 계약

### 2.1 상수와 enum

`career_pipeline/readiness.py`에 아래 이름과 값만 공개한다.

```python
READINESS_SCHEMA_VERSION = "career-pipeline-readiness-v1"
REQUIREMENTS_TRACE_VERSION = "career-pipeline-requirements-trace-v1"

class RequirementClassification(str, Enum):
    IMPLEMENTED = "implemented"
    LOCALLY_MISSING = "locally_missing"
    EXTERNAL_ONLY = "external_only"

class ReadinessAxisName(str, Enum):
    LOCAL_FOUNDATION = "local_foundation"
    OFFLINE_ACCEPTANCE = "offline_acceptance"
    EXTERNAL_INPUTS = "external_inputs"
    LIVE_EXECUTION = "live_execution"
    SUBMISSION = "submission"

class LocalFoundationStatus(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"

class OfflineAcceptanceStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"

class ExternalInputsStatus(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"

class LiveExecutionStatus(str, Enum):
    DISABLED = "disabled"
    REVIEW_REQUIRED = "review_required"
    AUTHORIZED = "authorized"

class SubmissionStatus(str, Enum):
    NOT_ATTEMPTED = "not_attempted"
    UNVERIFIED = "unverified"
    VERIFIED = "verified"

class EvidenceSourceKind(str, Enum):
    CODE = "code"
    TEST = "test"
    ARTIFACT = "artifact"
    DOCUMENT = "document"
    EXTERNAL_ATTESTATION = "external_attestation"

class EvidenceFreshness(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"

class BlockerCode(str, Enum):
    ORIGIN_UNCONFIRMED = "ORIGIN_UNCONFIRMED"
    DOM_UNVERIFIED = "DOM_UNVERIFIED"
    AUTOMATION_POLICY_UNCONFIRMED = "AUTOMATION_POLICY_UNCONFIRMED"
    CREDENTIALS_UNAVAILABLE = "CREDENTIALS_UNAVAILABLE"
    MFA_REQUIRED = "MFA_REQUIRED"
    CAPTCHA_PRESENT = "CAPTCHA_PRESENT"
    PII_TRANSMISSION_UNAUTHORIZED = "PII_TRANSMISSION_UNAUTHORIZED"
    UPLOAD_NOT_AUTHORIZED = "UPLOAD_NOT_AUTHORIZED"
    CLICK_NOT_AUTHORIZED = "CLICK_NOT_AUTHORIZED"
    SUBMIT_NOT_AUTHORIZED = "SUBMIT_NOT_AUTHORIZED"
    RECEIPT_UNVERIFIED = "RECEIPT_UNVERIFIED"
```

`AxisStatus` type alias는 다섯 status enum의 union으로 정의한다. 허용 조합은 다음 표와 정확히 일치해야 한다.

| axis | 허용 status |
|---|---|
| `local_foundation` | `complete`, `incomplete` |
| `offline_acceptance` | `passed`, `failed`, `not_run` |
| `external_inputs` | `ready`, `blocked` |
| `live_execution` | `disabled`, `review_required`, `authorized` |
| `submission` | `not_attempted`, `unverified`, `verified` |

### 2.2 frozen dataclass

필드 순서와 타입을 아래대로 고정한다.

```python
@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    source_kind: EvidenceSourceKind
    source: str
    sha256: str | None
    version: str | None
    observed_at: str | None
    freshness: EvidenceFreshness

@dataclass(frozen=True)
class RequirementRecord:
    requirement_id: str
    axis: ReadinessAxisName
    title: str
    classification: RequirementClassification
    evidence_ids: tuple[str, ...]
    blocker_codes: tuple[BlockerCode, ...] = ()
    cli_exposure: str = "deferred_to_m5"

@dataclass(frozen=True)
class BlockerRecord:
    code: BlockerCode
    axis: ReadinessAxisName
    requirement_id: str
    message: str
    evidence_ids: tuple[str, ...] = ()

@dataclass(frozen=True)
class AxisReadiness:
    axis: ReadinessAxisName
    status: AxisStatus
    requirement_ids: tuple[str, ...]
    blocker_codes: tuple[BlockerCode, ...]
    evidence_ids: tuple[str, ...]

@dataclass(frozen=True)
class ProjectReadinessReport:
    schema_version: str
    requirements_trace_version: str
    generated_at: str
    axes: tuple[AxisReadiness, ...]
    requirements: tuple[RequirementRecord, ...]
    blockers: tuple[BlockerRecord, ...]
    evidence: tuple[EvidenceRecord, ...]
```

### 2.3 검증 규칙

`ReadinessContractError(ValueError)`와 `validate_readiness_report(report) -> ProjectReadinessReport`를 구현한다.

1. `schema_version`과 `requirements_trace_version`은 위 상수와 정확히 같아야 한다.
2. `generated_at`과 `observed_at`은 값이 있으면 timezone-aware ISO-8601이어야 한다.
3. ID는 `^[A-Z0-9][A-Z0-9_.-]{2,79}$`, SHA는 `^[0-9a-f]{64}$`를 만족한다. `source`, `title`, `message`, `version`은 해당 값이 존재하면 trim 후 비어 있지 않아야 한다.
4. evidence는 `sha256` 또는 `version` 중 하나 이상을 가져야 한다. `ARTIFACT`는 반드시 `sha256`을 갖는다. `CURRENT`/`STALE`은 `observed_at`을 요구한다. `NOT_APPLICABLE`은 `observed_at=None`만 허용한다.
5. evidence/requirement ID는 각각 유일해야 한다. 모든 `evidence_ids`, `requirement_ids`는 존재하는 ID를 가리킨다.
6. axis는 위 표의 순서로 정확히 다섯 개가 한 번씩 있어야 하며 axis/status enum 조합이 맞아야 한다.
7. requirement와 blocker tuple은 각각 `requirement_id`, `(code.value, requirement_id)` 오름차순이어야 한다. 각 axis의 참조 tuple도 중복 없이 정렬되어야 한다.
8. `implemented`는 같은 requirement가 참조하는 evidence에 `CODE`와 `TEST`가 모두 있어야 하고 blocker가 없어야 한다.
9. `locally_missing`은 blocker가 없어야 한다. 이는 저장소/오프라인에서 해결할 수 있는 공백이며 external blocker로 위장하지 않는다.
10. `external_only`는 blocker code가 하나 이상이어야 하고 같은 requirement를 가리키는 `BlockerRecord`가 각 code마다 정확히 하나 있어야 한다.
11. blocker의 axis와 requirement의 axis가 같아야 한다. axis의 blocker/evidence/requirement 참조는 해당 axis 소속 record에서 계산한 집합과 정확히 같아야 한다.
12. `local_foundation=complete`는 `local_foundation` 요구사항에 `locally_missing`이 없을 때만 허용한다. `external_only` 요구사항은 이 축을 incomplete로 만들지 않는다.
13. `offline_acceptance=passed`는 `offline_acceptance` 요구사항이 모두 `implemented`일 때만 허용한다. `locally_missing`이 있으면 `not_run` 또는 `failed`만 허용한다.
14. `external_inputs=ready`는 `external_inputs` blocker가 0개일 때만 허용한다. 하나라도 있으면 `blocked`여야 한다.
15. `live_execution=authorized`는 `live_execution` blocker가 0개이고 관련 요구사항이 모두 `implemented`일 때만 허용한다. M2B trace의 기본 상태는 `disabled`다.
16. `submission=verified`는 `RECEIPT_UNVERIFIED` blocker가 없고 submission 요구사항이 모두 `implemented`일 때만 허용한다. M2B trace의 기본 상태는 `not_attempted`다.
17. dataclass와 JSON 허용 키에는 aggregate test count 필드를 두지 않는다. strict deserializer는 알 수 없는 키를 거부하므로 `test_count`, `passed_count`, `failed_count`, `skipped_count`, `coverage_percent`, 최상위 `ready`를 모두 거부한다.

### 2.4 생성·직렬화 함수

아래 함수명과 반환형을 고정한다.

```python
def build_readiness_report(
    *,
    generated_at: str,
    axis_statuses: Mapping[ReadinessAxisName, AxisStatus],
    requirements: Iterable[RequirementRecord],
    blockers: Iterable[BlockerRecord],
    evidence: Iterable[EvidenceRecord],
) -> ProjectReadinessReport: ...

def readiness_report_to_dict(report: ProjectReadinessReport) -> dict[str, Any]: ...
def readiness_report_from_dict(value: Any) -> ProjectReadinessReport: ...
def canonical_readiness_json(report: ProjectReadinessReport) -> bytes: ...
def readiness_report_sha256(report: ProjectReadinessReport) -> str: ...
```

- builder는 requirements/blockers/evidence를 위 정렬 규칙대로 정렬하고 axis 참조 tuple을 record에서 계산한다. 호출자가 axis 참조를 직접 주입할 수 없게 한다.
- `to_dict`는 enum을 `.value`, tuple을 JSON list로 변환하고 dataclass 필드 외 키를 만들지 않는다.
- `from_dict`는 각 객체 레벨의 key set이 dataclass 필드 집합과 정확히 같을 때만 수용한다. 누락 키와 초과 키를 모두 `ReadinessContractError`로 거부한다.
- `canonical_readiness_json`은 `json.dumps(..., ensure_ascii=False, sort_keys=True, separators=(",", ":"))`의 UTF-8 bytes를 반환하고 newline을 붙이지 않는다.
- `readiness_report_sha256`은 canonical bytes의 lowercase SHA-256을 반환한다.
- 어떤 함수도 경로를 열거나 환경변수를 읽거나 시간을 내부 생성하지 않는다. clock은 `generated_at`/`observed_at` 인자로만 들어온다.

## 3. 요구사항 trace 문서 계약

생성 경로는 `docs/engineering-discipline/harness/career-pipeline-completion/requirements-trace-v1.md`다. UTF-8 Markdown이며 아래 구조를 정확히 사용한다.

1. H1 `# Career Pipeline Requirements Trace v1`
2. 메타데이터 bullet:
   - `Schema: career-pipeline-readiness-v1`
   - `Trace version: career-pipeline-requirements-trace-v1`
   - `CLI exposure: deferred_to_m5`
   - `Live boundary: disabled; no network, browser, credentials, real PII, upload, click, or submit`
3. 고정 열 표:

```text
| requirement_id | axis | classification | implementation_paths | test_ids | artifact_sources | cli_exposure | blocker_codes | rationale |
```

4. requirement ID는 오름차순으로 다음 14개를 정확히 기록한다.

| requirement_id | axis | classification | blocker_codes |
|---|---|---|---|
| `REQ-CAPTCHA` | `external_inputs` | `external_only` | `CAPTCHA_PRESENT` |
| `REQ-CLICK` | `live_execution` | `external_only` | `CLICK_NOT_AUTHORIZED` |
| `REQ-CREDENTIALS` | `external_inputs` | `external_only` | `CREDENTIALS_UNAVAILABLE` |
| `REQ-DOM` | `external_inputs` | `external_only` | `DOM_UNVERIFIED` |
| `REQ-LIVE-EXECUTION` | `live_execution` | `external_only` | `ORIGIN_UNCONFIRMED,DOM_UNVERIFIED,AUTOMATION_POLICY_UNCONFIRMED,CREDENTIALS_UNAVAILABLE,PII_TRANSMISSION_UNAUTHORIZED` |
| `REQ-MFA` | `external_inputs` | `external_only` | `MFA_REQUIRED` |
| `REQ-OFFLINE-ACCEPTANCE` | `offline_acceptance` | `locally_missing` | 빈 셀 |
| `REQ-ORIGIN` | `external_inputs` | `external_only` | `ORIGIN_UNCONFIRMED` |
| `REQ-PII-AUTHORITY` | `external_inputs` | `external_only` | `PII_TRANSMISSION_UNAUTHORIZED` |
| `REQ-POLICY` | `external_inputs` | `external_only` | `AUTOMATION_POLICY_UNCONFIRMED` |
| `REQ-READINESS-CONTRACT` | `local_foundation` | `implemented` | 빈 셀 |
| `REQ-RECEIPT` | `submission` | `external_only` | `RECEIPT_UNVERIFIED` |
| `REQ-SUBMIT` | `live_execution` | `external_only` | `SUBMIT_NOT_AUTHORIZED` |
| `REQ-UPLOAD` | `live_execution` | `external_only` | `UPLOAD_NOT_AUTHORIZED` |

모든 행의 `cli_exposure`는 `deferred_to_m5`다. `REQ-READINESS-CONTRACT`의 implementation은 `career_pipeline/readiness.py`, tests는 이 계획의 14 test node ID, artifact source는 `career-pipeline-readiness-v1`과 canonical SHA contract를 적는다. `REQ-OFFLINE-ACCEPTANCE` rationale에는 `M4 owns career_pipeline/offline_acceptance.py; absent in M2B`를 적는다. external row는 로컬 코드가 외부 사실을 추정할 수 없다는 근거와 관련 기존 문서 또는 코드 경로를 적는다.

5. 표 아래 `## Axis interpretation`에서 기본 M2B 상태를 정확히 기록한다.

- `local_foundation=complete`
- `offline_acceptance=not_run`
- `external_inputs=blocked`
- `live_execution=disabled`
- `submission=not_attempted`

이 상태는 M2B 계약 자체의 상태 예시이며 현재 실제 지원서의 live readiness 주장이나 생성 artifact가 아니다.

---

## 4. 실행 작업

### Task 0: 기준선과 소유권 게이트

**Dependencies:** 없음

**Files:** 읽기 전용

- [ ] **Step 1: 기준 commit과 clean 상태 확인**

Run:

```powershell
git rev-parse HEAD
git status --porcelain=v1
```

Expected: 둘째 명령은 출력 없음. 계획 체크포인트 커밋 때문에 현재 HEAD가 locked baseline보다 앞서는 것은 허용하되, 다음 명령이 exit `0`이어야 한다. 구현 직전 HEAD를 로컬 Git 메타데이터에 기록하며 이 파일은 절대 stage하지 않는다.

```powershell
git merge-base --is-ancestor 6b127c974daf008341e03feb74052b74bb5e0d12 HEAD
Set-Content -LiteralPath .git/career-pipeline-m2b-baseline -Value (git rev-parse HEAD) -NoNewline
```

- [ ] **Step 2: 기준 테스트 확인**

Run: `python -m pytest -q`

Expected: `425 passed, 2 skipped`.

- [ ] **Step 3: 금지 파일 기준 hash 기록**

Run: `git hash-object career_pipeline/__main__.py tests/test_cli.py docs/career-pipeline-usage.md docs/application-execution.md docs/site-intake.md`

Expected: 다섯 hash가 출력된다. 최종 단계에서 같은 명령 결과와 비교한다.

### Task 1: versioned report와 결정적 직렬화

**Dependencies:** Task 0 완료 후

**Files:**

- Create: `career_pipeline/readiness.py`
- Create: `tests/test_readiness.py`

- [ ] **Step 1: 첫 8개 RED 테스트 작성**

`tests/test_readiness.py`에 공용 fixture `make_report()`와 아래 node ID를 정확히 작성한다.

```text
test_contract_enums_are_stable
test_report_serialization_is_versioned_canonical_and_has_no_ready_boolean
test_report_round_trip_preserves_enum_and_tuple_types
test_report_sha256_matches_canonical_bytes
test_report_rejects_missing_duplicate_or_misordered_axes
test_report_rejects_status_from_another_axis
test_deserializer_rejects_unknown_and_missing_keys
test_builder_sorts_records_and_derives_axis_references
```

`make_report()`는 14 requirement와 16 blocker record를 사용한다. stable blocker code 종류는 11개이고, `REQ-LIVE-EXECUTION`이 다섯 외부 선결조건을 자기 axis에서 다시 참조하므로 record 수는 16개다. 기본 axis 상태는 `complete/not_run/blocked/disabled/not_attempted`로 만든다. evidence ID는 `EVIDENCE-CODE`, `EVIDENCE-TEST`, `EVIDENCE-DOC`, `EVIDENCE-EXTERNAL`을 사용하며 정렬된 tuple을 기대한다. 테스트 시간은 `2026-07-12T18:00:00+09:00`, SHA fixture는 `"a" * 64`로 고정한다.

- [ ] **Step 2: RED 확인**

Run: `python -m pytest tests/test_readiness.py -q`

Expected: collection error 1건, `ModuleNotFoundError: No module named 'career_pipeline.readiness'`, passed 0.

- [ ] **Step 3: enum, dataclass, builder, 직렬화 구현**

`career_pipeline/readiness.py`에 §2의 공개 계약을 그대로 구현한다. 이 단계에서는 §2.3의 구조·타입·정렬·참조·axis/status·strict key 검증을 포함한다. 분류별 evidence/blocker 의미 검증은 Task 2에서 완성한다.

- [ ] **Step 4: GREEN 확인**

Run: `python -m pytest tests/test_readiness.py -q`

Expected: `8 passed`.

- [ ] **Step 5: 정확한 범위만 stage/commit**

Run:

```powershell
git add -- career_pipeline/readiness.py tests/test_readiness.py
git diff --cached --name-only -- career_pipeline/readiness.py tests/test_readiness.py
git commit --only -m "feat(readiness): define versioned report contract" -- career_pipeline/readiness.py tests/test_readiness.py
```

Expected: staged/committed path는 두 파일뿐이다. 다른 작업자의 staged 파일은 commit에 포함하지 않고 reset/stash/revert하지 않는다.

### Task 2: 분류·증거 freshness·stable blocker 불변식

**Dependencies:** Task 1 완료 후

**Files:**

- Modify: `career_pipeline/readiness.py`
- Modify: `tests/test_readiness.py`

- [ ] **Step 1: 다음 4개 RED 테스트 추가**

```text
test_implemented_requires_code_and_test_evidence_and_no_blocker
test_locally_missing_cannot_use_external_blockers
test_external_only_requires_matching_stable_blocker_records
test_evidence_requires_source_sha_or_version_and_valid_freshness
```

각 테스트는 한 규칙마다 invalid report를 하나씩 만들고 `ReadinessContractError`의 안정된 message fragment를 확인한다: 각각 `implemented evidence`, `locally_missing blocker`, `external_only blocker`, `evidence freshness`.

- [ ] **Step 2: RED 확인**

Run:

```powershell
python -m pytest tests/test_readiness.py::test_implemented_requires_code_and_test_evidence_and_no_blocker tests/test_readiness.py::test_locally_missing_cannot_use_external_blockers tests/test_readiness.py::test_external_only_requires_matching_stable_blocker_records tests/test_readiness.py::test_evidence_requires_source_sha_or_version_and_valid_freshness -q
```

Expected: `4 failed`.

- [ ] **Step 3: 의미 검증 구현**

§2.3 4번과 8~16번 규칙을 `validate_readiness_report()`에 추가한다. blocker code는 enum의 11개 값 외 문자열을 deserializer에서 거부한다. external-only blocker가 local foundation을 incomplete로 바꾸지 않는 규칙과 M2B 기본 다섯 status 조합을 통과시킨다.

- [ ] **Step 4: aggregate test count 비승격 테스트 1개 추가 후 즉시 GREEN**

추가 node ID:

```text
test_aggregate_test_counts_are_rejected_as_readiness_inputs
```

정상 report dict의 최상위에 `test_count=425`, evidence 객체에 `passed_count=425`를 각각 넣고 두 경우 모두 `ReadinessContractError`가 발생하는지 확인한다. report dataclass에 count 필드를 추가해서 해결하면 안 된다.

Run: `python -m pytest tests/test_readiness.py -q`

Expected: `13 passed`.

- [ ] **Step 5: 정확한 범위만 stage/commit**

Run:

```powershell
git add -- career_pipeline/readiness.py tests/test_readiness.py
git commit --only -m "feat(readiness): enforce evidence and blocker invariants" -- career_pipeline/readiness.py tests/test_readiness.py
```

Expected: commit path는 두 파일뿐이다.

### Task 3: versioned requirements trace

**Dependencies:** Task 2 완료 후

**Files:**

- Modify: `tests/test_readiness.py`
- Create: `docs/engineering-discipline/harness/career-pipeline-completion/requirements-trace-v1.md`

- [ ] **Step 1: 문서 RED 테스트 1개 추가**

추가 node ID:

```text
test_requirements_trace_matches_contract_and_defers_cli_to_m5
```

테스트는 문서를 UTF-8로 읽고 Markdown 표의 첫 열을 파싱한다. schema/trace version, 고정 표 header, 첫 열의 14 requirement ID가 각각 정확히 한 번 등장하는지, 11 blocker code가 모두 등장하는지, `deferred_to_m5`, 다섯 기본 axis 상태가 등장하는지 확인한다. `python -m career_pipeline` readiness 명령 예시는 없어야 한다.

- [ ] **Step 2: RED 확인**

Run: `python -m pytest tests/test_readiness.py::test_requirements_trace_matches_contract_and_defers_cli_to_m5 -q`

Expected: `1 failed` with `FileNotFoundError` for `requirements-trace-v1.md`.

- [ ] **Step 3: 요구사항 trace 문서 작성**

§3의 경로·메타데이터·표 열·14개 행·axis interpretation을 그대로 작성한다. 현재 코드에서 확인 가능한 implementation/test/document 경로만 적고, 실제 origin/DOM/policy/credentials/PII authority/live action/receipt를 확인했다는 표현은 쓰지 않는다.

- [ ] **Step 4: GREEN 확인**

Run: `python -m pytest tests/test_readiness.py -q`

Expected: `14 passed`.

- [ ] **Step 5: 정확한 범위만 stage/commit**

Run:

```powershell
git add -- tests/test_readiness.py docs/engineering-discipline/harness/career-pipeline-completion/requirements-trace-v1.md
git commit --only -m "docs(readiness): add versioned requirements trace" -- tests/test_readiness.py docs/engineering-discipline/harness/career-pipeline-completion/requirements-trace-v1.md
```

Expected: commit path는 두 파일뿐이다.

### Task 4 (Final): 회귀·경계·커밋 검증

**Dependencies:** Task 1~3 완료 후

**Files:** 읽기 전용 검증

- [ ] **Step 1: 전용 테스트와 수집 수 확인**

Run:

```powershell
python -m pytest tests/test_readiness.py --collect-only -q
python -m pytest tests/test_readiness.py -q
```

Expected: `14 tests collected`, `14 passed`.

- [ ] **Step 2: 전체 회귀 확인**

Run: `python -m pytest -q`

Expected: `439 passed, 2 skipped`. Task 0 이후 다른 작업자의 승인된 테스트 commit이 먼저 합쳐졌다면 M2B delta는 정확히 `+14`여야 하며, 총합이 달라진 사실과 선행 commit을 보고하고 임의로 테스트를 삭제하거나 수치를 맞추지 않는다.

- [ ] **Step 3: compile과 whitespace 확인**

Run:

```powershell
python -m compileall -q career_pipeline
$m2bBaseline = Get-Content -LiteralPath .git/career-pipeline-m2b-baseline -Raw
git diff --check "$m2bBaseline..HEAD"
```

Expected: 두 명령 모두 출력 없이 exit 0.

- [ ] **Step 4: no-live/no-network 및 CLI 금지 경계 확인**

Run:

```powershell
git diff --exit-code "$m2bBaseline..HEAD" -- career_pipeline/__main__.py tests/test_cli.py docs/career-pipeline-usage.md docs/application-execution.md docs/site-intake.md
$matches = rg -n "^(from|import) (requests|httpx|socket|urllib|playwright|selenium|webbrowser|subprocess)(\.|\s|$)" career_pipeline/readiness.py tests/test_readiness.py
if ($LASTEXITCODE -eq 0) { $matches; throw "forbidden live/network import" }
if ($LASTEXITCODE -ne 1) { throw "scan failed" }
$matches = rg -n "test_count|passed_count|failed_count|skipped_count|coverage_percent|\"ready\"\s*:" career_pipeline/readiness.py
if ($LASTEXITCODE -eq 0) { $matches; throw "aggregate test count or collapsed ready field found" }
if ($LASTEXITCODE -ne 1) { throw "scan failed" }
```

Expected: diff와 두 scan 모두 match/output 없이 완료된다. match가 하나라도 있으면 명시적으로 실패한다.

- [ ] **Step 5: 변경·commit 범위 확인**

Run:

```powershell
$m2bBaseline = Get-Content -LiteralPath .git/career-pipeline-m2b-baseline -Raw
git diff --name-only "$m2bBaseline..HEAD" -- career_pipeline/readiness.py tests/test_readiness.py docs/engineering-discipline/harness/career-pipeline-completion/requirements-trace-v1.md
git log --format="%s" "$m2bBaseline..HEAD" -- career_pipeline/readiness.py tests/test_readiness.py docs/engineering-discipline/harness/career-pipeline-completion/requirements-trace-v1.md
git status --porcelain=v1
```

Expected:

- M2B 경로는 정확히 세 개다.
- M2B commit message는 정확히 다음 세 개다: `feat(readiness): define versioned report contract`, `feat(readiness): enforce evidence and blocker invariants`, `docs(readiness): add versioned requirements trace`.
- M2B 소유 파일에 uncommitted 변경이 없다. 다른 작업자의 unrelated 변경이 보이면 그대로 두고 M2B 결과와 분리해 보고한다.

- [ ] **Step 6: 모든 검증이 통과한 뒤 로컬 baseline marker만 제거**

Run:

```powershell
Remove-Item -LiteralPath .git/career-pipeline-m2b-baseline
```

Expected: marker가 제거되고 tracked/staged 상태에는 변화가 없다.

---

## 5. 자체 검토 체크리스트

- [x] M2B milestone의 세 산출물 경로를 모두 명시했다.
- [x] exact enum 값, dataclass 필드 순서, strict serialization, canonical hash 규칙을 고정했다.
- [x] 다섯 axis와 axis별 status를 하나의 `ready` boolean 없이 분리했다.
- [x] `implemented`, `locally_missing`, `external_only`의 상호 배타적 검증 규칙을 명시했다.
- [x] origin, DOM, policy, credentials, MFA, CAPTCHA, PII authority, upload, click, submit, receipt의 11개 stable blocker code를 고정했다.
- [x] evidence source/SHA/version/timestamp/freshness 규칙을 명시했다.
- [x] aggregate test count가 schema 및 판정 입력에 들어가지 못하도록 strict-key RED/GREEN 테스트를 명시했다.
- [x] RED/GREEN node ID, 명령, 단계별 `8/13/14`, 전체 `439 passed, 2 skipped` 수치를 명시했다.
- [x] requirements trace 경로, Markdown 구조, 열, 14개 행, 기본 axis 상태를 명시했다.
- [x] `__main__.py`와 CLI 문서 수정 금지, no-live/no-network/no-PII 경계를 명시했다.
- [x] 같은 파일을 수정하는 작업을 직렬화하고 정확한 stage/commit 범위와 메시지를 명시했다.
- [x] 다른 작업자의 파일을 reset/stash/revert하지 않는 중단 및 보고 규칙을 명시했다.
- [x] final verification이 전용 테스트, 전체 회귀, compile, diff, 금지 import, 금지 파일, commit 범위를 모두 확인한다.
