# Behavior IR Correctness Repair 감사 (2026-08-17)

- 기준 `origin/main` 시작 SHA: `8588cdf9ffe01bc3769089b2e5ddf573b4d07788`
- 작업 성격: **SHADOW correctness repair**. writer selection, Reliable Judge, Golden Path pass/block, interview scoring, ConstructCertificate production integration, Evidence Portfolio selection rule은 변경하지 않는다.
- 개인정보 경계: `career_runs/`는 `.gitignore` 대상이다. 실제 atomic claim·회사명·개인 수치는 이 문서나 Git에 기록하지 않는다.

## 최종 판정: HOLD_CORRECTNESS

코드 수준의 네 correctness 결함은 수리했고 correctness 전용 합성 회귀는 통과했다. 그러나 이번 실행 환경에는 git-ignore된 실제 `career_runs/` 37-run corpus가 없고, 일반 네트워크가 차단되어 전체 repository checkout도 만들 수 없었다. 따라서 **full pytest, 기존 18-case 전체 재실행, 37-run AFTER 재감사, PRIVATE review candidate 재생성을 실행 완료로 주장할 수 없다.** 이 네 항목이 닫히기 전에는 `READY_FOR_HUMAN_CALIBRATION`으로 판정하지 않는다.

## 1. 확인된 네 correctness 문제

1. `construct_relation_v2`가 criterion candidate를 순회하면서 첫 action-compatible atom에서 중단해, 뒤쪽 full action+object match를 놓칠 수 있었다.
2. `BehaviorAtom`이 ProfileClaim의 `verification.contribution`을 보존하지 않아 `caused / contributed / observed / unknown`의 권한 차이를 relation v2가 검사할 수 없었다.
3. `build_behavior_atoms(raw_mapping)`은 qualitative confirmed claim의 EvidenceRef/source binding을 함수 자체에서 fail-closed 검증하지 않았다. `claim_submission_issues()`는 qualitative claim의 evidence 존재·SHA/source_path 유효성까지 보증하지 않는다.
4. `construct_relation_v2`의 `direct_run_count`와 safety counter가 hard-coded 0 또는 계산 상태가 불명확해, 실측 0과 구조상 차단을 구분할 수 없었다.

## 2. Object matcher before / after

Before:

```text
criterion → atom 순회 → 첫 action match 발견 → object mismatch여도 break
```

After:

```text
criterion → 모든 candidate atom 검사
FULL(action+object) > ACTION-ONLY > MISSING
```

relation row에 다음 shadow 진단을 추가했다.

- `criterion_match_states`
- `object_match_fixed_criterion_ids`
- `legacy_relation_without_object_match_fix`
- `object_match_fix_changed_relation`

따라서 atom 순서가 바뀌어도 repaired relation과 criterion match state는 동일하다. legacy 결과는 실제 입력 순서 기준의 before/after 계측에만 사용한다.

## 3. Contribution scope policy

`BehaviorAtom`에 다음을 보존한다.

- `contribution_scope`
- `ownership_ceiling`
- `source_kind`
- `source_binding_status`
- `claim_status`
- `context_only`

보수적 direct 정책:

| contribution | direct | ownership ceiling |
|---|---|---|
| `caused` | actor/criterion/source 조건 충족 시 가능 | `applicant_owned_behavior` |
| `contributed` | 개인 기여 범위에서 가능 | `contribution_only_no_solo` |
| `observed` | 금지 | `observation_only` |
| `unknown` | 금지 / review-required | `unknown_review_required` |

`contributed`는 어떤 경로에서도 `caused`나 solo ownership으로 승격하지 않는다. relation artifact에는 `contribution_scope`, `contribution_ok_for_direct`, `contribution_block_reason`, `relation_without_contribution_gate`, `contribution_blocked_direct`를 남긴다.

## 4. Source-bound atom policy

`build_behavior_atoms()`가 upstream validation 실행 여부를 가정하지 않는다. confirmed qualitative claim도 실제 EvidenceRef가 없거나 source binding이 잘못되면 atom을 만들지 않는다.

새 별도 validator를 복제하지 않고 `profile_schema.validate_ledger()`를 schema-v1 validation shell에 재사용해 다음 canonical 규칙을 그대로 적용한다.

