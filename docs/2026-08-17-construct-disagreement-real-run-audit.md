# 구성개념(Construct) 불일치 실측 감사 보고서 (2026-08-17)

- 감사 대상: `career_runs/` 내 4개 입력(00_채용공고분석, 02_확정경험원장, 04_공식근거, run.json)을 갖춘 실제 run 37개
- 감사 도구: `career_pipeline/real_run_disagreement_audit.py` (deterministic, LLM 미사용, in-memory shadow 재계산)
- 이 문서는 개인정보를 포함하지 않는다. atomic claim 문구가 포함된 상세 리포트는 git-ignore된
  `career_runs/_audit/`에만 존재한다.

## 결론: HOLD (blueprint 승격 보류)

실측 데이터에서 shadow 구성개념 매퍼는 **거부(veto) 렌즈로는 유효한 신호를 제공**했지만,
**선택(selection) 렌즈로는 아직 검증되지 않았다.** B 패턴(construct_direct_not_selected)이
실측 run에서 단 한 건도 재현되지 않았고(직접 연결 0건), A 패턴의 37%는 렌즈 축이 다른
미해결 케이스로 남는다. 승격의 핵심 근거인 "direct 구성개념 근거 → 증거 선택" 루프가
실측 데이터에서 한 번도 발화하지 않았으므로 blueprint 승격은 시기상조다.

## 1. 검증 결과

| 항목 | 결과 |
|---|---|
| 전체 pytest | **745 passed / 0 failed / 7 skipped** |
| 동결 벤치마크 (10 case) | **10/10 통과, 전 rate 1.0** |
| Golden Path 회귀 | 없음 (`test_golden_path`, `test_evidence_to_signal` green; 생산 writer 경로 변경 없음) |
| GitHub Actions | **실행 불가** — 계정 billing 잠금으로 모든 워크플로우가 0-step 실패 (러너 미할당) |
| shadow decision_effect | `none_shadow_mode` 유지 (생산 결정 영향 없음) |

### 테스트 수리에 대한 공개
- `tests/test_deep_writer.py`, `tests/test_preference_writer.py`의 3개 선존재 실패
  (bundle 커밋 4개와 무관한 커밋 `bdfe019`/`696e745`/`005552b`/`d059bb4`에서 마지막 수정)를
  수리했다: 경험원장 계약(schema_version 2 + experiences 배열 + stable claim_id + evidence
  참조)을 테스트 픽스처가 지키지 않던 결함. 픽스처 계약 정렬 수정이며 생산 코드 변경 없음.

## 2. 실측 감사 방법

각 run에 대해 in-memory로 `build_job_analysis_graph` → `build_evidence_portfolio` →
`build_construct_portfolio`를 재계산하고 (기존 shadow 산출물 파일을 덮어쓰지 않음):

- **A (lexical_high_construct_weak)**: lexical portfolio가 선택했지만 core construct에
  direct/partial 연결이 없는 applicant evidence
- **B (construct_direct_not_selected)**: 문항 관련 core construct에 direct 연결이 있는데
  선택되지 않은 evidence
- 분류 규칙 (결정적, 스크립트 docstring에 문서화):
  - A: atomic core 연결 존재 → `insufficient`(임계값 민감도) / context-only core →
    `construct_mapper_preferred` / 신호 커버 1건 이상 → `insufficient`(축 불일치) /
    그 외 → `construct_mapper_preferred`
  - B: direct 후보 점수가 선택된 applicant 최고 점수 초과, 또는 문항에 applicant evidence
    미선택, 또는 atomic 토큰이 문항 프롬프트와 2개 이상 겹침 → `construct_mapper_preferred`,
    그 외 → `lexical_mapper_preferred`

## 3. 실측 결과

| 지표 | 값 |
|---|---|
| real_run_count | 37 |
| lexical_high_construct_weak_count (A) | **218** (37개 run 전부에서 발생) |
| construct_direct_not_selected_count (B) | **0** |
| reviewed_disagreement_count | 218 |
| construct_mapper_preferred_count | 138 (63%) |
| lexical_mapper_preferred_count | 0 |
| unresolved_count (insufficient) | 80 (37%) |
| false_direct_count | 0 |
| context_only_direct_violation_count | 0 |
| taxonomy_escalation_violation_count | 0 |
| generic_direct_candidate_count | 0 |
| uncovered core construct 발생 run | 4 (총 4개 construct) |
| 링크 분포 | direct 0 / partial 165 / inferred 304 / context-only 264 |

### 핵심 실측 발견

