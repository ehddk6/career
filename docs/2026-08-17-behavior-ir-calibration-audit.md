# Behavior IR Calibration (Shadow-Only) 실측 감사 보고서 (2026-08-17)

- 이전 단계: `docs/2026-08-17-construct-disagreement-real-run-audit.md` (v1 감사, 결론 HOLD)
- 이번 단계: BehaviorAtom typed IR + ConstructCriterion micro-decomposition + relation v2 shadow
- 시작 SHA: `bb8683de493678c15150829c35fc14c604dcca82` (HEAD == origin/main, `git fetch` 후 확인)
- 이 문서는 **개인정보를 포함하지 않는다.** atomic claim 문구가 포함된 상세 감사 리포트와
  human review 후보 세트는 git-ignore된 `career_runs/_audit/`에만 존재한다.
  (`career_runs/`는 `.gitignore`에 포함 — 커밋 대상 아님)

## 결론: HOLD_BEHAVIOR_IR

- 실측 37 run에서 **v2 direct = 0건** (v1 direct = 0건과 동일)
- BehaviorAtom coverage는 유효했지만(원자 947개, atomizable claim rate 0.45),
  **required micro-criterion을 모두 채운 source-backed 증거가 실측에서 0건**
- safety violation은 전부 0건 — authority 경계는 유지됨
- `PROMOTE_BLUEPRINT_SHADOW` 최소 조건(real v2 direct > 0, 다수 run, real B 발생) 미충족
- `PROMOTE_VETO_ONLY`는 human-reviewed precision 표본이 아직 없어(후보 338건 생성, review_label 전부 null)
  보류 — 이번 단계는 판정만 내리고 Blueprint production integration을 구현하지 않는다.

## 1. 검증 결과 요약

| 항목 | 결과 |
|---|---|
| 전체 pytest | **777 passed / 0 failed / 7 skipped** |
| 동결 벤치마크 (18 case = 기존 10 + 신규 8) | **18/18 통과, 전 rate 1.0** |
| 기존 frozen case 기대값 약화 | 없음 (10개 case 원문 유지) |
| Golden Path 회귀 | 없음 (`test_golden_path`, `test_evidence_to_signal` green) |
| GitHub Actions | **CI_NOT_RUN_BILLING_LOCK** — 계정 billing 잠금으로 러너 미할당, 0-step 실패 |
| 생산 선택 변경 | 없음 (Phase A additive fields만 추가, 선택·순서·점수 불변) |
| shadow decision_effect | `none_shadow_mode` 유지 (writer/judge/interview/gate 영향 없음) |

## 2. 문제 정의와 이전 direct=0 원인

이전 v1 감사에서: A(`lexical_high_construct_weak`) = 218건이지만 B(`construct_direct_not_selected`) = 0,
v1 direct link = 0건. 단순 direct threshold 문제가 아니라 **"확정 ProfileClaim의 원자 단위와
직무 construct를 증명하는 observable behavior의 단위가 맞지 않는다"**는 가설을 세웠다.

이번 단계는 다음 구조를 **shadow mode로만** 구현·검증했다:

```
Source Evidence → Verified Claim → BehaviorAtom → ConstructCriterion → Construct relation v2
```

## 3. Phase A — Evidence Portfolio score decomposition

- `evidence_portfolio.py`에 순수 헬퍼 `score_candidate()`를 두고 기존 공식을 그대로 유지:
  `score = weighted + qo*1.1 + defensibility*0.75 - risk*0.8 - usage*0.35`
- 선택된 row에 additive 진단 필드 추가 (선택·순서·rounding·SCHEMA_VERSION 불변):
  `signal_relevance_contribution / question_overlap_contribution / defensibility_contribution /
  risk_penalty / reuse_penalty / covered_signal_count / covered_signal_ids /
  zero_signal_selection / positive_relevance_contribution / selected_due_to_defensibility_only`
- `selected_due_to_defensibility_only` = posting/question relevance contribution이 0인데
  defensibility 때문에 score > 0이 되어 선택된 경우
- invariant 테스트: sum-of-parts ≡ final (≤0.003), 선택 identity snapshot,
  정렬 키 (-score, evidence_id) 순서 유지 — `tests/test_evidence_portfolio_decomposition.py`

### 실측 score decomposition (A 218건)

