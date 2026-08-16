# 프롬프트 실행 결과와 Career Pipeline 비교 보고서

- Date: 2026-07-15
- Isolated directory: `C:\Users\ehddk\OneDrive\문서\취업\tmp\prompt_pipeline_comparison_20260715`
- Baseline: `C:\Users\ehddk\OneDrive\문서\취업\career_runs\kodit-2026-h2-rigorous-20260714-v22`

## 최종 판정

- 원문 품질 우승자(잠정): **외부 자기소개서 기존 후보**(별도 기존 비교 기록의 블라인드 중앙값 98점).
- 제출 안전성 우승자: **Career Pipeline v22**(결정적 자소서·공식근거 검증 이슈 0건, 최종 감사 93/100 `pass`).
- 종합 추천본: **Career Pipeline v22를 기반으로 사용**하고 외부 후보의 Q1·Q2·Q4 표현만 수동 검토한다. Q3는 `contribution_overstatement` 때문에 그대로 사용하지 않는다.

> 두 결과의 `data_package_id`가 달라 원문 점수 비교는 동일 동결자료에 대한 확정 판정이 아니라 잠정 참고값이다.

## 핵심 비교

| 항목 | 외부 기존 후보 | Career Pipeline v22 | 판정 |
|---|---:|---:|---|
| 문항 글자 수 | [467, 438, 514, 988] | [504, 525, 535, 1285] | 프로젝트 Q4가 더 충실하고 외부 Q4는 짧음 |
| 기존 별도 비교 기록의 블라인드 중앙값 | 98 | 92(현재 v22 아님) | 외부 우세지만 패키지 불일치 |
| 결정적 draft 검증 | 차단 | 통과 | 프로젝트 우세 |
| 공식근거 검증 | 차단 | 통과 | 외부 Q4 연결성 경고 |
| 최종 감사 | 미완결 | 93/100, 통과 | 프로젝트 우세 |

## 외부 후보를 최종 제출본으로 쓰지 않는 이유

- Q3: `contribution_overstatement` — 답변이 기록된 직접 기여 범위를 넘어섰다.
- Q4: 엄격한 공식근거 연결 검증에서 `research_application_use_not_linked`가 발생했다.
- Career Pipeline v22: 같은 경험 원장·공식근거로 재검증한 결과 이슈가 0건이다. 현재 v22에 대한 신규 블라인드 점수는 외부 프롬프트 실행 미완결로 산출하지 못했다.

외부 문장은 윤문 참고자료로는 유용하지만 제출 산출물로 자동 승격할 수 없다.

## 회사조사·면접 비교

- 회사조사 프롬프트는 `CR-DATA-001` v1.0까지 생성했지만 최상위 manifest가 완성되지 않았고 final/judges 디렉터리도 비어 있어 **부분 실행**이다. hard-fail 보고서 자체는 PASS이나 미검증 항목이 24개이고 결론은 `INSUFFICIENT_EVIDENCE`다.
- 기존 프로젝트 회사조사는 공식 사실·해석·확인 필요·활용 맵이 있지만 JSON 계약 sidecar가 없어 계약 검증은 하위 호환 방식으로 비활성화된다.
- 기존 프로젝트 면접팩은 제출문항 4개, 30/60/90초 답변, 꼬리질문, 압박질문, 근거 ID를 담고 있다. 다만 D3/D4·25문항·역질문을 기계 검증하는 JSON 패킷은 아니므로 외부 프롬프트와 동급 결과로 취급하지 않았다.
- 외부 면접 프롬프트의 추적 가능한 완결 산출물은 확인되지 않았다.

## 입력·패키지 검증

- 프롬프트 원본 4개를 격리 디렉터리에 복사했고 SHA-256이 모두 일치한다. 상세: `C:\Users\ehddk\OneDrive\문서\취업\tmp\prompt_pipeline_comparison_20260715\input_manifest.json`.
- 외부 회사조사 manifest 입력 해시 불일치: 11개 중 0개.
- Career Pipeline 패키지: `SOL-DATA-608228643DF2` / v1.1 / frozen SHA `608228643df29ad9deab874e72e9842e247fa54c0c80d2316fd43674077b81c7`.
- 외부 기존 자기소개서 패키지: `SOL-DATA-ACB9EA4AEAAC` / v1.1 — 기준선과 다름.
- 외부 회사조사 패키지: `CR-DATA-001` / v1.0 — 프로젝트와 다름.

## 계약·최소 실행 검증

- sidecar가 없으면 `enabled=false`, `hard_fail=false`로 하위 호환된다.
- sidecar가 한쪽만 있으면 `incomplete_prompt_contract_pair` HARD_FAIL이다.
- 정상 sidecar 두 개는 `13_프롬프트통합검증.json`을 생성하고 PASS한다.
- 수치 경험 방어 깊이 D3은 `insufficient_defense_depth`로 차단되고 D4는 통과한다.
- X/Y 비교는 실제 문항 집합 3개와 5개에서 통과했고, 문항별 `choice`, `reason`, `decisive_difference`를 요구한다.
- `contracts init`은 기존 회사조사·면접 Markdown의 해시를 보존했다.

## 실행하지 못했거나 사람 확인이 필요한 항목

- 제공된 최종 통합 프롬프트의 추적 가능한 독립 완결 실행 산출물이 없다: `C:\Users\ehddk\Downloads\회사조사_면접_프롬프트_묶음\GPT-5.6_Sol_자기소개서_최종_통합_프롬프트.md`.
- 회사조사 프롬프트는 Codex CLI hook/subagent 런타임 반복으로 중단되었고 재시도에서도 모델 버전·plugin/hook 오류가 발생했다.
- 외부 면접 프롬프트는 완결된 추적 산출물이 없다.
- 회사조사 미검증 24개, 프로젝트 Q2 직무 연결, Q3 기관 고유성, 문체 위험은 사람 확인이 필요하다.
- 제출 전 현재 공식 공고·정책자료와 지원 사이트의 실제 글자 수 규칙을 다시 확인해야 한다.

## 보존·변경 범위

- 비교 산출물은 모두 `C:\Users\ehddk\OneDrive\문서\취업\tmp\prompt_pipeline_comparison_20260715` 아래에 저장했다.
- 비교 과정에서 원본 프롬프트, v22 산출물, 사용자가 수정한 저장소 파일을 덮어쓰지 않았다.
- commit, push, PR, 실제 지원 제출은 수행하지 않았다.

Machine-readable files: `comparison_report.json`, `input_manifest.json`, `execution_status.json`, `smoke_results.json`.
