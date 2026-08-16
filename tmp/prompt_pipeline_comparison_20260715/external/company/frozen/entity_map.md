# Entity Map

- 데이터 패키지: `CR-DATA-001` v1.0

| ID | 구분 | 명칭 | 관계 | 지분·통제 관계 | 주요 사업 | 채용 관련성 | 출처 | 상태 |
|---|---|---|---|---|---|---|---|---|
| ENT-01 | LEGAL_ENTITY | 신용보증기금 | 조사 대상 및 채용 주체 | NEEDS_VERIFICATION | 기업이 부담하는 채무 보증, 보증신청 후 신용조사·보증심사 | 직접 | `kodit-role-20260711`, `kodit-intern-duty-20260711` | 명칭·채용 주체 `CONFIRMED_PRIMARY`; 법적 지위·지배관계 `NEEDS_VERIFICATION` |
| ENT-02 | BUSINESS_UNIT | 보증 분야 | 채용 직무 분야 | 조직도·보고선 `NEEDS_VERIFICATION` | 신용보증 기한연장, 기업신용 상시관리 | 직접 | `kodit-intern-duty-20260711` | `CONFIRMED_PRIMARY` |
| ENT-X01 | LEGAL_ENTITY | 한국도로공사서비스(주) | 허용 입력 PDF의 발행 주체이나 조사 대상과 다름 | 조사하지 않음 | 고속도로 통행료 수납·영업소 운영 등 | 없음 | 직무기술서 PDF 6개 | `NOT_APPLICABLE`; KODIT 근거 사용 금지 |

브랜드, 모회사, 자회사, 계열사, 상장 여부, 연결·별도 재무 범위, 회사명 변경·합병·분할 이력은 동결 근거에 없어 `NEEDS_VERIFICATION`이다.