| bucket | count |
|---|---|
| positive_signal_relevance | 79 |
| positive_question_overlap_only | 1 |
| defensibility_only (zero signal + zero question overlap) | 138 |
| reuse_or_other | 0 |

- **선택된 evidence 중 zero-signal = defensibility-only = 151건** — 선택된 근거의 상당수가
  신호·문항 관련성 없이 방어가능성 수치만으로 선택됨 (138건은 A 케이스, 나머지 13건은 A가 아닌 문항)
- 이 수치는 다음 단계에서 Evidence Portfolio candidate floor 검토의 근거가 되지만,
  **이번 작업에서는 생산 selection rule을 바꾸지 않았다.**

## 4. Phase B — BehaviorAtom typed IR (`career_pipeline/behavior_ir.py`)

- deterministic, fail-closed, **LLM 미사용**. ~34개 한국어 행동 동사 어휘
  (대조/비교/검토/점검/심사/확인/발견/판별/파악/분류/구분/선별/분석/진단/취합/안내/설명/상담/소명/
  협의/조정/연계/보고/승인요청/요청/기록/작성/정리/수정/보완/개선/관리/처리/모니터링)
- 한국어 활용 어미 정규화 (했다/했습니다/하여/해서/하며/드렸다 등) + 단어 경계 lookahead
  (`관리자` false positive 차단). 불확실하면 잘못 normalize하지 않고 미추출.
- **입력 제한** — BehaviorAtom은 새로운 applicant fact를 생성하지 않는다:
  - A. confirmed claim의 `normalized_value`에서 결정적 직접 추출 (`atomic_claim_direct` / `lossless_claim_projection`)
  - B. 동일 experience의 actions와 대조 확인된 행동 (`source_bound_action`)
- **금지**: unconfirmed claim → atom, metric/% 결과 claim → atom, actions 문구만 → atom,
  research/company fact → applicant atom, context-only 승격, LLM 창작
- 거부 진단 코드: `unconfirmed_claim`, `claim_submission_issue`, `metric_claim_no_behavior`,
  `context_only_action_no_claim`

## 5. Phase C — ConstructCriterion micro-decomposition (`career_pipeline/construct_criteria.py`)

- construct 하나당 긴 indicator 하나를 7개 family × micro-criterion으로 분해
  (`criterion_application` 4, `analytical_diagnosis` 3, `stakeholder_explanation` 3,
  `coordination` 3, `boundary_escalation` 3, `documentation` 2, `execution_control` 3)
- `required_for_direct` 구분 — DIRECT는 required criterion 전부 충족 필요
- **source_basis 경계 유지**: target construct → `target`, taxonomy prior construct →
  `taxonomy_prior` (prior criterion은 어떤 경우에도 target DIRECT 불가)
- v1 스키마(`job_analysis_schema.py`, `construct_portfolio.py`)는 수정하지 않아
  `graph_id`/matrix/cache semantics가 byte-identical 유지. 기준은 새 shadow artifact
  `06_구성개념기준.json`으로 기록.

## 6. Phase D — relation v2 shadow (`career_pipeline/construct_relation_v2.py`)

- v1 relation을 삭제하지 않고 병렬 shadow로 추가. exact-token score는 DIRECT 판정에 사용하지 않고
  INFERRED 후보(retrieval)에만 사용.
- DIRECT 조건: factual BehaviorAtom 존재 + actor scope 호환 + required criterion 전부
  action-match 및 object-verified. PARTIAL은 일부 criterion만 충족. INFERRED는
  source-backed proof 부족. NONE은 관계 없음.
- deterministic explanation codes: `direct_all_required_criteria`,
  `partial_missing_required`, `partial_object_unverified`, `direct_blocked_actor_scope`,
  `inferred_no_atom`, `no_criteria_no_direct`, `prior_only_criterion_no_direct`
- safety counters 6종은 구조적으로 0 (아래 실측 확인)

## 7. Frozen benchmark 확장

- 기존 `construct_disagreement_v1.json` 10개 case **원문 유지, 기대값 약화 없음**
- 신규 8 case 추가 (canonical `fixture_sha256` 계산, 합계 18 case):
  `atomic_action_direct_v2`, `metric_only_no_behavior`, `context_action_unbound`,
  `source_bound_action_direct`, `korean_inflection_invariance`, `wrong_actor`,
  `prior_only_criterion`, `partial_criterion`
