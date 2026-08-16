param(
    [string]$RunId = "CR-20260715-1539",
    [string]$AnalyzedAt = "2026-07-15T17:30:00+09:00"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$out = Join-Path $root "company_research/step3"
$analysis = Join-Path $out "analysis"
New-Item -ItemType Directory -Force -Path $analysis | Out-Null

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    [IO.File]::WriteAllText($Path, $Content.TrimStart("`r", "`n").TrimEnd() + "`n", [Text.UTF8Encoding]::new($false))
}

function Assert-Hash([string]$RelativePath, [string]$Expected) {
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $root $RelativePath)).Hash.ToLowerInvariant()
    if ($actual -ne $Expected) { throw "Upstream artifact changed: $RelativePath expected=$Expected actual=$actual" }
}

Assert-Hash "company_research/step2/source_ledger.json" "1427a4014d6ae343f999ecb80711ab98e35f329f619f6f1837cc8891a321ce6e"
Assert-Hash "company_research/step2/claim_ledger.json" "40cbb02e516cf3c31f219f78930050b59276450c8703663c52986d43b4cb55ec"
Assert-Hash "company_research/frozen/research_questions.md" "6c18876de2caba7231de8eb256029a0bab619a178668982323f4df552bc0d214"

$businessModel = @'
---
run_id: CR-20260715-1539
company_data_package_id: CR-DATA-001
step: STEP_3
analysis_status: COMPLETED_WITH_GAPS
---

# BUSINESS MODEL MAP

## 핵심 구조

신용보증기금은 담보력이 부족한 기업의 신용을 조사·심사한 뒤 채권자에게 보증서를 발급해 자금조달을 가능하게 하는 정책금융기관이다. 기업에는 담보 보완과 금융 접근성을, 금융기관에는 신용위험의 일부 이전을 제공한다. 이 설명은 법정 목적과 공개 업무흐름에 근거하며, 개별 보증의 승인이나 성과를 뜻하지 않는다.

| 요소 | 검증된 내용 | 근거 | 상태·제한 |
|---|---|---|---|
| 해결 문제 | 담보력이 약한 기업의 자금융통 제약과 정보비대칭 | SRC-001, SRC-002 | `CONFIRMED_PRIMARY`; 모든 신청기업이 지원되는 것은 아님 |
| 핵심 고객 | 요건을 갖춘 개인기업·법인기업·기업단체 | SRC-006 | `CONFIRMED_PRIMARY`; 개별 적격성은 심사 전 미확정 |
| 핵심 상대방 | 보증서를 바탕으로 대출·거래를 제공하는 은행·기업·국가 등 채권자 | SRC-002 | `CONFIRMED_PRIMARY` |
| 가치 제안 | 담보 보완, 비용 절감, 대외신용도 제고, 대표자 연대보증 부담 완화 | SRC-002 | `CONFIRMED_PRIMARY`; 효과 크기는 기업별 상이 |
| 핵심 활동 | 상담, 자료수집, 신용조사, 심사·승인, 약정·보증서 발급, 사후관리 | SRC-003~SRC-005, SRC-011 | 발급 전 단계는 확인; 사후관리 세부 절차는 `PARTIAL` |
| 위험 인수 | 보증채무 이행 가능성을 부담하고 신용조사·차등심사로 선별 | SRC-001, SRC-005 | 손실률·회수율은 STEP 5 전까지 미확정 |
| 재원 기반 | 기본재산과 보증료 등 법정·업무상 재원 | SRC-001, SRC-019 | 구조만 확인; 기간별 구성·규모는 `BLOCKED_SOURCE_NOT_EXTRACTED` |
| 사업 확장 | 유동화보증, 보증연계투자, 신용보험, 팩토링 등 | SRC-001, SRC-007, SRC-008, SRC-020 | 사업 존재·계획 확인; 성과 비교는 미실시 |
| 전달 채널 | 전국 영업조직과 비대면 신용보증 플랫폼·모바일 앱 | SRC-003, SRC-018 | 현재 공개 조직 기준; 채용 배치 100개소와 전체 110영업점은 범위가 다름 |
| 정책 성과 논리 | 보증을 통해 기업의 자금 접근성을 높이고 국민경제의 균형 발전에 기여 | SRC-001, SRC-002 | 법정 목적·인과 논리이며 실제 추가성과는 별도 검증 필요 |

