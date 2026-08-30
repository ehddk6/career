# Checkpoint — 자기소개서 writer v2 holdout 승격 계산 완료 — 2026-08-29 17:49

## The story so far

R10 회귀시험은 12/12, R11 holdout은 9/9 문항과 preflight를 통과했고 R11 manifest 검증은 729개 파일 모두 일치합니다. 사용자 평가는 A/B/A/A/A/A/A/B/A이며, 질문 문구를 포함한 보정 패킷을 기준으로 최종 계산했습니다. NRS는 선호 6:3, 자연스러운 한국어 6:3, `REJECT_BOTH` 0건이고, 사실·수치·행위자 오류와 감사식 메타 문구 누출도 0건입니다. 모든 승격 조건을 통과해 `eligible_for_user_approval`이 되었으나 기본 writer는 여전히 변경하지 않았습니다. 전체 pytest는 873 passed, 7 skipped입니다.

## Decided

- NRS는 인간 blind 검토와 사용자 승인 전까지 shadow-only로 유지하며, 기본 writer는 자동으로 바꾸지 않습니다.
- 기존 6:6 결과는 보존하되 `genre_contract_failure`로 writer 효능 근거에서 제외합니다.
- 모델 식별자는 확인할 수 없으므로 manifest에 `null`로 기록합니다.
- control과 NRS는 동일한 프롬프트 계약, backend, 후보 수, 재시도 예산 및 장르 게이트를 사용합니다.
- 원래 R11 blind 패킷의 문항 누락은 계약 결함으로 기록하며, 기존 파일과 manifest는 보존합니다. 보정 패킷과 사용자의 진행 지시를 근거로 question_fit을 최종 계산에 반영했습니다.

## Waiting on the user

- NRS를 production 기본 writer로 채택할지 여부는 사용자만 결정할 수 있습니다. 현재 기본값은 shadow-only입니다.

## Next first action

사용자가 production opt-in을 명시하면 `production_opt_in.final.private.json`을 근거로 기본 writer 설정 변경 범위를 제안하고 승인된 범위에서만 적용합니다.

## Tried

- 이전 R1–R9 실행은 감사 기록으로 보존했습니다. 초기 실행 안정성, 기여도 검증의 오탐, 계획 경로의 근거 누락 문제를 수정했으며 기존 산출물은 삭제하지 않았습니다.
- 선택한 수치와 실제 산문 수치가 일치하지 않아 발생한 오탐은 산문에 보이는 승인 수치만 참조에 연결하도록 수정했습니다.
- 선택하지 않은 선택형 조사 근거가 본문에 보이지 않아도 연결되던 문제는, 실제 문장에 나타난 경우에만 연결하도록 수정했습니다.
- 일부 생성 후보는 사실·장르 게이트에서 탈락했습니다. 양쪽은 동일한 3개 생성·후보당 최대 2회 예산을 모두 사용했고, 유효 후보만 counterbalanced blind 선별에 넣었습니다. 탈락 기록은 private pilot 자료에 남아 있습니다.
- 기본 셸과 번들 Python에는 pytest가 설치되어 있지 않아 격리 작업트리의 `.tmp_nrs_v2_test` 임시 환경에 `.[dev]`를 설치해 검증했습니다.
