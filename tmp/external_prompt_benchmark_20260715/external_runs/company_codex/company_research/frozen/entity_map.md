---
run_id: CR-20260715-1539
company_data_package_id: CR-DATA-001
company_data_package_version: "1.0"
step: STEP_1
step_status: COMPLETED_WITH_GAPS
frozen_at: 2026-07-15T16:00:22+09:00
---

# ENTITY MAP

## 판정 원칙

- 엔터티 이름과 법적 지위는 구분한다. 로컬 공고에서 기관명이 확인되어도 설립 근거와 법적 지위는 별도 공식 원문 확인 전까지 확정하지 않는다.
- KODIT, 보증 분야, 채용 접수 테넌트는 각각 브랜드·사업 범위·전달 채널 후보로 분리한다.
- 기존 자기소개서·기업조사·모델 평가에만 등장하는 관계는 엔터티 사실로 승격하지 않는다.
- 다른 기관 자료는 오염 방지를 위해 지도에 표시하되 조사 대상과 연결하지 않는다.

| ID | 이름 | 유형 | 법적 명칭 | 조사대상과 관계 | 근거 | 관계 상태 | 범위 | 비고 |
|---|---|---|---|---|---|---|---|---|
| ENT-001 | 신용보증기금 | LEGAL_ENTITY | 신용보증기금 | 조사 대상 루트 | LOC-003, URL-001, URL-003 | NAME_CONFIRMED_LEGAL_STATUS_NEEDS_VERIFICATION | 대한민국 | 로컬 공고에서 기관명은 확인. 법적 지위·설립 목적·정책금융 체계 내 역할은 STEP 2 공식 원문 검증 필요. |
| ENT-002 | 신용보증기금(KODIT) | BRAND | UNVERIFIED | ENT-001의 브랜드 후보 | URL-003 | NEEDS_VERIFICATION | 대한민국 | STEP 0 표기와 공식 도메인 출처 후보에 기반한 잠정 항목. 동일성·공식 영문명은 재검증 전 미확정. |
| ENT-003 | 보증 분야 | BUSINESS_UNIT | NOT_APPLICABLE | ENT-001 채용분야의 업무 범위 | LOC-003, URL-001 | POSTING_CONFIRMED_ORG_LEVEL_UNVERIFIED | 채용분야 | 공고상 분야명은 확인되지만 본부·영업점·팀 등 조직단위인지 여부는 미확인. |
| ENT-004 | kodit2.saramin.co.kr 채용 접수 테넌트 | UNVERIFIED | UNVERIFIED | ENT-001 공고 전달·접수 채널 후보 | URL-001 | NEEDS_VERIFICATION | 채용 접수 | 도메인만으로 운영 법인·위탁 관계를 단정하지 않는다. 고용주 엔터티와 혼동 금지. |
| ENT-005 | 한국도로공사서비스(주) | LEGAL_ENTITY | 한국도로공사서비스(주) | 조사 대상과 무관한 별도 기관 | LOC-057, LOC-058, LOC-059, LOC-060, LOC-061, LOC-062 | OUT_OF_SCOPE | 대한민국 | 직무기술서 6개를 렌더링·텍스트 확인. 신용보증기금 분석에서 제외. |

## 확인되지 않은 관계

- ENT-001의 PARENT, SUBSIDIARY, AFFILIATE, JOINT_VENTURE: UNVERIFIED
- 정확한 목표 팀·영업점·근무부점: UNVERIFIED
- ENT-001과 접수 테넌트 운영 법인의 계약·위탁 관계: UNVERIFIED
- 보증 분야가 공식 조직도상의 독립 BUSINESS_UNIT인지 여부: UNVERIFIED

## 오염 방지 결론

input/직무기술서/의 한국도로공사서비스 자료, 01_자료목록.md에만 기재된 외부 작업공간 파일, 모델 생성 자기소개서·평가 결과는 신용보증기금의 엔터티·사업·재무·문화 claim 근거로 사용하지 않는다.