## 직무 연결

공고의 `신용보증 기한연장, 기업신용 상시관리 등`은 신규 보증의 독립 심사보다 기존 보증관계의 정보 최신성·처리 정확성을 보조하는 역할로 해석하는 것이 안전하다. 다만 실제 시스템, 조회 권한, 고객 접점, 보고선과 오류 KPI는 공개 근거가 없어 `UNVERIFIED`다.
'@

$revenueLogic = @'
---
run_id: CR-20260715-1539
company_data_package_id: CR-DATA-001
step: STEP_3
analysis_status: COMPLETED_WITH_GAPS
---

# REVENUE LOGIC

## 해석 원칙

신용보증기금은 일반 기업처럼 매출 극대화만으로 평가할 수 없다. 법정 목적 수행을 위해 기본재산을 바탕으로 보증 위험을 인수하고, 보증료를 받으며, 사고 발생 시 보증채무를 이행하고 이후 회수 절차를 거치는 구조다. 따라서 `보증 공급 확대`와 `건전성 유지`를 함께 봐야 한다.

## 확인된 흐름

1. 정부·금융기관·기업 등의 출연 및 기타 방식으로 기본재산을 조성한다(SRC-001).
2. 신청기업을 조사·심사하고 승인된 보증에 대해 보증서를 발급한다(SRC-002~SRC-005).
3. 보증금액에 대해 평가등급 등에 따라 보증료를 차등 적용한다. 공식 안내 범위는 연 0.5%~3.0%, 대기업 3.5%다(SRC-019).
4. 보증사고가 현실화하면 기금의 손실부담이 발생할 수 있으므로 심사, 한도, 사후관리와 회수가 재무 지속가능성을 좌우한다. 이 문장은 제도 구조에 대한 분석이며 기간별 손실 규모는 아직 확인하지 않았다.

## 수익·비용·위험 드라이버

| 구분 | 드라이버 | 방향 | 검증 상태 |
|---|---|---|---|
| 재원 | 기본재산·출연 | 보증 공급 여력 확대 | 구조 `CONFIRMED_PRIMARY`, 규모 `UNVERIFIED` |
| 수입 | 보증료 | 보증 운용 수입 | 요율 범위 `CONFIRMED_PRIMARY`, 실제 수입 `UNVERIFIED` |
| 비용·손실 | 보증채무 이행, 운영비 | 재무여력 감소 | 구조적 위험만 확인, 금액 `BLOCKED` |
| 회수 | 구상권 등 사후 회수 | 손실 일부 상쇄 | 법정 업무 구조만 확인, 회수율 `BLOCKED` |
| 위험량 | 보증잔액·신규 공급 | 정책효과와 위험노출 동시 확대 | 시계열 `BLOCKED_SOURCE_NOT_EXTRACTED` |
| 위험도 | 사고율·대위변제율 | 상승 시 손실 압력 | 시계열 `BLOCKED_SOURCE_NOT_EXTRACTED` |

## 금지 결론

- 보증 공급 증가만으로 성과 개선이라 단정하지 않는다.
- 보증료율 범위를 평균 수익률로 사용하지 않는다.
- 계획 규모를 실제 집행액으로 바꾸지 않는다.
- 재무관리계획·감사보고서 수치 추출 전에는 성장률, 손실률, 회수율, 재무건전성을 계산하지 않는다.
'@

$valueChain = @'
---
run_id: CR-20260715-1539
company_data_package_id: CR-DATA-001
step: STEP_3
analysis_status: COMPLETED_WITH_GAPS
---

# VALUE CHAIN MAP

```text
기업의 자금·거래 필요
  → 보증 신청·상담
  → 자료 제출·수집
  → 신용조사·신용평가
  → 보증심사·승인
  → 약정 체결·보증서 발급
  → 금융기관 등의 대출·거래 실행
  → 기한연장·기업신용 상시관리
  → 정상 종료 또는 사고 대응·회수
```