- `15_구성개념불일치벤치마크.json` 재생성: **18/18 통과**
  - direct_precision_guard_rate 1.0, disagreement_detection_rate 1.0,
    taxonomy_boundary_rate 1.0, benign_relation_invariance_rate 1.0,
    v2_direct_precision_rate 1.0, v2_direct_recall_rate 1.0

## 8. Real-run v1 vs v2 재감사 (37 run)

| 지표 | v1 | v2 |
|---|---|---|
| direct | 0 | **0** |
| partial | 165 | 1051 |
| inferred | 304 | 19 |
| context-only / none | 264 | 1581 |
| direct 발생 run | 0 | 0 |

- v1→v2 direct recovery / v1 partial→v2 direct / v1 inferred→v2 direct: 전부 **0**
- real B under v2 (v2 direct인데 lexical portfolio 미선택): **0**

### BehaviorAtom 실측 coverage

| 지표 | 값 |
|---|---|
| atom_count | 947 |
| behavior_atom_run_count | 37 (전 run) |
| rejected_projection_count | 279 |
| atomizable_claim_count | 359 |
| confirmed_claim_count | 797 |
| **atomizable_claim_rate** | **0.45** |
| source_bound_action_atom_count | 843 |

### safety violations (실측)

| counter | 값 |
|---|---|
| false_direct_candidate_count | 0 |
| context_only_direct_violation_count | 0 |
| unconfirmed_direct_violation_count | 0 |
| research_as_applicant_violation_count | 0 |
| taxonomy_escalation_violation_count | 0 |
| actor_scope_violation_count | 0 |

## 9. 왜 real-run direct가 안전하게 만들어지지 않는가 — source granularity 진단

v2 relation 2,651건의 explanation code 분포:

| code | count | 의미 |
|---|---|---|
| no_criteria_no_direct | 1600 | 해당 construct에 family micro-criteria가 없음 (generic/explicit construct) |
| partial_missing_required | 951 | required criterion 중 일부 결손 |
| partial_object_unverified | 68 | action은 match되나 object class 미검증 |
| direct_blocked_actor_scope | 32 | 팀/타인 주어 행동 |

가장 많이 결손된 required criterion (partial_missing_required 내):

- `crit_execution_control_inspect_status_or_deadline` 308
- `crit_execution_control_manage_next_action` 289
- `crit_execution_control_identify_missing_or_delayed_work` 288
- `crit_criterion_application_compare_against_rule_or_source` 130
- `crit_criterion_application_preserve_decision_basis` 122
- `crit_analytical_diagnosis_explain_basis` 121
- `crit_analytical_diagnosis_compare_or_segment_information` 116
- `crit_criterion_application_classify_exception` 114
- `crit_stakeholder_explanation_identify_recipient_need` 108
- `crit_analytical_diagnosis_identify_pattern_or_cause` 107

**정량 진단 (threshold lowering 아님):**

1. **claim 원자 단위 vs criterion 단위 불일치가 확인됨.** 실측 확정 claim의 55%는
   atom화 불가(metric-only, unconfirmed, submission-unsafe). atom화된 claim도
   평균적으로 단일 동사 1~2개를 담아, family당 required criterion 2~3개를
   **한 claim 안에서** 모두 채우는 경우가 0건.
2. **criterion 1,600건은 아예 criteria가 없는 construct** (7개 family 외 generic/explicit
   construct). 이 construct는 구조적으로 v2 direct가 불가능.
3. **actor/object granularity**: 32건은 팀 주어로 차단, 68건은 object class 미검증 —
   둘 다 보수적 fail-closed 방향이며 안전성은 유지됨.
4. 결과: "confirmed + source-backed + 모든 required criterion 충족"의 교집합이
   현재 claim 원자 단위에서는 실측 0건. 이는 **threshold 문제가 아니라
   source granularity 문제**라는 가설을 지지한다. 단순 threshold lowering으로는
   해결되지 않으며, 다음 단계 후보는 claim 단위가 아닌 (a) multi-claim 합성 증거,
   (b) required criterion 재캘리브레이션, (c) criterion object 검증의 source 확장이다.

## 10. A/B disagreement 변화

