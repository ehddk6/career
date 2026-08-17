# Structured-Adaptive Interview Intelligence

## 문제 재정의

기존 `08_면접대비팩.md`는 1분 자기소개, 30·60·90초 답변, 꼬리·압박 질문, 근거 연결을 제공하고 `validate_interview_pack()`은 형식·수치·자기소개서 연결을 검사한다. 이것은 좋은 **practice artifact + validator**지만, 면접을 순차적 진단 문제로 모델링하지 않는다.

새 엔진의 목표는 질문을 많이 만드는 것이 아니다. 최종 제출본이 만든 주장을 실제 면접에서 방어할 수 있는지, 어느 역량과 주장 경계가 약한지, 다음 질문 한 개가 무엇을 가장 잘 밝힐지를 결정하는 것이다.

```text
final application assertions
+ confirmed experience ledger
+ verified official research
+ application questions / target role
        ↓
Claim-Defense Graph
        ↓
Standardized Core Backbone
        ↓
Deterministic Fact / Scope Gates
        ↓
Optional Multi-role Semantic Judges
        ↓
Weakness State
        ↓
Expected-Diagnostic-Utility Probe Selection
        ↓
next question
```

## 연구에서 채택한 원칙

### 1. 표준화된 코어를 버리지 않는다

Campion et al.의 구조화 면접 연구는 직무분석 기반 질문, 동일 질문, 행동기반 평가척도, 일관된 시행을 핵심 구조 요소로 둔다. Campion, Palmer & Campion의 구조화 면접 리뷰는 질문 내용과 평가 과정 양쪽에서 구조화 요소를 분리해 다룬다. Levashina et al.의 리뷰 역시 질문 형식, 평가척도, probing/follow-up을 별도의 설계 문제로 본다.

따라서 매 세션은 `core:intro:60` → `core:q1` → `core:q2` ... 순서의 고정 코어를 먼저 수행한다. 적응형 질문은 이 기준점을 대체하지 않는다.

### 2. 과거행동 질문과 상황질문을 목적별로 분리한다

과거행동 질문은 제출된 경험의 실제 행동·기여·결과를 검증하는 데 쓰고, 상황질문은 공식 직무 근거가 있는 업무에서 판단 순서·권한·보고/인계 기준을 확인하는 데 쓴다. 둘을 한 점수로 섞지 않는다.

### 3. 점수는 행동 앵커를 가진 차원별 진단으로 제한한다

총점 하나를 생성하지 않는다. 다음 차원을 0~4 행동 앵커로 분리한다.

- directness
- evidence_defensibility
- ownership_precision
- causal_precision
- decision_visibility
- specificity
- job_understanding
- organization_understanding
- pressure_resilience
- reflection_quality
- communication_density

0/2/4에는 서술형 앵커가 있고 1/3은 중간 판단이다. semantic judge를 쓰더라도 deterministic fact gate가 우선한다.

### 4. 적응형 follow-up은 자유 생성이 아니라 제한된 질문은행에서 선택한다

최근 adaptive interviewing 연구는 고정 topic coverage와 emergent follow-up 사이의 trade-off를 명시적으로 다루고 있다. 그러나 현재 채용선발의 예측타당도로 직접 일반화할 근거는 부족하다. 따라서 본 구현은 LLM이 무제한 질문을 즉석 생성하게 하지 않는다.

먼저 근거에서 다음 probe family를 결정론적으로 생성한다.

- ownership_probe
- decision_probe
- counterfactual_probe
- metric_probe
- causality_probe
- organization_probe
- situational_job_probe
- fit_counterfactual_probe

그 뒤 질문 선택만 다음 휴리스틱으로 적응시킨다.

```text
utility
= base diagnostic value
+ current-session weak-dimension priority
+ cross-session weakness gap
+ uncovered-dimension bonus
+ uncovered-claim-node bonus
+ claim/question risk
- repeated-family penalty
- small extreme-difficulty penalty
```

