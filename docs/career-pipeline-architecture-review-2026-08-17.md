# Career Pipeline Architecture Re-evaluation — 2026-08-17

## 결론

이 프로젝트의 핵심 문제는 더 좋은 프롬프트를 만드는 것이 아니다. 현재 시스템은 이미 경험 원장, 공고, 회사조사, 논증검색, 검증, 지원 실행 안전장치를 갖고 있다. 남은 병목은 **서로 다른 지식의 권한과 상태를 한 방향으로 흐르게 하고, 사용자가 우회할 수 없는 golden path를 만드는 것**이다.

따라서 Career Pipeline을 다음과 같은 compiler + defense system으로 정의한다.

```text
raw evidence / official sources
        ↓
AUTHORITY LAYER
confirmed applicant claims + confirmed official research
        ↓
PLANNING LAYER
eligibility + matching + research requirements + narrative blueprint
        ↓
SEARCH LAYER
argument routes + portfolio selection + strategy priors
        ↓
REALIZATION LAYER
final prose
        ↓
DEFENSE LAYER
claim-defense graph + structured-adaptive mock interview
        ↓
EXECUTION LAYER
package / review / authorization / safe form execution
```

각 layer는 앞 layer보다 factual authority가 커질 수 없다. downstream 모델은 새 사실을 만들 권한이 없고, 오직 선택·구조화·표현·검증만 할 수 있다.

## 현재 잘 된 부분

### 1. 지원자 사실 권한이 분리되어 있다

`02_확정경험원장.json`이 개인 사실의 단일 권한 원천이고, metric verification과 contribution boundary를 둔 것은 이 프로젝트의 가장 중요한 기반이다.

### 2. 회사조사가 단순 검색요약을 넘어갔다

Research Intelligence는 문항 요구 → argument slot → 공식 source registry → claim ingestion → freshness/conflict → coverage → blueprint routing으로 발전했다. 회사 사실이 단순 prompt context가 아니라 추적 가능한 authority claim이 되었다.

### 3. 자기소개서가 prose-first에서 argument-search로 이동했다

Narrative Compiler와 Deep Writer는 경험·공식근거로 가능한 논증 route를 먼저 탐색하고, semantic judges/Pareto/portfolio selection 후 prose를 만든다. Strategy Prior는 사실 권한을 갖지 않으므로 유튜브·기존 전략·선호학습이 factual contamination을 일으키지 않게 분리되어 있다.

### 4. 실행 자동화가 안전 경계를 가진다

지원서 package, form discovery/mapping, review, authorization, CAPTCHA/MFA 차단 등은 '자동화 가능성'과 '실제 제출 권한'을 분리한다. 이 원칙은 유지해야 한다.

## 재평가에서 드러난 구조적 문제

### P0-1. Golden path가 아직 코드 레벨에서 하나가 아니다

`prepare`, Research Intelligence, `integrated_writer`, `finalize`, 기존 interview pack, 새 interview intelligence, `audit`가 논리적으로 연결되어 있지만 하나의 단일 orchestration contract로 강제되지는 않는다. 사용자가 중간 모듈을 직접 우회하면 최신 계층을 건너뛸 수 있다.

**전략:** 다음 단계에서 `career_pipeline run` 또는 동등한 orchestration command를 만들어 최신 경로를 기본값으로 고정한다. 레거시 직접 실행은 compatibility path로 명시한다.

### P0-2. 기존 면접팩은 문서 검증에는 강하지만 순차적 진단 상태가 없다

`08_면접대비팩.md`와 `validate_interview_pack()`은 형식·길이·근거 연결을 검사한다. 그러나 다음 질문 선택, 약점 상태, claim-risk priority, cross-session learning이 없다.

**전략:** `career_pipeline.interview_intelligence`를 별도 DEFENSE LAYER로 추가한다. 기존 면접팩은 사람이 읽는 compatibility artifact로 유지한다.

### P0-3. Legacy finalize의 interview strictness 계약을 별도 점검해야 한다

코드상 `validate_interview_pack()`은 `strict=True`일 때 30/60/90 길이·단계적 구체화·꼬리/압박 답변·근거 연결을 더 깊게 검사할 수 있다. 현재 finalize 호출부가 strict-quality 분기 안에 있어도 `strict=True`를 명시하지 않는 경로가 존재한다. output contract가 기대하는 깊은 검증과 실제 호출 강도가 항상 동일한지 회귀 테스트가 필요하다.

**전략:** golden-path hardening에서 이 호출 계약을 명시적 테스트로 고정하고, 기존 산출물 compatibility를 확인한 뒤 strict mode를 실제 enforce한다.

### P0-4. 최종 자기소개서와 면접팩 사이에 stale-content 위험이 남는다

현재 rigorous selection 전 면접팩이 준비될 수 있고, 이후 `_link_final_claims_to_interview_pack()`가 최종 claim/reference를 다시 연결한다. ID linkage는 보정되지만 이미 작성된 면접 답변 문장 자체가 최종 선택 논증과 완전히 동일하다는 보장은 별도 문제다.