| 단계 | 입력 | 핵심 판단·활동 | 출력 | 주요 위험 | 근거·상태 |
|---|---|---|---|---|---|
| 신청·상담 | 기업현황, 신청금액 | 신용상태와 신청 적정성 사전검토 | 접수·추가자료 요청 | 부정확한 초기정보 | SRC-003; `CONFIRMED_PRIMARY` |
| 자료수집 | 등기·세무·재무·금융자료 | 자료 완전성·최신성 확인 | 조사자료 | 누락·오입력·개인정보 위험 | SRC-004; `CONFIRMED_PRIMARY` |
| 조사·심사 | 수집자료, 현장정보 | 신용평가, 검토표, 사업성·성장성 판단 | 승인 여부·금액 | 정보비대칭·판단오류 | SRC-004, SRC-005; `CONFIRMED_PRIMARY` |
| 약정·발급 | 승인 결과 | 전자약정, 보증료 적용, 보증서 발급 | 보증관계 성립 | 조건·금액 오류 | SRC-019; `CONFIRMED_PRIMARY` |
| 대출·거래 | 보증서 | 채권자의 대출·거래 실행 | 기업 자금조달 | 용도·상환 위험 | SRC-002; `CONFIRMED_PRIMARY` |
| 사후관리 | 기존 보증·기업 변동정보 | 기한연장, 신용상태 갱신·이상징후 관리 | 갱신·조치 기록 | 최신성 누락·지연 | SRC-011; 세부 절차 `UNVERIFIED` |
| 사고·회수 | 채무불이행·보증사고 | 보증채무 이행 및 회수 | 손실·회수 | 대위변제·회수 부족 | SRC-001; 수치 `BLOCKED` |

## 체험형 인턴의 안전한 위치 지정

확정 가능한 범위는 `기한연장과 기업신용 상시관리 등`이다. 자료 확인, 변동 탐지, 처리상태 기록, 고객 안내 보조와 연결될 가능성은 있지만, 이는 직무 가설이다. 심사·승인·등급 산출·독립 고객판단 권한은 근거가 없으므로 부여하지 않는다.
'@

$customerMap = @'
---
run_id: CR-20260715-1539
company_data_package_id: CR-DATA-001
step: STEP_3
analysis_status: COMPLETED_WITH_GAPS
---

# CUSTOMER MAP

| 고객·이해관계자 | 해결하려는 문제 | 제공 가치 | 접점 | 중요 정보 | 미확인·제한 |
|---|---|---|---|---|---|
| 담보력이 부족한 개인·법인기업 | 대출·거래에 필요한 담보와 신뢰 부족 | 보증을 통한 금융·거래 접근성 | 플랫폼·앱·영업점 상담 | 사업·재무·세무·신용 자료 | 모든 기업이 자동 대상은 아님 |
| 성장유망 중소·중견기업 | 성장자금과 자본시장 접근 | 일반보증, 유동화보증, 보증연계투자 등 | 담당 조직·영업점 | 성장성·기업가치·기술력 | 상품별 대상·한도 상이 |
| 은행 등 채권자 | 차주의 신용위험 관리 | 보증서를 통한 위험 일부 이전 | 전자 보증서·업무 채널 | 승인조건·보증금액·기간 | 실제 위험분담률은 상품별 확인 필요 |
| 정책당국·국민 | 정책목표 달성과 기금 건전성 | 기업 자금융통, 경제안전망, 책임 있는 위험관리 | 공시·감사·성과관리 | 공급·사고·대위변제·회수 | 최신 시계열 미추출 |
| 기존 보증기업 | 만기·조건 변경과 신용정보 갱신 | 기한연장·상시관리의 정확하고 신속한 처리 | 영업점·전화·비대면 채널 | 최신 재무·변동·상환 정보 | 인턴의 고객접점 빈도·권한 미확인 |

## 고객 관점의 핵심 긴장

- 고객은 빠른 처리를 원하지만 기금은 공적 재원을 보호하기 위해 충분한 자료와 심사가 필요하다.
- 금융 접근성 확대는 정책효과를 높이지만 위험노출도 키울 수 있다.
- 비대면 제출은 편의성을 높이지만 자료 품질·개인정보·시스템 통제의 중요성을 높인다.
'@

$organizationMap = @'
---
run_id: CR-20260715-1539
company_data_package_id: CR-DATA-001
step: STEP_3
analysis_status: COMPLETED_WITH_GAPS
---

# ORGANIZATION MAP

## 공개 조직 구조

