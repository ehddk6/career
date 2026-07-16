# 벤치마크 결과

## 최종 판정

`career-pipeline-v24`는 외부 6개 프롬프트의 동일 입력 산출물과의 익명 비교에서 `ALL_DIMENSIONS_AHEAD`를 달성했다.

| 항목 | 결과 |
|---|---:|
| 전체 지표 | 26 |
| Career Pipeline 우세 | 26 |
| 외부 방식 우세 | 0 |
| 무승부 | 0 |
| 회사조사 | Career Pipeline 우세 |
| 자기소개서 | Career Pipeline 우세 |
| 면접 | Career Pipeline 우세 |
| Career Pipeline HARD FAIL | 0 |

최종 판정 파일: `tmp/external_prompt_benchmark_20260715/benchmark_v24_gpt55.json`

## 결정적 개선

- 회사조사: 사업모델·전략 실행·출처·직무 연결을 claim ID로 연결하고 2026-07-16 공식 자료 재확인 기록을 추가했다.
- 자기소개서: 승인 경험만 사용하고 네 문항을 523·504·541·1222자로 맞췄다. 답변 SHA-256, 계산 모드, 목표 구간과 headroom을 `07_글자수검증.json`에 기록했다.
- 면접: 35개 질문을 recruiter·hiring manager·fact auditor·situational·executive·red-team 흐름으로 분리했다. 최종 제출 경험별 질문과 20·60·120초 카드의 분량 검사를 모두 통과했다.
- 안전성: 외부 최종본의 수치 경험은 D2·D3 방어 상태로 제출 답변에 사용되어 D4 필수 계약을 통과하지 못했다. v24는 미검증 수치와 과장 기여를 사용하지 않았다.
- 평가 공정성: HARD FAIL을 일으킨 수치나 주장을 고유성·문체·말하기 장점으로 다시 계산하지 못하도록 익명 평가 계약을 보강했다.

## 검증 결과

- 관련 테스트: `76 passed`
- 전체 테스트: `674 passed, 5 skipped`
- 계약 검증: HARD FAIL 0, REVIEW_REQUIRED 0
- 내부 감사: 96/100
- 블라인드 벤치마크: `ALL_DIMENSIONS_AHEAD` (26/26)

## 해석 제한

이 결과는 동결된 KODIT 입력과 현재 평가 계약에서의 비교 결과다. 실제 음성 모의면접은 수행하지 않았으며, 모델 기반 정성 평가는 재실행 시 일부 변동할 수 있다. 실제 합격이나 제출 완료를 뜻하지 않는다.