**전략:** 면접 intelligence는 `draft_final.json`을 우선 읽고 최종 주장으로 claim-defense graph를 다시 컴파일한다. 향후 legacy 면접팩도 최종 selection 이후 regenerate 또는 semantic alignment gate를 거치게 한다.

### P1-1. 품질 평가는 아직 empirical benchmark보다 휴리스틱 비중이 높다

자소서 rubric, Deep Writer judges, interview dimensions는 명시적이고 유용하지만 실제 사용자 선호·서류 결과·모의면접 개선과의 calibration corpus가 부족하다.

**전략:** representative benchmark를 독립 제품으로 만든다.

- 과거 실제 지원 문항 + 확정 원장 + 당시 회사자료
- V4/V5/V6 및 외부 강한 모델의 blind A/B
- 사용자 pairwise preference
- deterministic factual error rate
- 회사특이성/방어가능성/문항충실도
- 실제 결과는 verified outcome metadata로만 사용하고 합격 확률로 역산하지 않음
- 면접은 동일 question bank 전후 세션의 weak-dimension 변화량을 측정

### P1-2. Model judge는 factual authority가 아니며 provider diversity도 아직 제한적이다

현재 Deep Writer/Interview semantic judge는 모델 평가를 사용하지만 모델이 스스로 만든 점수는 ground truth가 아니다. 또한 실행 adapter가 특정 runner 계약에 묶여 있다.

**전략:** provider-neutral judge adapter + permutation/role balancing + deterministic hard-cap을 유지하고, human/user preference를 calibration source로 우선한다.

### P1-3. 기관별 실제 면접 형식은 아직 일반 구조에 압축되어 있다

행동면접, 경험면접, 직무 상황질문까지는 일반 엔진으로 처리할 수 있지만 PT, 토론/토의, 세일즈 role-play, 금융시장 case, 공공기관 정책 제안은 다른 task state와 평가축이 필요하다.

**전략:** 공고/후기에서 확인된 면접 유형만 `InterviewTaskModel`로 등록하고 type-specific engine을 추가한다. 확인되지 않은 면접 유형은 발명하지 않는다.

## 새 면접 계층의 명확한 역할

새 `Structured-Adaptive Interview Intelligence`는 면접을 다음 문제로 본다.

> 이미 제출한 주장 중 어떤 부분이 사실·기여·인과·판단·직무이해 측면에서 가장 불확실하며, 다음 질문 한 개가 그 불확실성을 가장 많이 줄일 수 있는가?

이때 자유생성 질문보다 다음 두 단계가 우선한다.

1. **standardized backbone:** 모든 세션에서 동일한 1분 소개 + 문항별 core defense
2. **adaptive probe:** weak dimension, claim risk, uncovered node/dimension, repetition cost를 이용해 제한된 질문은행에서 선택

이는 structured interview의 비교가능성을 보존하면서 adaptive interviewing의 효율을 취하는 구조다.

## 권한 계층 재정의

| 계층 | 예 | factual authority |
|---|---|---|
| Authority | confirmed experience claim, confirmed official research | YES |
| Planning | match, research requirement, blueprint | NO — authority를 선택/배치 |
| Strategy | YouTube frame, legacy strategy, preference | NO |
| Generation | Deep Writer prose | NO |
| Diagnostic | interview semantic judge, quality rubric | NO |
| Outcome | verified result/feedback metadata | NO — calibration/diagnosis only |
| Execution | package/form authorization | NO — 승인된 artifact를 전달 |

이 표가 앞으로 모든 기능 추가의 기준이다. 새 기능이 factual authority를 암묵적으로 늘리면 설계 오류다.

## 우선순위 로드맵

### P0 — 지금

- Structured-Adaptive Interview Intelligence 추가
- final-draft claim-defense graph
- standardized core + adaptive probe bank
- question-scoped metric/fact boundary
- deterministic hard gates > semantic judges
- aggregate-only cross-session weakness profile
- docs/tests/agent default workflow 반영

### P0 — 다음 hardening

- golden-path orchestration command
- legacy interview strict validation call contract 회귀테스트/강제
- final selection 후 legacy interview pack content alignment/regeneration
- 공통 deterministic duplicate/contamination helper로 우회 경로 제거

### P1

- real historical application benchmark harness
- pairwise preference + outcome-calibrated but non-probabilistic evaluation
- provider-neutral multi-model judge adapters
- interview improvement benchmark

### P2

- verified interview-format discovery
- PT/case/discussion engines
- 음성/시간/prosody 등 multimodal practice signal (privacy boundary 포함)

## 성공 기준

'기능 수'가 아니라 다음으로 측정한다.

1. unsupported fact/metric이 downstream에서 살아남는 비율 → 0에 수렴
2. 동일 질문에서 모델을 바꿔도 authority refs가 변하지 않음
3. 사용자 blind preference 승률 개선
4. 회사·직무 특이성 증가와 factual error rate 동시 유지
5. 면접 세션 반복 시 weak-dimension EMA 개선
6. 같은 claim에 대한 답변 간 role/metric/causality contradiction 감소
7. golden path 우회율 감소

이 프로젝트의 다음 혁신은 더 큰 prompt가 아니라 **권한 보존형 compiler, argument search, sequential defense, empirical feedback loop를 하나의 폐쇄루프로 만드는 것**이다.