이 값은 **합격 확률도, 검증된 psychometric information function도 아니다.** 현재는 다음 질문의 진단 효용을 정렬하기 위한 명시적 휴리스틱이다. 실제 사용자 모의면접 데이터가 누적되면 별도 benchmark로 보정해야 한다.

## 사실 권한

면접 엔진은 새로운 사실을 만들 수 없다.

| 대상 | 권한 소스 |
|---|---|
| 지원자 경험·역할·수치 | `02_확정경험원장.json`의 confirmed claim |
| 회사·기관·직무 사실 | `04_공식근거.json`의 confirmed research claim |
| 현재 제출 주장 표면 | 최종 `draft_final.json` 또는 최종 draft |
| 질문 의미 | `run.json.questions` |
| 과거 모의면접 학습 | aggregate weakness profile only |

최종 자기소개서는 무엇을 방어해야 하는지 정하지만 새로운 factual authority는 아니다. final draft가 참조한 미확정/없는 claim이 있으면 graph compilation 자체가 실패한다.

수치는 질문 target node 단위로 허용한다. 다른 경험에서 확인된 수치라고 해서 현재 질문에서 재사용할 수 없다. 공식 research claim 자체에 확인된 수치가 있으면 그 research node를 대상으로 하는 질문에서만 사용할 수 있다.

## Claim-Defense Graph

각 최종 자기소개서 문항을 다음 두 종류의 노드에 연결한다.

### Applicant node

- experience_id
- claim_id / claim_field / claim_value
- role / situation / actions / outcomes / competencies
- verification method / scope / period / formula / contribution
- authorized metric values
- lexical anchors
- risk

수치가 있거나 contribution 경계가 약하거나 인과 표현이 강할수록 risk가 상승한다.

### Research node

- research claim ID / claim / claim_type
- application_use
- source URL / checked_at / published_at / basis_date
- source type / tier / argument role / support strength
- freshness / conflict metadata
- authorized metric values
- risk

volatile fact, selection/eligibility/risk claim, conflict-group claim은 더 높은 검증 우선순위를 갖는다.

## 결정론적 hard gates

모델 평가보다 먼저 다음을 검사한다.

- target-scoped 승인되지 않은 수치
- target evidence anchor와의 지나치게 낮은 연결
- 본인 역할 표현 부재
- 팀/본인 경계 부재
- observed/unknown contribution에서의 인과 확대 위험
- 판단 기준 부재
- reflection 질문의 학습/한계 부재
- 고난도 압박 질문에서 주장 범위·근거 경계 표현 부재
- 목표 시간 대비 지나치게 짧거나 긴 답변
- 지나치게 빈약한 답변

`unsupported_metric`이면 semantic judge가 높게 평가하더라도 `evidence_defensibility`와 관련 `causal_precision`은 1점 이하로 강제된다. `ownership_overclaim_risk`이면 `ownership_precision`도 1점 이하로 제한한다.

## Semantic judges

선택적으로 여러 model ID를 사용할 수 있다. 각 model은 두 역할로 같은 답을 독립 평가한다.

- `structured_interviewer`
- `skeptical_interviewer`

각 judge는 question target node만 보고 밖의 지식을 사용할 수 없다. 점수는 차원별 median으로 집계한다. judge 결과는 진단 신호일 뿐 deterministic authority를 뒤집지 못하며 합격/불합격 확률을 만들지 않는다.

## 약점 메모리

`.career_profile/interview_weakness_profile.json`에는 다음만 저장한다.

- semantic dimension EMA
- deterministic weak-signal EMA
- observation count
- deterministic flag counts

원문 답변과 합격 확률은 저장하지 않는다. 따라서 다음 기관에서 과거 문장을 복사하지 않고도 반복 약점만 활용할 수 있다.

## 산출물

### `08_면접지능설계.json`

- authority/design contract
- source artifact provenance
- claim-defense graph
- question bank
- weakness profile summary
- recommended sequence
- high-risk nodes

### `08_면접질문은행.md`

사람이 바로 연습할 수 있는 고정 코어 + adaptive probe 질문은행.

### `08_면접세션평가.json`

모의면접 transcript를 평가한 세션 산출물. 세션 내부에는 검토용 answer excerpt가 남을 수 있지만 cross-session weakness profile에는 전달하지 않는다.

