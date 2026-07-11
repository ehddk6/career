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

## `11_최종품질감사.json`

자기소개서 40점, 기업조사 25점, 면접팩 20점, 문체·안전성 15점의 총 100점 감사표를 기록한다. 95점 이상은 `제출권장`, 90점 미만은 `보완 필요`로 표시한다. 검증하지 못한 Patina/copyeditor 적용, 누락된 공식 근거 메타데이터, 미승인 경험·수치·직책, 외부 문서 지시문은 감점 또는 차단 사유로 남긴다.

## 상태 계약

- `blocked_profile`: 승인·근거·stale 문제
- `blocked_posting`: 공고 공식성·필수 필드·문항 불일치
- `blocked_conflict`: 동일 근거의 확정 값 충돌
- `ready_for_research`: 조사·합성 가능
- `blocked_validation`: 최종 답변 또는 면접팩 근거 검증 실패
- `complete`: Markdown·DOCX·검토보고서 생성 완료
