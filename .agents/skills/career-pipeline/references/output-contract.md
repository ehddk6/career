# Career Pipeline Output Contract

## V2 근거 원칙

제출 답변과 면접팩은 `02_확정경험원장.json`의 `confirmed` 경험·claim만 사용한다. `proposed`, `rejected`, `stale`, `unknown`은 근거로 사용할 수 없다.

## `04_기업직무조사.md`

중요 주장마다 공식 출처의 직접 Markdown 링크를 넣고 확인된 사실과 `[확인 필요]`를 분리한다.

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

- V2의 모든 답변에는 `experience_refs`가 한 개 이상 필요하다.
- `claim_fields`는 해당 경험의 `confirmed` claim 이름과 정확히 일치해야 한다.
- 답변의 모든 수치는 참조한 claim의 `normalized_value`와 일치해야 한다.
- `evidence_paths`는 승인 claim의 `source_path`와 정확히 일치해야 한다.

## `08_면접대비팩.md`

`1분 자기소개`, 문항별 30·60·90초 답변, `꼬리질문`, `압박질문`, 로컬 `근거`를 포함한다. 자기소개서와 승인 원장에 없는 새로운 수치를 추가하지 않는다.

## `12_최종산출물.json`

최종 답변 JSON·Markdown·DOCX의 상대 경로와 SHA-256, 선택된 원본 종류, 생성 시각, 후처리 모델 호출 여부, 논리 tier, 실제 모델 ID, 검증 결과를 기록한다. `run.json.final_artifact`에도 같은 내용을 저장한다. 감사는 이 manifest에 기록된 파일만 읽는다.

## `11_최종품질감사.json`

자기소개서 40점, 기업조사 25점, 면접팩 20점, 문체·안전성 15점의 총 100점 내부 규칙 점수를 기록한다. 기존 `score`와 `recommendation`을 유지하면서 `internal_validation_score`, `quality_gate`, `human_review_recommended`를 함께 기록한다. Patina의 존재 여부 자체는 점수가 아니며 기본 실행에서 Patina 보고서가 없어도 실패하지 않는다.

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
