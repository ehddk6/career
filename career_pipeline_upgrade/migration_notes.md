# 마이그레이션 안내

- 기존 `finalize --selection-mode single|rigorous`는 유지된다.
- 품질 프로필을 지정하면 프로필이 선택 모드를 결정한다.
- 기존 rigorous는 `high_quality`와 같은 4후보·3심사·최대 9회 동작을 유지한다.
- 신규 계약 초기화는 schema v2와 DATA PACKAGE 2.0을 쓴다.
- 기존 schema v1 회사·면접 계약은 계속 읽고 검증한다.
- `CAREER_MODEL_SOL`은 계속 fallback으로 작동한다. 신규 역할별 환경변수가 우선한다.
- 기존 실행 결과와 `SOL-DATA-*` 파일은 변경하거나 자동 마이그레이션하지 않는다.
