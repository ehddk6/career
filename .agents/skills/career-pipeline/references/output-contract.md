# Career Pipeline Output Contract

## V2 근거 원칙

제출 답변과 면접팩은 `02_확정경험원장.json`의 `confirmed` 경험·claim만 사용한다. `proposed`, `rejected`, `stale`, `unknown`은 근거로 사용할 수 없다.

## `04_기업직무조사.md`

중요 주장마다 공식 출처의 직접 Markdown 링크를 넣고 `확인된 사실`, `해석`, `확인 필요`, `문항·면접 활용 맵`을 분리한다. 활용 맵에는 `draft.json`이 참조하는 공식 근거 ID를 그대로 적어 회사·직무 조사와 최종 답변의 연결을 감사할 수 있어야 한다.

## `05_문항전략.md`

각 문항에 문항 분류, 선택 `experience_id`, 허용 `claim_fields`, 공고 업무·역량 연결, 부족 근거를 기록한다.

## `draft.json`

UTF-8 JSON 배열로 작성한다.

```json
[
  {
    "question_index": 1,
    "answer": "승인된 사실만 사용한 답변",
    "experience_refs": [
      {
        "experience_id": "exp_1234567890abcdef",
        "claim_fields": ["budget_savings", "case_count"]
      }
    ],
    "evidence_paths": ["경험정리/근거문서.docx"]
  }
]
```

- 경험·행동·지원동기·업무계획 문항에는 `experience_refs`가 한 개 이상 필요하다.
- 경제·사회 이슈처럼 외부 사실의 분석만 요구하는 조사형 문항은 무관한 개인 경험을 억지로 붙이지 않는다. 이 경우 `experience_refs`와 `evidence_paths`는 비울 수 있지만, 검증된 공식 `research_refs`가 반드시 있어야 한다.
- `claim_fields`는 해당 경험의 `confirmed` claim 이름과 정확히 일치해야 한다.
- 참조한 claim의 핵심 값이 답변 본문에 실제로 드러나야 한다. 단순히 ID만 붙인 참조는 `experience_claim_not_visible`로 차단한다.
- 답변의 모든 수치는 참조한 claim의 `normalized_value`와 일치해야 한다.
- `evidence_paths`는 승인 claim의 `source_path`와 정확히 일치해야 한다.

## `08_면접대비팩.md`

`1분 자기소개`, 각 문항의 30·60·90초 답변, `꼬리질문`과 `꼬리답변`, `압박질문`과 `압박답변`, 문항별 로컬·공식 `근거`를 포함한다. 30·60·90초 답변은 같은 문장을 복제하지 않고 단계적으로 논리와 근거가 구체화되어야 한다. 근거란에는 해당 자기소개서 문항의 `experience_id`와 공식 근거 ID를 그대로 적는다. 감사에서는 제목 존재뿐 아니라 실제 답변 본문, 연습 길이, 방어 논리, 자기소개서 근거 ID 연결을 문항별로 검사한다. 자기소개서와 승인 원장에 없는 새로운 수치를 추가하지 않는다.

## `04_공식근거.json`

각 주장에는 `claim_type`(`organization_role`, `job_duty`, `industry_issue`, `program_or_service`, `risk_or_limit`, `eligibility`, `selection_criteria`)와 `application_use`를 기록한다. `application_use`는 해당 공식 사실을 자기소개서 문항 또는 면접 답변에서 어떻게 사용할지 설명하며, 지원자의 해석을 공식 사실처럼 섞지 않는다. 조사형 이슈 문항에는 `industry_issue`·`risk_or_limit`·`program_or_service`, 기관 역할·지원동기에는 `organization_role`·`program_or_service`, 업무계획에는 `job_duty`·`program_or_service` 근거를 사용한다. 공식 선발 기준은 `selection_criteria`로 기록하고 면접팩 평가 기준과 근거 ID를 연결한다.

## `12_최종산출물.json`