## 사용법

설계도 생성:

```powershell
python -m career_pipeline.interview_intelligence compile `
  --run "career_runs\<run-folder>"
```

transcript 예시:

```json
[
  {
    "question_id": "core:intro:60",
    "answer": "...",
    "elapsed_seconds": 58
  },
  {
    "question_id": "core:q1",
    "answer": "...",
    "elapsed_seconds": 63
  }
]
```

결정론적 평가만:

```powershell
python -m career_pipeline.interview_intelligence evaluate `
  --run "career_runs\<run-folder>" `
  --transcript "mock_interview.json" `
  --update-profile
```

다중 semantic judge 포함:

```powershell
python -m career_pipeline.interview_intelligence evaluate `
  --run "career_runs\<run-folder>" `
  --transcript "mock_interview.json" `
  --judge-model-id "<judge-a>" `
  --judge-model-id "<judge-b>" `
  --update-profile
```

## 기존 파이프라인과의 관계

이 모듈은 다음을 대체하지 않는다.

- experience ledger / claim verification
- posting / eligibility / matching
- official research intelligence
- Narrative Compiler / Integrated Writer / Deep Writer
- finalize
- legacy `08_면접대비팩.md`
- audit / application execution safety

`08_면접대비팩.md`는 여전히 사람이 읽는 연습팩이고 기존 validator의 호환 경계다. 새 엔진은 최종 제출본 이후 **무엇을 어떻게 검증하고 다음에 무엇을 물어볼지**를 담당하는 별도 intelligence layer다.

## 현재 한계와 다음 검증

1. `selection_utility`는 empirical calibration 전의 휴리스틱이다.
2. semantic judge의 0~4 점수는 모의면접 진단용이며 채용선발 타당도 수치가 아니다.
3. 음성 속도, pause, filler, prosody, 시선 등 multimodal signal은 아직 다루지 않는다.
4. 실제 개선 효과는 representative interview benchmark와 longitudinal A/B로 검증해야 한다.
5. 기관별 실제 면접유형/PT·토론·토의·AI면접은 별도 task model이 필요하다.

## 연구 근거

- Campion, M. A., Pursell, E. D., & Brown, B. K. (1988). *Structured interviewing: Raising the psychometric properties of the employment interview*. Personnel Psychology, 41(1), 25-42. DOI: 10.1111/j.1744-6570.1988.tb00630.x
- Campion, M. A., Palmer, D. K., & Campion, J. E. (1997). *A Review of Structure in the Selection Interview*. Personnel Psychology, 50(3), 655-702. DOI: 10.1111/j.1744-6570.1997.tb00709.x
- Levashina, J., Hartwell, C. J., Morgeson, F. P., & Campion, M. A. (2014). *The Structured Employment Interview: Narrative and Quantitative Review of the Research Literature*. Personnel Psychology, 67, 241-293. DOI: 10.1111/peps.12052
- Taylor, P. J., & Small, B. (2002). *Asking applicants what they would do versus what they did do: A meta-analytic comparison of situational and past behaviour employment interview questions*. Journal of Occupational and Organizational Psychology, 75, 277-294. DOI: 10.1348/096317902320369712
- Kell, H. J. et al. (2017). *Exploring Methods for Developing Behaviorally Anchored Rating Scales for Evaluating Structured Interview Performance*. ETS Research Report. DOI: 10.1002/ets2.12152
- Anugraha, D., Padmakumar, V., & Yang, D. (2026). *SparkMe: Adaptive Semi-Structured Interviewing for Qualitative Insight Discovery*. arXiv:2602.21136. 이 연구는 adaptive interviewing 설계 참고이며 채용선발 타당도 근거로 사용하지 않는다.
- Wen, Z. et al. (2026). *PolyInterview: An LLM-based Platform for Immersive Mock Interview Practice with Comprehensive Multimodal Assessment*. arXiv:2607.10310. 이 연구는 mock interview product/evaluation 참고이며 채용 합격예측 근거로 사용하지 않는다.