2026-07-15 확인 기준 공식 조직안내는 본부 `4부문 16부 6실`, 영업조직 `9영업본부, 110영업점, 15재기지원단, 11채권관리단`을 제시한다(SRC-018).

```text
이사장
├─ 이사회·운영위원회
├─ 전무이사
│  ├─ 경영기획부문: 경영기획·성과관리·ICT전략
│  ├─ 신용사업부문: 신용보증·자본시장·창업·플랫폼금융·빅데이터
│  ├─ 전략사업부문: 신용보험·기업개선·인프라금융
│  └─ 경영지원부문: 인재·업무·고객·안전
├─ 영업본부
│  ├─ 영업점
│  ├─ 재기지원단
│  └─ 채권관리단
└─ 감사 및 미래전략·리스크준법·홍보 등 독립/직속 조직
```

## 목표 직무와 조직의 연결

- 채용공고는 보증 분야 인턴을 전국 영업점 100개에 배치한다고 밝힌다(SRC-011, SRC-012).
- 공식 조직안내의 `110영업점`은 전체 조직 수이고, 채용공고의 `100개`는 이번 채용 배치 대상 수다. 두 수치를 충돌로 보거나 동일하게 치환하지 않는다.
- 신용사업부문과 영업점이 보증 업무의 정책·현장 실행 축으로 보이지만, 인턴의 정확한 소속 팀과 보고선은 합격·배치 전 `UNVERIFIED`다.
- 리스크준법실·성과관리부·ICT전략부·플랫폼금융부 등은 통제·성과·디지털 채널의 조직적 뒷받침을 보여준다. 다만 인턴이 이 조직들과 직접 협업한다고 단정할 수 없다.

## 남은 확인 질문

1. 배치 영업점에서 기한연장·상시관리의 담당 파트와 결재선은 무엇인가?
2. 인턴이 접근 가능한 시스템·문서 종류와 개인정보 마스킹 수준은 무엇인가?
3. 일일·주간 처리량, 오류 기준, 고객 안내 범위는 어떻게 정해지는가?
'@

Write-Utf8NoBom (Join-Path $analysis "business_model_map.md") $businessModel
Write-Utf8NoBom (Join-Path $analysis "revenue_logic.md") $revenueLogic
Write-Utf8NoBom (Join-Path $analysis "value_chain_map.md") $valueChain
Write-Utf8NoBom (Join-Path $analysis "customer_map.md") $customerMap
Write-Utf8NoBom (Join-Path $analysis "organization_map.md") $organizationMap

$sourceAddendum = [ordered]@{
    schema_version = 1; step = "STEP_3"; run_id = $RunId; company_data_package_id = "CR-DATA-001"; checked_at = $AnalyzedAt
    sources = @(
        [ordered]@{ source_id="SRC-018"; title="조직 안내"; publisher="신용보증기금"; source_type="OFFICIAL_WEB"; grade="A2"; url="https://www.kodit.or.kr/kodit/cm/cntnts/cntntsView.do?cntntsId=11149&mi=2456"; access_status="VERIFIED"; evidence_locator="조직도 및 조직·직원안내" },
        [ordered]@{ source_id="SRC-019"; title="보증서 발급"; publisher="신용보증기금"; source_type="OFFICIAL_WEB"; grade="A2"; url="https://www.kodit.or.kr/kodit/cm/cntnts/cntntsView.do?cntntsId=11070&mi=2529"; access_status="VERIFIED"; evidence_locator="약정체결과 보증서 발급·보증료" },
        [ordered]@{ source_id="SRC-020"; title="개요 및 연혁"; publisher="신용보증기금"; source_type="OFFICIAL_WEB"; grade="A2"; url="https://www.kodit.or.kr/kodit/cm/cntnts/cntntsView.do?cntntsId=11146&mi=2450"; access_status="VERIFIED"; evidence_locator="주요 사업 및 연혁" }
    )
}
Write-Utf8NoBom (Join-Path $out "source_addendum.json") ($sourceAddendum | ConvertTo-Json -Depth 8)