- A (`lexical_high_construct_weak`): **218건 유지** (변화 없음 — 생산 selection 불변 확인)
- B (`construct_direct_not_selected`): **0건 유지**
- v2 렌즈에서도 실측 direct가 0이므로 B는 여전히 재현되지 않음 — synthetic reproduction으로만
  존재 (신규 8 case 중 `atomic_action_direct_v2`, `source_bound_action_direct` 등)

## 11. Human calibration (PRIVATE)

- PRIVATE 후보 세트: `career_runs/_audit/behavior_ir_review_candidates.json` (git-ignore, 커밋 금지)
- **338건, 층화 추출**:
  - A_signal 71 / A_zero_signal_partial 76 / A_zero_signal_no_atom 61
  - rejected_context_only 66 / v2_nearest_direct 54 / v2_actor_scope 6 / uncovered_core_construct 4
- 각 후보: anonymized run id, question index, evidence id, atomic claim text, source binding status,
  v1 relation, BehaviorAtom projection, matched/missing criteria, proposed v2 relation, `review_label: null`
- **아직 human review 미수행** (review_label 전부 null). 이 문서의 어떤 "N건"도
  사람 검증 완료로 표현하지 않는다. deterministic classification과 human review sample은 분리.
- PRIVATE 상세 감사: `career_runs/_audit/2026-08-17-real-run-disagreement-audit.detailed.json` + `.md`

## 12. 개인정보 보호 경계

- `career_runs/` 전체가 `.gitignore`에 포함되어 있어 real-run 상세 데이터는 커밋 불가.
- public repo에는 집계와 synthetic reproduction만 기록 (본 문서, 동결 벤치마크 fixture,
  벤치마크 리포트). real B가 나오면 동일 구조를 synthetic fixture로 재현해 frozen corpus에 추가.

## 13. 최종 판정: HOLD_BEHAVIOR_IR

근거:

1. 실측 v2 direct = 0건, direct run = 0 — `PROMOTE_BLUEPRINT_SHADOW` 최소 조건 미충족.
   (human-reviewed direct 후보 ≥ 30, direct run ≥ 10, precision ≥ 0.90 목표는 표본 자체가 0)
2. real B (construct-direct / lexical-unselected) 실측 0건 — selection 대체 근거 부족.
3. authority 경계는 전부 안전 (safety violations 0) — 다만 이는 direct가 없어서이기도 하며,
   v2 direct precision을 평가할 실측 표본이 없다.
4. `PROMOTE_VETO_ONLY`는 "v2가 weak evidence를 높은 precision으로 식별"을 요구하나
   human-reviewed precision 표본이 아직 없어 보류. 후보 338건에 대한 human review가
   다음 단계의 선행 조건.
5. 단순 threshold lowering으로 direct를 만들지 않았고, 부족한 표본을 억지로 채우지 않았다.
6. direct=0의 원인은 source granularity 진단으로 정량 제시됨 (섹션 9) —
   acceptance criterion D-2 충족 (실측 direct를 안전하게 만들 수 없는 이유의 quantitative diagnosis).

## 14. 다음 단계 (production integration 아님)

1. PRIVATE 338건 human review → direct/partial 정밀도 라벨 수집
2. multi-claim 합성 증거(같은 experience 내 보완 claim 결합)로 required criterion 충족 실험
3. object-class 검증의 source 확장 (claim 내 evidence binding 범위) 검토
4. required criterion 재캘리브레이션 후보 (가장 결손 많은 execution_control / analytical_diagnosis 우선)
5. real B가 관측되면 synthetic fixture로 frozen corpus 추가

## 15. 남은 위험

- 7개 family 외 construct(no_criteria 1,600건)는 현재 구조로 v2 평가 불가 — family 커버리지 확장 필요
- atomizable claim rate 0.45는 confirmed claim의 절반 이상이 atom화 불가 — 경험원장 작성 단계의
  claim 원자 단위 개선이 선행되어야 함
- BehaviorAtom 어휘는 34개 동사로 제한 — 어휘 밖 행동은 unknown으로 남아 coverage 저하
- human review 미수행 상태에서 v2 direct/partial precision 미평가 — 판정에 이 불확실성을 반영
- CI는 billing lock으로 미실행 (`CI_NOT_RUN_BILLING_LOCK`) — unlock 후 반드시 재실행 필요
