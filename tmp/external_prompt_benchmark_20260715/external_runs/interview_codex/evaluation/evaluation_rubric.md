# EVALUATION RUBRIC

| 평가 항목 | 배점 | 기준 |
|---|---:|---|
| 질문 응답성 | 15 | 첫 문장에서 직접 답하고 질문의 모든 부분을 다룸 |
| 사실 정확성 | 20 | Claim/Fact ID 범위, 수치·기관·제도 구분 |
| 판단 타당성 | 15 | 기준과 대안을 설명하고 과도한 일반화 회피 |
| 직접 행동 | 15 | 본인이 한 행동과 계획이 구체적 |
| 직무 연결 | 10 | 기한연장·상시관리의 확인·기록·보고·인계 연결 |
| 회사 연결 | 10 | KODIT 역할·미션·2026 방향 중 필요한 것만 연결 |
| 솔직한 한계 | 5 | 모르는 범위·권한·미확인 사실을 명확히 구분 |
| 전달 명료성 | 5 | 짧은 문장, 반복 최소화, 결론-근거 구조 |
| 시간 준수 | 5 | 목표 분량 안에서 마무리 |
| 합계 | 100 |  |

## 판정

- 85~100: `PASS_CANDIDATE` - 사실 검증까지 통과한 경우에만
- 75~84: `REVISE_MINOR`
- 60~74: `REVISE_MAJOR`
- 0~59: `FAIL`
- HARD FAIL이 하나라도 있으면 점수와 무관하게 `REVIEW_REQUIRED`

## 답변 기록 스키마

```json
{
  "question_id": "",
  "answer_summary": "",
  "content_assessment": {
    "directness": 0,
    "fact_accuracy": 0,
    "judgment": 0,
    "direct_action": 0,
    "job_relevance": 0,
    "defensibility": 0
  },
  "delivery_assessment": {
    "available": false,
    "clarity": null,
    "pace": null,
    "sentence_control": null
  },
  "strongest_point": "",
  "largest_risk": "",
  "missing_information": [],
  "contradictions": [],
  "unanswered_part": "",
  "recommended_minimal_revision": "",
  "next_probe": ""
}
```

