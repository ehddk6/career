# Checkpoint — P0 운영 수렴 패키지 구현 완료 — 2026-08-30 10:28

## The story so far

P0 운영 수렴 패키지를 구현했습니다. 기본 CLI에는 `career-pipeline workflow start/resume/status/migrate-plan`이 추가됐고 기존 최상위 `status`와 `career-pipeline-golden`은 유지됩니다. `workflow status`와 `migrate-plan`은 읽기 전용입니다. migration 계획은 strict V2, private workspace 경계, 필수 산출물 SHA를 기반으로 재개 후보를 보고합니다. `workflow resume`은 `--system-benchmark off|report|required`를 지원하며 기본값은 off입니다. 실제 `career_runs` 68건을 읽기 전용으로 검사했고 strict V2 실행만 `resume_candidate`로 표시했습니다. 전체 테스트는 883 passed, 7 skipped입니다.

## Decided

- D-002: NRS v2를 production 기본 자기소개서 작성기로 사용한다.
- D-003: 사용자가 P0 운영 수렴 패키지 구현을 승인했다.
- 기존 실행과 사용자 자료는 일괄 변환하거나 덮어쓰지 않는다.

## Waiting on the user

- Q-001: 최초 production NRS end-to-end 스모크 런에 사용할 현재 유효한 공식 공고 1건은 사용자가 선택해야 한다.

## Next first action

사용자가 선택한 최신 공식 공고와 승인된 별도 지원자 프로필 사실을 받아 `career-pipeline workflow start`로 첫 NRS production smoke run을 시작한다.

## Tried

- 첫 시스템 벤치마크 테스트는 다문항 함수가 기본 검증기만 사용해 독립 검증기를 주입할 수 없어서 실패했다. 운영 기본값은 바꾸지 않고 선택적 `validator` 인자를 추가해 해결했다.
- Windows 기본 콘솔 인코딩에서는 human migration 출력의 한글이 도구 출력에 깨져 보였다. JSON 출력과 pytest 캡처는 정상이며, 실제 PowerShell 표시 환경은 별도로 확인할 필요가 있다.
