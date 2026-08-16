# Claim Ledger

- 데이터 패키지: `CR-DATA-001` v1.0
- 조사 기준일: 2026-07-15
- 외부 네트워크 사용: 없음

| Claim ID | 주장 | 주장 유형 | 대상 기간 | 출처 | 출처 수준 | 근거 위치 | 반대 근거·한계 | 상태 | 본문 사용 |
|---|---|---|---|---|---|---|---|---|---|
| KAKAO-SCOPE-001 | 조사 목표명은 `카카오`다. | FACT | 2026-07-15 | CTRL-001 | 내부 통제 | `frozen/research_questions.md` | 법인·브랜드는 확정하지 못함 | CONFIRMED_PRIMARY | 목표명 표시에만 가능 |
| KAKAO-ENTITY-001 | 카카오의 정확한 법인명 | FACT | 기준일 | 없음 | 없음 | 없음 | 동명·계열사 혼동 가능 | NEEDS_VERIFICATION | 금지 |
| KAKAO-POSTING-001 | 카카오 지원 공고의 법인·사업부·직무·팀·게시일·마감일 | FACT | 기준일 | 없음 | 없음 | 없음 | KODIT 공고만 존재 | NEEDS_VERIFICATION | 금지 |
| KAKAO-BIZ-001 | 카카오의 고객·제품·수익모델·비용구조 | FACT | 최근 | 없음 | 없음 | 없음 | 대상 법인·사업 범위 미확정 | NEEDS_VERIFICATION | 금지 |
| KAKAO-STRAT-001 | 카카오의 최근 3개년 전략과 자원 배분 | COMPANY_CLAIM/FACT | 최근 3개년 | 없음 | 없음 | 없음 | 발표·투자·실행·성과 자료 없음 | NEEDS_VERIFICATION | 금지 |
| KAKAO-FIN-001 | 카카오의 재무·운영 수치와 추세 | FACT/CALCULATION | 최근 3개년 | 없음 | 없음 | 없음 | 연결·별도·기간·통화 미확정 | NEEDS_VERIFICATION | 금지 |
| KAKAO-PEER-001 | 카카오의 경쟁사·대체재·비교 우위 | FACT/VALUE_JUDGMENT | 기준일 | 없음 | 없음 | 없음 | 고객·제품·사업 범위 미확정 | NEEDS_VERIFICATION | 금지 |
| KAKAO-CULT-001 | 카카오의 실제 조직문화·평가·보상·승진·근무제도 | FACT | 기준일 | 없음 | 없음 | 없음 | 공식·독립·후기 자료 모두 없음 | NEEDS_VERIFICATION | 금지 |
| APP-001 | 동일 데이터를 기존 엑셀 수식과 외주 프로그램에 입력해 결과 비교 분석 보고서를 작성하고 팀장에게 보고했다. | FACT | 기간 UNVERIFIED | APP-001 | APPLICANT | `clm_3e69991c9b56d728b429` | 보고 후 조치·성과 미상 | CONFIRMED_PRIMARY | 지원자 사실로 가능 |
| APP-002 | 3,000페이지 자료를 체계적으로 분류해 2일 만에 정리했다. | FACT | 기간 UNVERIFIED | APP-001 + APP-002 | APPLICANT | `clm_88cfeab230789e5b0d5f`; raw DOCX p456 | 기여 범위·품질지표 미상 | CONFIRMED_PRIMARY | 범위 그대로 가능 |
| APP-003 | 상인 50명 인터뷰와 5개 타 시장 비교로 문제점·개선안을 도출했다. | FACT | 기간 UNVERIFIED | APP-001 + APP-002 | APPLICANT | `clm_abaa19a532d1aabc9140`; raw DOCX p152 | 실행·성과는 미확인 | CONFIRMED_PRIMARY | 조사 행동까지만 가능 |
| APP-004 | 과거 데이터를 분석해 목표 고객군을 50~70대 중장년층으로 재설정했다. | FACT | 기간 UNVERIFIED | APP-001 | APPLICANT | `clm_2bfba21afb61776d752b` | 재설정 이후 성과 미상 | CONFIRMED_PRIMARY | 행동까지만 가능 |
| APP-005 | 엑셀 자동화를 도입해 급여 산정 속도를 30% 높였다. | FACT | 기간 UNVERIFIED | APP-001 + APP-002 | APPLICANT | `clm_353c575898c6254492e8`; raw DOCX p570 | 측정 기준·기간 미상 | CONFIRMED_PRIMARY | 수치는 한계 병기 |
| BRIDGE-001 | 위 경험이 카카오 목표 직무에 직접 적합하다. | INFERENCE | 향후 | APP-001~005 | APPLICANT ONLY | 직무 근거 없음 | 같은 행동이 필요하다는 공고가 없음 | NEEDS_VERIFICATION | 직접 적합 단정 금지 |
| OFF-KODIT-001 | 신용보증기금 보증 인턴의 주요업무는 신용보증 기한연장·기업신용 상시관리다. | FACT | 2026-07-09 | KODIT package | LEVEL 2 | `input/career_run/04_공식근거.json` | 카카오와 대상 불일치 | NOT_APPLICABLE | 카카오 본문 금지 |
| OFF-EXS-001 | 한국도로공사서비스 상담·영업 직무는 통행료·고객 응대 등을 수행한다. | COMPANY_CLAIM | 발표일 UNVERIFIED | EXSERVICE PDFs | LEVEL 2 | `input/직무기술서/` | 카카오와 대상 불일치 | NOT_APPLICABLE | 카카오 본문 금지 |