1. **A 패턴은 강하게 재현된다.** 218건 중 138건은 선택된 evidence가 core construct
   근거가 전혀 없으면서 **포스팅 신호 커버도 0건**인 순수 방어가능성(verification/risk)
   수치에 의한 선택이었다. 예: 문항 프롬프트가 갈등·배려에 대한 것인데 마케팅 채널별
   모집 전략 claim이 선택됨, 순수 수치 claim("70%")만 선택됨. 이 경우 구성개념 렌즈가
   더 합리적이다 (샘플 8건 육안 검토, 상세는 로컬 리포트).
2. **B 패턴은 재현되지 않는다.** 실측 run에서 direct 관계가 0건이다. 구성개념 매퍼는
   실측 데이터에서 어떤 applicant claim도 "직접 지지"로 판정하지 않았으므로 "direct인데
   선택 안 됨" 사례가 존재할 수 없다. 동결 벤치마크의 direct 케이스(safe-paraphrase-001,
   direct-but-unselected-001)는 합성 입력에서만 발화한다.
3. **미해결 80건은 축 불일치다.** evidence가 일부 포스팅 신호를 커버하지만 core
   construct(평균 1.89개/run, 인디케이터 1개/construct)를 지지하지 못하는 경우로,
   두 렌즈가 서로 다른 축을 보며 어느 쪽이 더 합리적인지 사실만으로 판정 불가.
4. **권한 경계는 위반이 없었다.** taxonomy prior는 실측 run에서 target 상태 또는 core로
   승격된 사례 0건, direct에 context-only가 쓰인 사례 0건, false-direct 0건 — 모두
   구성(construction) 수준에서 강제되며 실측으로도 확인됨.

## 4. 승격 조건 평가

| # | 조건 | 판정 |
|---|---|---|
| 1 | 전체 pytest 통과 | 통과 (로컬 745/745; CI는 billing 잠금으로 미실행) |
| 2 | Golden Path 회귀 없음 | 통과 |
| 3 | 동결 벤치마크 전부 통과 | 통과 (8→10 case 확장 후 10/10) |
| 4 | 실측 run에서 A/B가 의미 있게 재현 | **부분 통과** (A 218건 재현, B 0건) |
| 5 | 검토에서 construct 매퍼가 더 합리적인 사례 확인 | 통과 (138건, 샘플 육안 검토) |
| 6 | 허용 불가 수준의 false-direct 없음 | 통과 (0건, 구성상 불가) |
| 7 | taxonomy/company/applicant 권한 경계 위반 없음 | 통과 (0건) |

조건 4가 부분 통과이므로 **HOLD**. 보완 기준: (a) 실측 데이터에서 direct 관계가 재현되도록
인디케이터/임계값 보정 후 재감사, 또는 (b) blueprint 승격의 역할을 "거부 렌즈"로 한정하는
문서상 명시.

## 5. 동결 코퍼스 확장 (실측 패턴의 합성 재현)

실측 패턴을 개인정보 없이 재현하는 동결 케이스 2건을 추가했다 (총 8→10):

- `metric-only-claim-selected-001` (category: `metric_only_irrelevant`): bare metric
  claim이 신호 커버 없이 lexical portfolio에 선택되고 construct 매퍼는 none으로
  판정하며 A 불일치가 탐지되는지 검증
- `uncovered-core-coverage-gap-001` (category: `uncovered_core_gap`): 한 core construct는
  cover되고 다른 core construct는 uncovered로 보고되는지 검증
  (`uncovered_core_construct_ids_contains` 체크를 벤치마크에 신설 — 기대를 강화하는 추가)

## 6. 남은 리스크

- 실측 데이터에서 direct 관계 미발화: 구성개념 매퍼의 핵심 가치("직접 지지 증거 선택")가
  실측에서 미검증. 1개 인디케이터/construct + 임계값 0.34가 실측 claim 길이와 만나지 않음.
- 80건 미해결(37%): 렌즈 축 불일치의 판정 기준 부재. 문서 기준(신호 커버 우선 vs core
  construct 지지 우선)이 정해지기 전까지는 shadow 유지가 안전.
- CI 미실행: billing 잠금 해제 후 워크플로우 1회 실행 필요.
- 테스트 수리 3건은 선존재 결함 수리이나, 리뷰어가 픽스처 계약 변경을 확인할 필요가 있음.

## 7. 커밋 정보

- HEAD: `25189b3` (실측 감사 이전 상태)
- 본 감사 커밋: 다음 커밋 SHA (push 후 기록)
- 포함: `career_pipeline/real_run_disagreement_audit.py` (신규),
  `career_pipeline/construct_benchmark.py` (uncovered 체크 추가),
  `tests/fixtures/construct_disagreement_v1.json` (케이스 2건 추가),
  `15_구성개념불일치벤치마크.json` (재생성),
  `tests/test_deep_writer.py`, `tests/test_preference_writer.py` (픽스처 계약 수리)
- 제외: `plan/` (관례상 untracked), `career_runs/_audit/` (git-ignore, 개인정보 포함)