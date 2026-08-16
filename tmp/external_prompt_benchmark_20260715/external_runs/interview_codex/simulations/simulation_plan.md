# SIMULATION PLAN

현재까지 실제 모의면접은 실행하지 않았다. 음성·실시간 답변 없이 작성된 문장만으로 전달력을 채점하지 않는다.

## 기본 실행 설정

```yaml
simulation_mode: STANDARD
feedback_timing: AFTER_FULL_INTERVIEW
difficulty: REALISTIC
question_count: 12
target_duration: "20 minutes (practice only)"
target_interview_stage: 면접전형
```

## 3회 권장 순서

1. `STANDARD / REALISTIC / 12문항`
   - Q001~Q012를 순서대로 진행
   - 전체 종료 후 내용 평가
2. `FACT_CHECK / DEEP_PROBE / 8문항`
   - EX01~EX04와 Q4 경제이슈만 집중
   - 수치·개인기여·근거 경계 검증
3. `PRESSURE / ADVERSARIAL_BUT_FAIR / 10문항`
   - `final/probe_defense_notes.md`의 RED TEAM 사용
   - 회피·과장·역할 월권 확인

## 상태 흐름

`PREPARE → ASK → WAIT → PROBE → WAIT → RECORD → NEXT → EVALUATE → RETRY`

## 운영 규칙

- 질문은 한 번에 하나만 제시한다.
- 첫 답변이 끝나기 전 피드백하지 않는다.
- `AFTER_FULL_INTERVIEW`에서는 종료 전 점수·힌트·모범답안을 주지 않는다.
- 꼬리질문은 직전 답변의 모호함·누락·수치·직무 연결에서만 만든다.
- 실제 음성 자료가 없으면 전달 평가는 `available: false`로 기록한다.
- 재시도는 전체 재작성보다 가장 큰 위험 한 가지를 고치는 방식으로 한다.