- evidence non-empty
- `source_path` non-empty
- paragraph index 유효
- source/excerpt SHA-256 유효
- confirmed status
- 기존 `claim_submission_issues()` 통과

거부 세부 분류는 `summary.rejection_breakdown`에 기록한다.

- `rejected_no_evidence`
- `rejected_unconfirmed`
- `rejected_metric_only`
- `rejected_submission_issue`
- `rejected_context_only`
- `rejected_invalid_source_binding`

기존 reader 호환을 위해 legacy `code`도 유지한다.

## 5. Safety counter semantics

기존 numeric safety 필드는 유지하고 `counter_status` metadata를 additive하게 추가했다.

- `actually_computed`: 실제 값을 계산함
- `impossible_by_construction`: repaired direct gate가 해당 위반을 direct로 만들 수 없게 차단함
- `not_evaluated`: 향후 필요한 경우 사용할 명시 상태. 계산하지 않은 값을 0으로 표시하지 않는 원칙을 유지함

현재 relation v2에서:

- `direct_run_count`: `actually_computed`
- `false_direct_candidate_count`: `actually_computed`
- context/unconfirmed/research/taxonomy/actor/contribution direct violation: `impossible_by_construction`

`direct_run_count`는 run 단위로 direct 존재 여부를 0/1로 계산하며 real-run aggregator가 합산하도록 설계했다.

## 6. Regression coverage

기존 unit test에 다음을 추가했다.

- first action match/object mismatch → second atom full match
- atom ordering invariance
- caused direct 가능
- observed direct 차단
- unknown direct 차단
- contributed no-solo escalation
- shared actor + observed direct 차단
- confirmed/no-evidence atom 0
- 같은 text의 valid source binding만 atom 생성
- malformed source binding fail-closed
- safety counter status 구분

별도 frozen correctness corpus `tests/fixtures/behavior_ir_correctness_v1.json`에 8 case를 추가했다.

1. `object-second-atom-full-match`
2. `atom-order-invariance`
3. `observed-contribution-block`
4. `unknown-contribution-block`
5. `contributed-no-solo-escalation`
6. `confirmed-no-evidence-no-atom`
7. `valid-evidence-behavior-atom`
8. `safety-counter-status`

기존 18-case 원본 fixture/hash/expectation은 먼저 검증한다. 다만 기존 `context-action-unbound-001`은 source-bound contract 이전에 만들어져 qualitative confirmed claim에 EvidenceRef가 없다. 기대값을 삭제하거나 allowed range를 넓히지 않고, **원본 hash 검증 후 benchmark 실행에만 deterministic EvidenceRef overlay**를 적용하는 legacy adapter를 correctness benchmark에 뒀다. production extraction에는 이 adapter를 사용하지 않는다.

## 7. 실행한 검증

이번 실행에서 실제로 수행한 항목만 기록한다.

| 검증 | 결과 |
|---|---|
| 수정 모듈 Python compile | 통과 |
| source-binding/contribution/object-order/counter 로컬 재구성 unit | **26 passed / 0 failed** |
| correctness frozen 8 case | **8/8 passed** |
| targeted repo pytest 전체 | **NOT_EVALUATED** — 전체 repository checkout 불가 |
| full `pytest -q` | **NOT_EVALUATED** |
| 기존 18-case frozen 전체 | **NOT_EVALUATED** — compatibility runner 작성, 실제 전체 실행은 미완료 |
| combined 26-case benchmark | **NOT_EVALUATED** — 8 correctness case만 실측 8/8 |

로컬 재구성 검증을 repository full pytest 또는 CI green으로 표현하지 않는다.

## 8. 37-run before / after

실제 37-run corpus는 `career_runs/` 아래 git-ignore된 PRIVATE 데이터이며 현재 실행 환경에 존재하지 않았다. 따라서 AFTER 수치를 임의로 채우지 않는다.