$claimUpdates = [ordered]@{
    schema_version = 1; step = "STEP_3"; run_id = $RunId; company_data_package_id = "CR-DATA-001"; claim_count = 5
    claims = @(
        [ordered]@{ claim_id="CLM-COMP-011"; rq_ids=@("RQ-02","RQ-06"); domain="FUNDING_LOGIC"; claim="신용보증기금의 보증 운용은 기본재산을 재산적 기초로 삼고 승인 보증에 보증료를 부과하는 구조다."; verification_status="CONFIRMED_PRIMARY"; confidence="HIGH"; source_ids=@("SRC-001","SRC-019"); evidence_locator="신용보증기금법 기본재산 정의·조성 및 공식 보증서 발급 안내"; counterevidence_or_limit="재원별 금액·비중과 실제 보증료 수입은 아직 추출하지 않았다."; application_use="기관의 정책금융 운영 원리 설명"; usage_restriction="보증료율을 평균 수익률로 사용 금지" },
        [ordered]@{ claim_id="CLM-COMP-012"; rq_ids=@("RQ-02","RQ-04"); domain="RISK_SHARING"; claim="보증은 신청기업을 조사·심사한 뒤 채권자에게 보증서를 발급해 기업의 자금조달을 돕고 채권자의 신용위험 일부를 기금으로 이전하는 구조다."; verification_status="CONFIRMED_PRIMARY"; confidence="HIGH"; source_ids=@("SRC-002","SRC-003","SRC-005"); evidence_locator="신용보증 기본구조·업무흐름·심사"; counterevidence_or_limit="상품별 보증비율과 손실분담은 동일하지 않다."; application_use="사업모델과 고객가치 설명"; usage_restriction="기금이 위험 전부를 부담한다고 표현 금지" },
        [ordered]@{ claim_id="CLM-COMP-013"; rq_ids=@("RQ-04","RQ-12"); domain="ORGANIZATION"; claim="공식 조직안내는 4부문 16부 6실과 9영업본부·110영업점·15재기지원단·11채권관리단을 제시한다."; verification_status="CONFIRMED_PRIMARY"; confidence="HIGH"; source_ids=@("SRC-018"); evidence_locator="조직·직원안내"; counterevidence_or_limit="조직은 개편될 수 있으며 인턴 채용 배치 대상은 별도 공고상 100개 영업점이다."; application_use="본부 정책과 영업점 실행 구조 이해"; usage_restriction="인턴의 실제 팀·보고선으로 치환 금지" },
        [ordered]@{ claim_id="CLM-COMP-014"; rq_ids=@("RQ-03","RQ-04"); domain="CUSTOMER_VALUE"; claim="공식 안내는 보증 이용 가치로 담보문제 해소, 비용절감, 대외신용도 제고, 기업경영 부담 완화를 제시한다."; verification_status="CONFIRMED_PRIMARY"; confidence="HIGH"; source_ids=@("SRC-002"); evidence_locator="보증이용에 따른 장점"; counterevidence_or_limit="효과의 크기와 실현 여부는 기업·상품별로 다르다."; application_use="고객 관점의 지원동기"; usage_restriction="모든 고객에게 동일 효과가 발생한다고 단정 금지" },
        [ordered]@{ claim_id="CLM-ROLE-002"; rq_ids=@("RQ-12"); domain="JOB_HYPOTHESIS"; claim="기한연장·기업신용 상시관리 업무는 기존 보증관계의 자료 최신성, 변동 탐지, 처리상태 기록을 지원할 가능성이 높다."; verification_status="INFERRED_NEEDS_VERIFICATION"; confidence="MEDIUM"; source_ids=@("SRC-003","SRC-004","SRC-011"); evidence_locator="공개 보증 흐름과 채용공고 업무를 결합한 분석"; counterevidence_or_limit="공식 직무분장·FAQ·현장 근거가 없어 실제 활동과 권한을 확정할 수 없다."; application_use="면접 질문·입사 후 확인 항목"; usage_restriction="확정 직무나 독립 판단 권한으로 표현 금지" }
    )
}
Write-Utf8NoBom (Join-Path $out "claim_updates.json") ($claimUpdates | ConvertTo-Json -Depth 10)

$claimMd = @'
# STEP 3 CLAIM UPDATES

