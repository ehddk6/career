---
run_id: CR-20260715-1539
company_data_package_id: CR-DATA-001
step: STEP_2
step_status: COMPLETED_WITH_GAPS
collected_at: 2026-07-15T16:45:00+09:00
---

# STEP 2 CLAIM LEDGER

## 상태 요약

- `BLOCKED_MISSING_SOURCE`: 1개
- `BLOCKED_SOURCE_NOT_EXTRACTED`: 1개
- `CONFIRMED_LOCAL`: 2개
- `CONFIRMED_PRIMARY`: 17개
- `NOT_READY`: 1개
- `PARTIAL_LOCAL`: 1개
- `UNVERIFIED`: 2개

## Claim 목록

| Claim ID | RQ | 영역 | 주장 | 상태 | 근거 | 제한 |
|---|---|---|---|---|---|---|
| CLM-COMP-001 | RQ-01 | ENTITY | 신용보증기금은 신용보증기금법에 따라 기업의 자금융통과 건전한 신용질서 확립을 통해 국민경제 발전에 기여하도록 설립된 기금이다. | `CONFIRMED_PRIMARY` | SRC-001 | 법률상 목적은 개별 사업의 실제 성과를 뜻하지 않는다. |
| CLM-COMP-002 | RQ-01, RQ-02 | BUSINESS_MODEL | 법정 목적 범위에는 기업 채무보증, 회사채 등 유동화, 신용정보의 관리·운용이 포함된다. | `CONFIRMED_PRIMARY` | SRC-001 | 세부 사업별 2026년 집행 실적은 별도 검증이 필요하다. |
| CLM-COMP-003 | RQ-02, RQ-04 | VALUE_CHAIN | 일반적인 신용보증 흐름은 신청·상담, 자료수집·신용조사, 보증심사·승인, 약정·보증서 발급으로 이어진다. | `CONFIRMED_PRIMARY` | SRC-002, SRC-003, SRC-004, SRC-005 | 공고상 인턴이 이 모든 단계를 독립 수행한다는 근거는 없다. |
| CLM-COMP-004 | RQ-03 | CUSTOMER | 보증대상은 일정 요건을 갖춘 개인기업·법인기업·기업단체이며 대기업·상장기업은 특정자금에 한해 제한적으로 허용된다. | `CONFIRMED_PRIMARY` | SRC-006 | 개별 신청기업의 지원 가능 여부는 심사 전 확정할 수 없다. |
| CLM-COMP-005 | RQ-04, RQ-10, RQ-12 | OPERATIONS | 신용조사에는 등기·행정·금융거래·국세·세무회계 자료가 사용되고, 최근 3년 재무제표 등도 수집 대상이다. | `CONFIRMED_PRIMARY` | SRC-004 | 자료 접근 권한과 인턴의 실제 취급 범위는 확인되지 않았다. |
| CLM-COMP-006 | RQ-04, RQ-10 | RISK_CONTROL | 보증심사는 사업성·미래성장성·기업가치·기술력·기업가 정신 등을 고려하고 보증금액에 따라 심사 수준이 구분된다. | `CONFIRMED_PRIMARY` | SRC-005 | 내부 세부 기준과 개별 평가 결과는 공개 근거로 확인하지 못했다. |
| CLM-COMP-007 | RQ-07 | PROGRAM | 신용보증기금은 2026년 유동화보증 신규자금 지원규모를 2.8조원으로 안내한다. | `CONFIRMED_PRIMARY` | SRC-007 | 계획 수치이며 실제 집행액이 아니다. |
| CLM-COMP-008 | RQ-07 | PROGRAM | 2026년 보증연계투자 지원규모는 673억원으로 안내되며, 신용보증과 투자를 연계해 중소기업 자금조달·재무구조 개선을 지원한다. | `CONFIRMED_PRIMARY` | SRC-008 | 계획 수치이며 실제 집행액이 아니다. |
| CLM-COMP-009 | RQ-11 | CULTURE | 공식 인재상은 기본인품과 성장자질을 축으로 책임감·열정, 혁신·소통, 논리적 사고, 문제해결 등을 제시한다. | `CONFIRMED_PRIMARY` | SRC-009 | 공식 가치 문구만으로 실제 조직문화를 확정할 수 없다. |
| CLM-COMP-010 | RQ-07, RQ-10 | GOVERNANCE | 공식 경영환경 모니터링 체계에는 거시경제·중소기업·정책·내부환경과 VOC, 고객자문단, 리스크준법실, 성과관리시스템 등이 제시된다. | `CONFIRMED_PRIMARY` | SRC-010 | 채널의 운영 빈도·효과·2026 성과는 확인되지 않았다. |
| CLM-JOB-001 | RQ-12, RQ-13 | JOB_POSTING | 체험형 청년인턴1(보증)은 140명을 모집하며 약 3개월 동안 전국 영업점 100개에서 신용보증 기한연장과 기업신용 상시관리 등을 수행한다. | `CONFIRMED_PRIMARY` | SRC-011, SRC-012 | '등'의 세부업무와 개별 배치 부점은 미확정이다. |
| CLM-JOB-002 | RQ-13 | EMPLOYMENT_TERMS | 근무기간은 2026-09-17부터 2026-12-16까지이고, 주 5일·1일 8시간, 월 225만원 수준(세전)이다. | `CONFIRMED_PRIMARY` | SRC-011 | 세후 실수령액과 개별 근무시간 선택 결과는 확정할 수 없다. |
| CLM-JOB-003 | RQ-13 | APPLICATION | 접수기간은 2026-07-09부터 2026-07-23 16:00까지이며 채용홈페이지 온라인 접수만 허용된다. | `CONFIRMED_PRIMARY` | SRC-011 | 사이트 장애 가능성이 안내되어 있고 최종 제출 완료가 필요하다. |
| CLM-JOB-004 | RQ-13 | ELIGIBILITY | 학력·성별·전공 제한은 없지만 신용보증기금 청년인턴 근무경험자는 지원할 수 없고, 마감일 기준 만 18~34세 및 채용일부터 출퇴근 가능 요건이 있다. | `CONFIRMED_PRIMARY` | SRC-011 | 지원자의 생년월일·과거 근무 여부·출퇴근 가능성은 이 조사에서 확인하지 않았다. |
| CLM-JOB-005 | RQ-13 | SELECTION | 서류는 업무수행계획서와 약식논술의 충실도·논리력·혁신적 사고를 평가하고, 면접은 기본인성과 직무능력을 평가한다. | `CONFIRMED_PRIMARY` | SRC-011 | 내부 배점표와 합격 가능성은 공개되지 않았다. |
| CLM-JOB-006 | RQ-13 | BLIND_RECRUITMENT | 업무수행계획서와 약식논술에는 이름·나이·출신지·가족관계·학교명·성별 등 블라인드 위반 정보를 기재하면 안 된다. | `CONFIRMED_PRIMARY` | SRC-011, SRC-014 | 기업명·기관명은 직무 관련 경력 확인을 위해 허용되지만 학교·지역 식별 표현은 금지된다. |
| CLM-JOB-007 | RQ-12 | PLACEMENT | 복수 근무부점 채용단위는 희망 순위를 참고하되 희망 외 부점 배치가 가능하고, 배치 후 같은 채용단위 내 타 부점 이동도 가능하다. | `CONFIRMED_PRIMARY` | SRC-011, SRC-012 | 정확한 배치 지점·팀·보고선은 합격 전 확정되지 않는다. |
| CLM-APP-001 | RQ-14 | APPLICANT_EVIDENCE | 지원자는 3,000페이지 규모 자료를 분류해 2일 만에 정리했다는 경험 문장을 현재 포함된 원문에서 확인할 수 있다. | `CONFIRMED_LOCAL` | SRC-016, SRC-017 | 자료량·기간의 외부 기록이나 산식은 별도로 확인되지 않았다. |
| CLM-APP-002 | RQ-14 | APPLICANT_EVIDENCE | 지원자는 상인 50명 인터뷰와 5개 시장 비교분석 경험 문장을 현재 포함된 원문에서 확인할 수 있다. | `CONFIRMED_LOCAL` | SRC-016, SRC-017 | 인터뷰 명단·비교표 등 별도 산출물은 현재 입력에 없다. |
| CLM-APP-003 | RQ-14 | APPLICANT_EVIDENCE | 지원자는 엑셀 자동화로 급여 산정 속도를 30% 향상했다는 경험 문장을 현재 포함된 원문에서 확인할 수 있다. | `PARTIAL_LOCAL` | SRC-016, SRC-017 | 30%의 기준선·측정기간·산식이 원장과 원문에 없다. |
| CLM-APP-004 | RQ-14 | LINEAGE_GAP | 승인 경험원장 20개 claim 중 13개는 현재 input에 없는 경험요약정리.docx 또는 인생기술서.docx를 상위 원문으로 참조한다. | `BLOCKED_MISSING_SOURCE` | SRC-016 | 승인 상태는 보존되지만 이번 패키지에서 독립 재검증할 수 없다. |
| CLM-FIN-001 | RQ-05, RQ-06 | FINANCIALS | 최근 3개 공시연도 및 2026 최신 가용 시점의 보증공급·보증잔액·대위변제·회수·사고율 추세는 이번 단계에서 확정하지 못했다. | `BLOCKED_SOURCE_NOT_EXTRACTED` | SRC-015 | 첨부 재무관리계획·감사보고서의 동일 범위 수치를 추출·대조해야 한다. |
| CLM-ROLE-001 | RQ-12 | JOB_REALITY | 인턴이 실제로 사용하는 시스템, 고객 접점 빈도, 보고선, 자료 접근권한, 오류 KPI는 공식 공고에서 확인되지 않았다. | `UNVERIFIED` | SRC-011 | 공식 FAQ·직무설명·현장 근거가 필요하다. |
| CLM-COMPARE-001 | RQ-09 | COMPARISON | 기술보증기금·지역신보·무역보험공사·기업은행과의 법적 역할·고객·재원·성과 비교는 이번 단계에서 검증 완료되지 않았다. | `UNVERIFIED` | - | 동일 기준일·동일 단위의 비교 원장이 필요하다. |
| CLM-DECISION-001 | RQ-15 | DECISION_GATE | 채용 기본조건과 직무 표면은 확인됐지만 재무·실제 직무 권한·현장문화·비교기관 근거가 남아 있어 최종 지원 우선순위는 아직 확정할 수 없다. | `NOT_READY` | SRC-011, SRC-015 | 지원자 본인의 자격·희망 근무지·기회비용도 별도 확인이 필요하다. |

## 사용 게이트

- `CONFIRMED_PRIMARY`만 회사·채용의 확정 사실로 사용한다.
- `CONFIRMED_LOCAL`과 `PARTIAL_LOCAL`은 지원자 경험으로만 사용하며 회사 사실과 섞지 않는다.
- `UNVERIFIED`와 `BLOCKED_*`는 질문·공백 목록에만 사용하고 자기소개서의 단정 문장에 사용하지 않는다.
- STEP 11 HARD FAIL은 이 단계에서 평가하지 않는다.