| 지표 | BEFORE | AFTER |
|---|---:|---:|
| run_count | 37 | **NOT_EVALUATED** |
| BehaviorAtom atom_count | 947 | **NOT_EVALUATED** |
| rejected_projection_count | 279 | **NOT_EVALUATED** |
| rejected_no_evidence | 미계측 | **NOT_EVALUATED** |
| source-binding으로 제거된 atom | 미계측 | **NOT_EVALUATED** |
| v2 direct | 0 | **NOT_EVALUATED** |
| v2 direct run count | 0 | **NOT_EVALUATED** |
| v2 partial | 1051 | **NOT_EVALUATED** |
| v2 inferred | 19 | **NOT_EVALUATED** |
| `partial_object_unverified` | 68 | **NOT_EVALUATED** |
| object-match fix로 relation 변경 | 미계측 | **NOT_EVALUATED** |
| contribution-blocked direct | 미계측 | **NOT_EVALUATED** |
| A `lexical_high_construct_weak` | 218 | **NOT_EVALUATED** |
| B repaired v2 direct-not-selected | 0 | **NOT_EVALUATED** |
| zero-signal selected | 151 | **NOT_EVALUATED** |
| defensibility-only selected | 151 | **NOT_EVALUATED** |

이를 실행하기 위한 PRIVATE runner는 `career_pipeline/behavior_ir_correctness_audit.py`에 추가했다. baseline과 AFTER를 나란히 출력하고 object-fix, contribution-block, source-binding 제거량을 별도로 집계한다.

## 9. PRIVATE review candidate 재생성

runner는 수정된 v2 기준으로 `career_runs/_audit/behavior_ir_review_candidates.json`을 생성하도록 구현했다. 포함 strata:

- `A_zero_signal`
- `A_positive_signal`
- `context_only`
- `nearest_direct`
- `contribution_blocked`
- `object_match_fixed`
- `source_binding_rejected`
- `actor_blocked`
- `uncovered_core`

각 row는 run identifier, question index, evidence id, atomic claim, source/evidence binding status, contribution scope, actor, BehaviorAtoms, matched/missing criteria, v1 relation, previous v2 relation(존재 시), repaired v2 relation, explanation code, `review_label=null`을 포함한다.

현재 corpus 부재로 **실제 candidate 파일은 재생성하지 못했다.** GPT label을 human review로 채우지 않았으며 `review_label`은 코드상 null로 고정한다.

## 10. 개인정보 보호 경계

- `.gitignore`의 `career_runs/` 경계를 유지한다.
- PRIVATE detailed report와 review candidate는 `career_runs/_audit/`에만 쓴다.
- public doc에는 real-run atomic claim, 회사명, 개인 수치, source excerpt를 넣지 않는다.
- 이번 변경에 PRIVATE 데이터를 commit하지 않는다.

## 11. CI 상태

- 검증 PR: `#4` (`codex/behavior-ir-correctness-repair` → `main`)
- GitHub Actions run: `32031233308` (`career-pipeline-ci`)
- 결과: **`CI_NOT_RUN_BILLING_LOCK`**
- 근거: job `95391489583`은 `steps=[]`, `runner_id=0`으로 실제 test step이 시작되지 않았고 GitHub annotation이 `The job was not started because your account is locked due to a billing issue.`라고 명시한다.

따라서 이 failure를 코드/pytest 실패나 CI green으로 해석하지 않는다.

## 12. 남은 위험과 다음 단계

현재 남은 blocker는 correctness 코드 자체보다 **검증 실행 범위**다.

1. 실제 repository checkout 환경에서 사용자 지정 targeted pytest 실행
2. `pytest -q` full suite 실행
3. 기존 18 + correctness 8 = combined frozen benchmark 실행 및 `15_구성개념불일치벤치마크.json` 재생성
4. PRIVATE `career_runs` 37-run audit 실행
5. AFTER delta와 `partial_object_unverified 68 → ?`, `v2 direct 0 → ?`, `A 218 → ?`, `B 0 → ?` 확정
6. PRIVATE review candidate 재생성 및 strata count 확정
7. 위 검증이 모두 통과한 뒤 `READY_FOR_HUMAN_CALIBRATION` 또는, direct≈0 + missing-required + multi-claim 분산의 정량 근거가 확인되면 `NEED_MULTI_CLAIM_PROOF_RESEARCH` 재판정

이번 단계에서는 multi-claim proof를 구현하지 않는다.