| Claim ID | 영역 | 주장 요약 | 상태 | 근거 | 제한 |
|---|---|---|---|---|---|
| CLM-COMP-011 | 재원 논리 | 기본재산을 기초로 보증료를 부과하는 구조 | `CONFIRMED_PRIMARY` | SRC-001, SRC-019 | 재원 구성·실제 수입 미추출 |
| CLM-COMP-012 | 위험분담 | 조사·심사 후 보증서로 자금조달과 위험 이전 지원 | `CONFIRMED_PRIMARY` | SRC-002, SRC-003, SRC-005 | 상품별 분담률 상이 |
| CLM-COMP-013 | 조직 | 4부문 16부 6실, 9영업본부·110영업점 등 | `CONFIRMED_PRIMARY` | SRC-018 | 채용 배치 100개소와 범위 구분 |
| CLM-COMP-014 | 고객가치 | 담보 보완·비용 절감·신용도 제고·부담 완화 | `CONFIRMED_PRIMARY` | SRC-002 | 개별 효과 미확정 |
| CLM-ROLE-002 | 직무가설 | 기한연장·상시관리는 최신성·변동·상태기록 보조 가능성 | `INFERRED_NEEDS_VERIFICATION` | SRC-003, SRC-004, SRC-011 | 공식 직무분장 미확보 |

STEP 2의 `CLM-FIN-001`, `CLM-ROLE-001`, `CLM-COMPARE-001`, `CLM-APP-004`는 해소되지 않았다. 이들을 확정 사실로 승격하지 않는다.
'@
Write-Utf8NoBom (Join-Path $out "claim_updates.md") $claimMd

$report = @'
---
run_id: CR-20260715-1539
company_data_package_id: CR-DATA-001
step: STEP_3
step_status: COMPLETED_WITH_GAPS
---

# STEP 3 BUSINESS AND FINANCIAL LOGIC REPORT

## 완료 범위

- 사업모델, 재원·수익 논리, 가치사슬, 고객, 조직 구조를 공식 1차 출처에 연결했다.
- STEP 2 원장에 공식 조직·보증료·사업연혁 출처 3건을 추가하고 claim 5건을 기록했다.
- 사실, 분석적 추론, 미확인 직무 가설을 분리했다.

## 남은 공백

- 최근 3개 공시연도와 2026 최신 가용 시점의 보증공급·잔액·사고·대위변제·회수 시계열
- 인턴의 실제 시스템, 자료 접근권한, 고객 접점, 보고선과 오류 KPI
- 사후관리·기한연장의 공식 세부 업무흐름
- 비교기관과 실제 조직문화 근거

## 단계 판정

- STEP 3: `COMPLETED_WITH_GAPS`
- HARD FAIL: `NOT_EVALUATED_AT_STEP_3`
- 최종 의사결정: `NOT_READY`
- 다음 단계: `STEP_4_EVENT_AND_EXECUTION_ANALYSIS`

`company_research/final/`은 최종 게이트 전이므로 생성·수정하지 않았다.
'@
Write-Utf8NoBom (Join-Path $out "step3_report.md") $report

$artifactPaths = @(
    "company_research/step3/analysis/business_model_map.md",
    "company_research/step3/analysis/revenue_logic.md",
    "company_research/step3/analysis/value_chain_map.md",
    "company_research/step3/analysis/customer_map.md",
    "company_research/step3/analysis/organization_map.md",
    "company_research/step3/source_addendum.json",
    "company_research/step3/claim_updates.json",
    "company_research/step3/claim_updates.md",
    "company_research/step3/step3_report.md"
)
$artifacts = foreach ($relative in $artifactPaths) {
    [ordered]@{ path=$relative; sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $root $relative)).Hash.ToLowerInvariant() }
}
$manifest = [ordered]@{
    schema_version=1; step="STEP_3"; step_status="COMPLETED_WITH_GAPS"; run_id=$RunId; company_data_package_id="CR-DATA-001"; analyzed_at=$AnalyzedAt
    source_addendum_count=3; claim_update_count=5
    gates=[ordered]@{ final_decision="NOT_READY"; hard_fail_status="NOT_EVALUATED_AT_STEP_3"; next_step="STEP_4_EVENT_AND_EXECUTION_ANALYSIS"; final_directory_written=$false }
    artifacts=@($artifacts)
}
Write-Utf8NoBom (Join-Path $out "manifest.json") ($manifest | ConvertTo-Json -Depth 8)

Write-Output "STEP_3 package built: $out"
