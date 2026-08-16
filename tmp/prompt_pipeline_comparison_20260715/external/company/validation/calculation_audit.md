# Calculation Audit

- 데이터 패키지: `CR-DATA-001` v1.0

1. 허용된 `04_공식근거.json`에는 KODIT 재무제표 수치가 없다.
2. `bok-fx-risk-20260711`의 14조원은 한국은행 제도 한도이므로 KODIT 수치에서 제외했다.
3. 수치 추정·환산·기간 보간을 수행하지 않았다.
4. `scripts/financial_analysis.py`는 근거 파일 SHA-256을 확인 가능한 형태로 기록하고 빈 계산 결과를 재현한다.
5. 결과 상태는 `INSUFFICIENT_SOURCE_DATA`이며 계산 오류는 발견되지 않았다.
