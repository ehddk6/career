# Narrative Compiler: 자기소개서 생성 구조 V3

## 문제 정의

기존 파이프라인은 사실 검증, 글자 수, 공식 근거, 문체 위험, 후보 비교에는 강하지만, 산문을 만들기 **전**에 답변의 논증을 고정하는 중간 계층이 없다. 결과적으로 모델이 큰 근거 패킷을 한 번에 읽고 소재 선택·인과관계·문항 해석·글자 배분·문체를 동시에 해결하게 된다. 이 구조는 검증을 통과하면서도 다음과 같은 평범한 답을 만들 수 있다.

- 지원동기가 기관 설명으로 시작하고 개인의 선택 이유가 늦게 등장한다.
- 업무수행계획이 `확인 → 대조 → 기록 → 보고` 체크리스트로 수렴한다.
- 여러 문항에서 같은 경험·동사·결론이 반복된다.
- 문제해결 답변이 행동을 나열하지만 `왜 그 판단을 했는지`가 없다.
- 이슈 논술이 사실·대응책을 많이 나열하지만 하나의 인과 메커니즘과 트레이드오프가 없다.

따라서 개선 단위는 프롬프트가 아니라 생성 아키텍처다.

## 새 구조

```text
공고 + 문항 + 확정 경험원장 + 공식 근거
        ↓
1. Question Semantic Contract
   - 문항 의도
   - 하위 요구
   - 선택 개수(예: 한 가지)
   - 경험/리서치 필요성
        ↓
2. Evidence Graph
   - 제출 안전 claim
   - 기여도/인과 범위
   - 공식 research claim
        ↓
3. Portfolio Optimizer
   - 전 문항을 동시에 보고 경험 배치
   - 적합도 + 근거 + story completeness - 재사용 비용
        ↓
4. Answer Blueprint IR
   - 논증 beat
   - beat별 글자 예산
   - 사용할 claim/research 후보
   - 시그니처 행동
   - 금지 패턴
   - 면접 방어 질문
        ↓
5. Bounded Prose Generation
   - 문항 하나 + 해당 blueprint만 전달
   - 사용한 claim ID를 모델이 명시
        ↓
6. Adversarial Narrative Critic
   - question_gap / weak_thesis / company_brochure /
     action_blur / causal_gap / portfolio_redundancy 등 typed issue
        ↓
7. Targeted Repair
   - MATERIAL/HARD 문제만 최소 범위 재작성
        ↓
8. 기존 Python 사실·형식·공식근거 검증
```

핵심은 모델에게 “좋은 자소서를 써라”라고 요구하는 것이 아니라, 먼저 **무엇을 어떤 논리 순서로 증명할지 컴파일**한 뒤 문장은 그 결과를 렌더링하게 만드는 것이다.

## 문항별 논증 패턴

### 지원동기

`직접 답 → 개인 선택 기준 → 기관 고유 사실 → 경험으로 적합성 증명 → 실제 직무 행동 → 구체적 마무리`

기관 소개로 시작하지 않는다. 기관 사실은 지원자의 선택 기준을 입증하는 데 필요한 1개 정도만 사용한다.

### 조직 적응/협업/문제해결

`직접 답 → 장면/제약 → 판단 기준 → 직접 행동 → 확인된 결과 → 이후 적용 원칙`

STAR의 항목 채우기가 아니라 `판단 → 행동` 연결을 핵심으로 둔다.

### 업무수행계획

`초기 우선순위 → 학습 순서 → 오류 지점과 통제 → 권한 밖 escalation → 고객/동료 handoff → 개선 loop`

확인·대조·기록·보고 동사만 나열하는 업무 매뉴얼형 답변을 금지한다.

### 이슈/약식논술

`하나의 이슈와 입장 → 인과 메커니즘 → 취약 대상 → 정책 트레이드오프 → 기관이 할 수 있는 대응 → guardrail`

문항이 “한 가지”를 요구하면 thesis에서 정확히 하나만 선택한다. 존재하지 않는 기관 정책수단은 공식 근거 없이 만들 수 없다.

## 경험 배치

기존 순차 매칭은 앞 문항이 좋은 경험을 먼저 가져가 뒤 문항의 대체 가능성을 고려하기 어렵다. Narrative Compiler는 beam search로 전 문항의 배치를 함께 평가한다.

개념적 목적함수:

```text
portfolio_score
= Σ(question-experience fit)
+ Σ(evidence/story completeness)
+ diversity bonus
- reuse penalty
```

경험 재사용 자체를 금지하지 않는다. 대체 가능한 경험이 있을 때만 재사용 비용을 크게 주고, 하나의 경험만 있는 경우에는 재사용을 허용한다.

## 근거·인과 경계

Blueprint는 확정 claim 중 제출에 안전한 claim만 후보로 올린다. 수치 claim은 검증 방법, 범위, 기여도가 불완전하면 계획 단계에서 제외한다.

`contribution`에 따라 문장 권한도 구분한다.

- `caused` → 해당 claim 범위에서만 인과 표현 가능
- `contributed` → 기여 표현만 가능, 단독 원인 표현 금지
- `observed` → 관찰된 변화만 가능, 개인 성과로 승격 금지

최종 권한은 기존 `validate_draft`와 경험원장 검증기가 가진다. Blueprint는 새 사실 권한을 만들지 않는다.

## 산출물

Plan-only 실행은 모델 호출 없이 다음을 만든다.

```powershell
python -m career_pipeline.narrative_compiler --run "career_runs/<run>"
```

- `05_답변설계도.json`: 모델 입력용 narrative IR
- `05_답변설계도.md`: 사람이 검토할 수 있는 설계도

실제 초안 생성:

```powershell
python -m career_pipeline.narrative_compiler `
  --run "career_runs/<run>" `
  --generate `
  --model-id "<configured-model-id>"
```

기본 출력은 `draft_narrative.json`이다. 기존 `draft.json`을 자동 덮어쓰지 않는다. 기존 파일을 교체하려면 사용자가 출력 경로와 `--force`를 명시해야 한다.

생성 과정은 문항별 생성 후 전체 포트폴리오 critic을 실행한다. `MATERIAL`/`HARD` 문제만 제한된 횟수만큼 재작성하고, 마지막에 기존 결정론적 검증을 다시 수행한다. critic 문제가 남거나 Python 검증이 실패하면 종료 코드는 성공으로 처리하지 않는다.

## 설계 원칙

1. 더 큰 모델보다 더 작은 문제를 모델에 준다.
2. 사실과 서사 전략을 분리한다.
3. 검증은 산문 뒤에서만 하지 않고 산문 전에 가능한 제약을 컴파일한다.
4. 문항별 최적화가 아니라 지원서 전체의 포트폴리오 최적화를 한다.
5. 표면적 키워드 포함 여부보다 `판단 → 행동 → 근거 → 직무 연결`의 논증 구조를 우선한다.
6. 생성 품질과 사실 안전성을 상충시키지 않는다. 허용된 근거 범위 안에서만 서사를 더 선명하게 만든다.
