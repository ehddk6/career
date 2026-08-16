---
run_id: CR-20260715-1539
company_data_package_id: CR-DATA-001
step: STEP_2
step_status: COMPLETED_WITH_GAPS
collected_at: 2026-07-15T16:45:00+09:00
---

# STEP 2 SOURCE COLLECTION REPORT

## 완료 범위

- 공식·법령·채용 출처 15건과 로컬 지원자 근거 2건을 source ledger로 등록했다.
- 채용공고 본문과 붙임 3건을 확인해 마감일, 근무기간, 근무지 범위, 지원자격, 전형, 블라인드 기준을 검증했다.
- 회사·직무·지원자·공백 claim을 분리하고 각 claim에 출처, locator, 반대·제약 근거, 사용 제한을 부여했다.

## 해소된 STEP 1 공백

- 지원 마감: 2026-07-23 16:00
- 근무기간: 2026-09-17~2026-12-16
- 근무 범위: 보증 분야 140명, 전국 영업점 100개, 채용단위 내 배치 변동 가능
- 지원자격·전형·블라인드 기준: 공식 공고와 붙임에서 확인

## 남은 핵심 공백

1. 최근 3개 공시연도 및 2026 최신 가용 시점의 동일 범위 재무·보증 지표
2. 인턴의 실제 시스템·자료 접근권한·고객 접점·보고선·오류 KPI
3. 공식 인재상과 구분되는 실제 조직문화 신호
4. 비교기관 4개 내외의 동일 기준 법적 역할·고객·재원·성과
5. 누락된 지원자 상위 원문 2개와 연결된 13개 claim

## 단계 판정

- STEP 2: `COMPLETED_WITH_GAPS`
- 최종 의사결정: `NOT_READY`
- HARD FAIL: `NOT_EVALUATED_AT_STEP_2`
- 다음 단계: `STEP_3_BUSINESS_AND_FINANCIAL_ANALYSIS`

`company_research/final/`은 현재 비어 있으며 최종 단계 전에는 채우지 않는다. 현재 원장은 중간 검증 산출물이며, `UNVERIFIED`·`BLOCKED_*` claim을 확정 사실로 승격하지 않는다.
