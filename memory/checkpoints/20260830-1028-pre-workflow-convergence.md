# Checkpoint — 취업 파이프라인 구조 개선 분석 완료 — 2026-08-30 09:58

## The story so far

NRS v2는 사용자 승인에 따라 production 기본 작성기로 적용됐고 전체 테스트 876개가 통과했습니다. 이어서 공고 분석·지원자 사실·자격 판정·공식 자료조사·자기소개서·면접·골든패스·감사 경로와 로컬 과거 실행 68건을 조사했습니다. 가장 큰 문제는 기능 부족이 아니라 운영 미채택입니다. 과거 실행에서 NRS 선택, 면접지능, 골든패스, 시스템 벤치마크 산출물이 모두 0건이었습니다. 자격 판정기는 정교하지만 실제 공고/프로필 투영이 구조화 입력을 만들지 못하고, 안전한 연구 수집기는 호출자가 없으며, 면접팩은 최종본 전후 수동 작성을 요구합니다. 분석과 다음 구현 계약은 `docs/2026-08-30-career-pipeline-improvement-analysis.md`에 있습니다.

## Decided

- D-002: NRS v2를 production 기본 자기소개서 작성기로 사용한다.
- 다음 우선순위는 새 작성 알고리즘이 아니라 기본 CLI·골든패스·레거시 진단을 묶는 운영 수렴이다.
- 기존 실행과 사용자 자료는 일괄 변환하거나 덮어쓰지 않는다.
- 합격 확률을 추정하지 않고 사용자 선호·수정·면접 수행은 진단 신호로만 사용한다.

## Waiting on the user

- Q-001: 최초 production NRS end-to-end 스모크 런에 사용할 현재 유효한 공식 공고 1건은 사용자가 선택해야 한다.

## Next first action

`docs/2026-08-30-career-pipeline-improvement-analysis.md`의 “1단계 구현 계약”대로 `career-pipeline workflow start/resume/status/migrate-plan` 운영 수렴 패키지부터 구현한다.

## Tried

- 2026-08-17 아키텍처 문서의 “골든패스·면접지능 부재”는 현재 구현과 맞지 않아 신규 권고에서 제외했다.
- 기본 시스템 Python에는 pytest가 없어 테스트를 시작하지 못했다. `.tmp_nrs_v2_test\Scripts\python.exe`로 재실행해 876 passed, 7 skipped를 확인했다.
- 첫 보고서 리허설에서 CLI 인자·출력·종료 코드·마이그레이션 판정이 모호했다. 보고서에 구체적인 1단계 구현 계약을 추가했다.
