# 기존 파이프라인 진단

```yaml
problem_id: CP-QUALITY-001
symptom: 외부 후보 98점, v22 92점의 원문 품질 차이
evidence: 기존 비교 기록과 v22 감사 93점
root_cause: 한국어 가독성 5점, 지원자 고유성 3점으로 생성·선택 압력이 낮음
affected_stage: rigorous generation and judging
quality_impact: 안전하지만 일반적이고 덜 기억되는 문장
recommended_fix: NATURAL_VOICE 후보와 평가 비중 확대
priority: critical
```

```yaml
problem_id: CP-QUALITY-002
symptom: Q2 직무 연결, Q3 기관 고유성과 목표 구체성 누락
evidence: v22 audit missing_job_connection, missing_target_specificity
root_cause: KODIT 문항 1~4를 생성 프롬프트에 직접 하드코딩하고 구조화 문항 계약이 없음
affected_stage: prepare and rigorous generation
quality_impact: 다른 공고로 일반화되지 않고 하위 요구가 후보별로 누락됨
recommended_fix: 05_문항전략.json과 공고 기반 검증
priority: critical
```

```yaml
problem_id: CP-QUALITY-003
symptom: 회사조사와 면접 Markdown은 통과하지만 시장·최근 실행·말하기 품질이 약함
evidence: 새 프롬프트 비교에서 business_model과 interview_defense가 외부 강점으로 분류됨
root_cause: 기존 계약이 사실 안전성 중심이며 사용성과 전달 품질을 충분히 구조화하지 않음
affected_stage: research and interview
quality_impact: 안전한 자료가 지원동기와 실제 답변으로 전환되지 않음
recommended_fix: 계약 v2와 INTERVIEW_COACH 심사
priority: high
```