최종 답변 JSON·Markdown·DOCX의 상대 경로와 SHA-256, 선택된 원본 종류, 생성 시각, 후처리 모델 호출 여부, 논리 tier, 실제 모델 ID, 검증 결과를 기록한다. `run.json.final_artifact`에도 같은 내용을 저장한다. 감사는 이 manifest에 기록된 파일만 읽는다.

rigorous 실행의 `selection`에는 `data_package`(ID·버전·동결 자료 SHA), 실제 Sol 모델 ID,
호출 수, 후보·심사 수, `review_required_candidates`, 최종 X/Y 선택과 심사 산출물 SHA-256을
함께 기록한다. 심사위원의 의미적 우려는 즉시 탈락시키지 않고 `REVIEW_REQUIRED`로 보관하며,
결정론적 오류 또는 원자료 대조로 확정된 오류만 `hard_fail`에 반영한다.

rigorous 후보 전략은 `FACT_FIRST`, `QUESTION_FIRST`, `EXPERIENCE_DIVERSITY`,
`JOB_RELEVANCE`로 분리한다. 전략 대응표는 `rigorous/private_mapping.json`에만 저장하고
익명 후보·심사 입력에는 포함하지 않는다.

## `11_최종품질감사.json`

자기소개서 40점, 기업조사 25점, 면접팩 20점, 문체·안전성 15점의 총 100점 내부 규칙 점수를 기록한다. 기존 `score`와 `recommendation`을 유지하면서 `internal_validation_score`, `quality_gate`, `human_review_recommended`를 함께 기록한다. 문체 진단 중 `should_rewrite=false`인 경미한 경고는 기록하되 감점하지 않는다. Patina의 존재 여부 자체는 점수가 아니며 기본 실행에서 Patina 보고서가 없어도 실패하지 않는다.

## 상태 계약

- `blocked_profile`: 승인·근거·stale 문제
- `blocked_posting`: 공고 공식성·필수 필드·문항 불일치
- `blocked_conflict`: 동일 근거의 확정 값 충돌
- `ready_for_research`: 조사·합성 가능
- `blocked_validation`: 최종 답변 또는 면접팩 근거 검증 실패
- `complete`: Markdown·DOCX·검토보고서 생성 완료

## Phase 2 자격 판정 계약

`ApplicantProfile`은 개인정보 본문을 저장하지 않고 승인 원장 경로와 구조화된 학력·경력·자격증·근무 가능 지역만 보유한다. `ApplicantExperience.status`가 `confirmed`인 경험만 자동 판정의 근거로 사용한다.

`PostingRecord`는 `posting_id`, 공고 URL, 공식 출처 상태, 게시·마감 시각, 본문 `body_sha256`, 필수 `required_rules`, 우대 `preferred_rules`를 기록한다. 같은 `posting_id`의 본문 SHA-256 변경은 `changed`로 기록하고 기존 지원 흐름을 자동 재사용하지 않는다.

`EligibilityDecision.status`는 다음 네 값만 허용한다.

- `eligible`: 구조화된 필수·우대 조건을 모두 충족
- `eligible_with_gaps`: 필수 조건은 충족하지만 우대 조건 일부 미충족
- `manual_review`: 정보 부족, 자연어 해석, 졸업예정·유효기간·지역 제한 등 불확실성
- `ineligible`: 명시적으로 확인된 필수 조건 미충족

판정은 합격 확률이나 채용 보증이 아니다. `manual_review`와 `eligible_with_gaps`에는 `human_review_required: true`를 기록한다. `reasons`는 문자열 배열이 아니라 `{code, field, message}` 객체 배열이며, `RuleEvaluation`에는 동일한 의미의 `reason_code`와 사용자용 `reason`을 함께 기록한다. 동일 입력은 공고 마감일 또는 검색 시각에서 유도한 평가 기준일을 사용해 결정론적으로 판정한다.
