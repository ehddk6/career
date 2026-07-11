# SKILL.md / output-contract.md 알려진 차이점

이 문서는 v2 통합으로 덮어씌워진 사용자 원래 수정본과 v2 버전의 차이를 기록합니다. 사용자 수동 복구를 위한 참고 자료입니다.

## SKILL.md

### committed 버전 (73ab934) - 67줄
- 첫 세션의 v1 스킬 설명
- 단순한 execute 순서: prepare -> 사용자 확인 -> finalize

### v2 덮어쓰기 후 (현재) - 102줄
- v2 프로필/포스팅/매칭 흐름 설명 추가
- blocked_profile, blocked_posting, blocked_conflict, blocked_validation, complete 상태 계약
- V2 실행 순서: profile build -> posting analyze -> matching -> research

### 알 수 없는 정보
- **사용자 원래 수정본** (2026-06-22~23 세션에서 추가했을 내용)
- 첫 세션(phase2_workspace_diff.md에 언급)의 차이:
  - "V2는 승인된 경험과 공식 공고만 제출 답변의 근거로 사용한다"
  - "proposed 값은 사용자가 확인하기 전까지 절대 확정하지 않는다"
  - description 변경: "사용자 승인 경험 원장을 만들고 공식 채용공고를 분석"

## output-contract.md

### committed 버전 (73ab934) - 31줄
- 04_기업직무조사.md, 05_문항전략.md, draft.json, 08_면접대비팩.md 형식 설명
- evidence_paths 정확히 일치 요구
- 자기소개서에 없는 주장 면접 답변에 추가 금지

### v2 덮어쓰기 후 (현재) - 35줄
- V2 근거 원칙 추가: confirmed만 사용, proposed/rejected/stale/unknown 제외
- experience_refs + claim_fields 구조 추가
- 상태 계약: blocked_profile/posting/conflict/validation, complete

### 알 수 없는 정보
- **사용자 원래 수정본** (2026-06-22~23 세션에서 추가했을 내용)
- 첫 세션의 차이:
  - V2 출처 원칙 명시
  - proposed 상태 명시적 언급
  - claim_fields의 confirmed 일치 요구
