# Claim Ledger

- 데이터 패키지: `CR-DATA-001` v1.0

| Claim ID | 주장 | 유형 | 기간 | 출처 | 수준 | 반대 근거·한계 | 상태 | 본문 사용 |
|---|---|---|---|---|---|---|---|---|
| kodit-role-20260711 | 신용보증기금은 기업이 부담하는 각종 채무를 보증해 성장유망기업을 지원하며 신청 뒤 신용조사·보증심사를 수행한다고 설명한다. | COMPANY_CLAIM | 2026-07-13 기준 | SRC-04-A | 2 | 성과·수익모델은 입증하지 않음 | ATTRIBUTED_ONLY | 가능, 주체 명시 |
| kodit-intern-duty-20260711 | 보증 분야 인턴 주요업무는 신용보증 기한연장과 기업신용 상시관리다. | FACT | 2026-07-09 | SRC-04-B | 2 | 세부 업무·권한은 미공개 | CONFIRMED_PRIMARY | 가능 |
| bok-fx-risk-20260711 | 한국은행은 높은 환율 변동성 등에 유의하며 14조원 한도의 중소기업 한시 특별지원 운용기간을 연장했다. | FACT | 2026-03 | SRC-04-C | 1 | 기업별 영향 방향은 다름 | CONFIRMED_PRIMARY | 가능 |
| kodit-liquidity-support-20260711 | 신용보증기금은 지역 소재 수출기업 등에 우대보증과 보증료 지원을 제공한다고 발표했다. | COMPANY_CLAIM | 2026-03-24 | SRC-04-D | 2 | 투입 규모·실제 효과 없음 | ATTRIBUTED_ONLY | 가능, 성과 표현 금지 |
| kodit-selection-criteria-20260713 | 서류는 충실도·논리력·혁신적 사고, 면접은 기본인성·직무능력을 평가한다. | FACT | 2026-07-09 | SRC-04-B | 2 | 공식 합격 가능성 점수는 아님 | CONFIRMED_PRIMARY | 가능 |
| app-doc-3000-2d | 지원자는 3,000페이지 자료를 체계적으로 분류해 2일 만에 정리했다. | FACT | 기간 미상 | SRC-02 `clm_88cfeab230789e5b0d5f` | APPLICANT | 조직·기간·세부 분담 미상 | CONFIRMED_PRIMARY | 가능, 범위 그대로 |
| app-compare-report | 지원자는 같은 데이터를 기존 엑셀 수식과 외주 프로그램에 넣어 결과 비교 분석 보고서를 작성하고 팀장에게 보고했다. | FACT | 기간 미상 | SRC-02 `clm_3e69991c9b56d728b429` | APPLICANT | 보고 후 조치 미상 | CONFIRMED_PRIMARY | 가능 |
| app-excel-speed | 지원자는 엑셀 자동화를 도입해 급여 산정 속도를 30% 향상했다. | FACT | 기간 미상 | SRC-02 `clm_353c575898c6254492e8` | APPLICANT | 측정 기준·기간 미상 | CONFIRMED_PRIMARY | 제한적 가능 |
| inf-intern-support | 자료 누락 확인, 전산 입력, 처리상황 기록, 고객 안내는 인턴의 가능한 보조 행동이다. | INFERENCE | 향후 | SRC-05 + kodit-intern-duty-20260711 | 내부 해석 | 실제 팀 분장 미확인 | INFERENCE_SUPPORTED | 추론 표지 필수 |
| nv-revenue | 신용보증기금의 수익·비용·재원 구조 | FACT | - | 없음 | - | 동결 자료 없음 | NEEDS_VERIFICATION | 금지 |
| nv-financial | 재무·운영 수치 및 최근 3개년 변화 | FACT/CALCULATION | - | 없음 | - | 동결 자료 없음 | NEEDS_VERIFICATION | 금지 |
| nv-competitors | 직접 경쟁사·대체재와 비교 우위 | FACT/VALUE_JUDGMENT | - | 없음 | - | 동결 자료 없음 | NEEDS_VERIFICATION | 금지 |
| nv-culture | 실제 조직문화·평가·보상·승진 | FACT | - | 없음 | - | 동결 자료 없음 | NEEDS_VERIFICATION | 금지 |
| nv-eligibility | 지원자의 연령, 과거 KODIT 인턴 여부, 출퇴근 가능 여부, 결격사유 | FACT | 2026 채용 | SRC-05 확인 필요 목록 | - | 지원자 확인 전 | NEEDS_VERIFICATION | 지원 전 확인 |
