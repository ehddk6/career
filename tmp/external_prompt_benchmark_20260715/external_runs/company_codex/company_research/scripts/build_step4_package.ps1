param(
    [string]$RunId = "CR-20260715-1539",
    [string]$AnalyzedAt = "2026-07-15T18:20:00+09:00"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$out = Join-Path $root "company_research/step4"
$analysis = Join-Path $out "analysis"
New-Item -ItemType Directory -Force -Path $analysis | Out-Null

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

function Sha256([string]$Path) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

$sources = @(
    [ordered]@{ source_id="SRC-021"; title="중장기 경영목표(2025~2029년)"; publisher="신용보증기금·ALIO"; source_type="OFFICIAL_DISCLOSURE"; grade="A1"; url="https://www.alio.go.kr/upload/disclosure/2024/11/11/2024111102898479/doc.html"; access_status="VERIFIED"; evidence_locator="경영목표 및 전략" },
    [ordered]@{ source_id="SRC-022"; title="신용보증현황"; publisher="신용보증기금"; source_type="OFFICIAL_DISCLOSURE"; grade="A2"; url="https://www.kodit.or.kr/kodit/cm/cntnts/cntntsView.do?cntntsId=11264&mi=2896"; access_status="VERIFIED"; evidence_locator="2026-03-31 기준 보증잔액·공급현황" },
    [ordered]@{ source_id="SRC-023"; title="2,690억 원 규모 유동화수익증권 첫 직접 발행"; publisher="신용보증기금"; source_type="OFFICIAL_PRESS_RELEASE"; grade="A2"; url="https://www.kodit.or.kr/kodit/na/ntt/selectNttInfo.do?bbsId=47&mi=2639&nttSn=4899880"; access_status="VERIFIED"; evidence_locator="2026-07-02 보도자료" },
    [ordered]@{ source_id="SRC-024"; title="ETRI 사업화 유망기술 설명회"; publisher="신용보증기금"; source_type="OFFICIAL_PRESS_RELEASE"; grade="A2"; url="https://www.kodit.or.kr/kodit/na/ntt/selectNttInfo.do?bbsId=47&mi=2639&nttSn=4899954"; access_status="VERIFIED"; evidence_locator="2026-07-02 보도자료" },
    [ordered]@{ source_id="SRC-025"; title="서울대학교 AI연구원 업무협약"; publisher="신용보증기금"; source_type="OFFICIAL_PRESS_RELEASE"; grade="A2"; url="https://www.kodit.or.kr/kodit/na/ntt/selectNttInfo.do?bbsId=47&mi=2639&nttSn=4886656"; access_status="VERIFIED"; evidence_locator="2026-06-29 보도자료" },
    [ordered]@{ source_id="SRC-026"; title="산업기반신용보증 2025 실적 및 2026 계획"; publisher="신용보증기금"; source_type="OFFICIAL_DISCLOSURE"; grade="A2"; url="https://www.kodit.or.kr/kodit/cm/cntnts/cntntsView.do?cntntsId=11370&mi=2806"; access_status="VERIFIED"; evidence_locator="2025 실적·2026 보증공급 목표" }
)

$claims = @(
    [ordered]@{ claim_id="CLM-STRAT-001"; rq_ids=@("RQ-07"); domain="STRATEGY"; claim="2025~2029 중장기 전략은 미래 성장동력 확충, 금융서비스 혁신 선도, 지속가능경영 기반 조성을 3대 전략목표로 두고 9개 전략과제를 제시한다."; verification_status="CONFIRMED_PRIMARY"; confidence="HIGH"; source_ids=@("SRC-021"); evidence_locator="경영목표 및 전략"; counterevidence_or_limit="전략 공시는 방향과 목표를 확인하지만 개별 과제의 연도별 예산·인력 배분까지 보여주지는 않는다."; application_use="기관 전략 이해"; usage_restriction="전략 발표를 실행 완료로 표현 금지" },
    [ordered]@{ claim_id="CLM-EXEC-001"; rq_ids=@("RQ-05","RQ-07"); domain="OPERATING_RESULT"; claim="2026년 3월 말 신용보증 잔액은 75조 6,515억원이고, 2026년 1분기 경제활력·경제기반 분야 공급 합계는 15조 8,342억원으로 공시됐다."; verification_status="CONFIRMED_PRIMARY"; confidence="HIGH"; source_ids=@("SRC-022"); evidence_locator="2026-03-31 보증현황"; counterevidence_or_limit="1분기 공급액을 연간 실적과 직접 비교하거나 연간화하지 않는다."; application_use="실행 규모의 최신 관찰값"; usage_restriction="연간 목표 달성률·건전성 결론 산출 금지" },
    [ordered]@{ claim_id="CLM-EXEC-002"; rq_ids=@("RQ-07"); domain="EXECUTION_RESULT"; claim="신용보증기금은 2026년 6월 30일 2,690억원 규모의 유동화수익증권을 처음 직접 발행했고, 기존 SPC 방식보다 편입기업의 3년간 평균 금융비용을 111bp 낮췄다고 밝혔다."; verification_status="CONFIRMED_PRIMARY"; confidence="HIGH"; source_ids=@("SRC-023"); evidence_locator="직접 발행 결과·금융비용 효과"; counterevidence_or_limit="111bp는 기관 발표치이며 외부 독립 검증 자료는 이번 단계에서 확인하지 않았다."; application_use="금융서비스 혁신의 실행 사례"; usage_restriction="모든 유동화보증에 동일 절감효과가 발생한다고 일반화 금지" },
    [ordered]@{ claim_id="CLM-EXEC-003"; rq_ids=@("RQ-07"); domain="PARTNERSHIP_EXECUTION"; claim="신용보증기금과 ETRI는 2026년 6월 30일 설명회를 열어 약 150명에게 기술이전 정보, 금융지원 안내, IP·데이터 사업화 컨설팅과 1대1 금융상담을 제공했다."; verification_status="CONFIRMED_PRIMARY"; confidence="HIGH"; source_ids=@("SRC-024"); evidence_locator="설명회 개최 및 제공 서비스"; counterevidence_or_limit="참석 이후 기술이전·사업화·보증 실행 성과는 아직 확인되지 않았다."; application_use="공공허브·민관협력의 운영 사례"; usage_restriction="행사 개최를 사업화 성과로 치환 금지" },
    [ordered]@{ claim_id="CLM-EXEC-004"; rq_ids=@("RQ-07"); domain="DIGITAL_EXECUTION"; claim="신용보증기금은 2026년 6월 26일 서울대학교 AI연구원과 협약을 체결해 BASA, NEST AI-Lab 데이터, AI 스타트업 지원, AX 전략·AI 거버넌스 자문을 협력 범위로 정했다."; verification_status="CONFIRMED_PRIMARY"; confidence="HIGH"; source_ids=@("SRC-025"); evidence_locator="업무협약의 자원·역할 약정"; counterevidence_or_limit="공동연구 산출물, 시스템 개선, 보증·투자 성과는 아직 관찰되지 않았다."; application_use="데이터·AI 전략의 착수 증거"; usage_restriction="협약 체결을 운영성과 또는 결과 관찰로 표현 금지" },
    [ordered]@{ claim_id="CLM-EXEC-005"; rq_ids=@("RQ-07"); domain="PLAN_AND_RESOURCE"; claim="산업기반신용보증은 2025년 승인잔액 16조 4,707억원과 기본재산 1조 1,246억원을 공시했고, 2026년 보증공급 목표를 3조원으로 제시했다."; verification_status="CONFIRMED_PRIMARY"; confidence="HIGH"; source_ids=@("SRC-026"); evidence_locator="2025 실적·2026 계획"; counterevidence_or_limit="2026년 3조원은 계획값이며 실제 공급 결과가 아니다."; application_use="계획과 재원 기반의 구분"; usage_restriction="3조원을 달성 실적으로 표현 금지" },
    [ordered]@{ claim_id="CLM-RES-001"; rq_ids=@("RQ-07","RQ-12","RQ-13"); domain="PEOPLE_RESOURCE"; claim="2026년 하반기 보증 분야 청년인턴 140명 모집은 전국 100개 영업점의 기한연장·기업신용 상시관리 지원 인력을 확보하려는 채용 실행이다."; verification_status="CONFIRMED_PRIMARY"; confidence="HIGH"; source_ids=@("SRC-011","SRC-012"); evidence_locator="채용공고와 채용단위 운영현황"; counterevidence_or_limit="채용 절차가 진행 중이며 실제 충원·배치·성과는 2026년 9월 이후 확인해야 한다."; application_use="현장 운영 인력 수요 신호"; usage_restriction="현재 이미 140명이 배치됐다고 표현 금지" }
)

$timeline = @'
---
run_id: CR-20260715-1539
company_data_package_id: CR-DATA-001
step: STEP_4
---

# EVENT TIMELINE

| Event ID | 시점 | 사건 | 전략 연결 | 관찰된 자원·행동 | 관찰된 결과 | 상태 | 근거 | 한계 |
|---|---|---|---|---|---|---|---|---|
| EVT-001 | 2024-10-30 | 2025~2029 중장기 전략 수정 공시 | 3대 전략목표·9개 과제 | 목표·과제 체계 공시 | 개별 실행 결과 아님 | `ANNOUNCED` | SRC-021 | 연도별 예산·인력 배분 미확인 |
| EVT-002 | 2026-03-31 | 2026년 1분기 신용보증 현황 공시 | 미래 성장동력·정책금융 | 분야별 보증 공급 | 잔액 75조 6,515억원, 1분기 공급 15조 8,342억원 | `RESULT_OBSERVED` | SRC-022 | 분기 공급액의 연간화 금지 |
| EVT-003 | 2026-06-26 | 서울대 AI연구원과 협약 체결 | 데이터·플랫폼·DT | BASA, NEST AI-Lab 데이터, 자문·지원 역할 약정 | 협약 체결 | `STARTED` | SRC-025 | 공동 산출물·성과 미관찰 |
| EVT-004 | 2026-06-30 | ETRI 사업화 유망기술 설명회 개최 | 공공허브·협력 강화 | 설명회, 컨설팅, 1대1 상담 | 약 150명 참석·서비스 제공 | `OPERATING` | SRC-024 | 후속 사업화 결과 미관찰 |
| EVT-005 | 2026-06-30 | 유동화수익증권 첫 직접 발행 | 금융서비스 혁신·포트폴리오 다각화 | TF, 프로세스·전산 구축, 직접 발행 | 2,690억원 발행, 평균 111bp 비용절감 발표 | `RESULT_OBSERVED` | SRC-023 | 절감효과는 기관 발표치 |
| EVT-006 | 2026년 계획 | 산업기반신용보증 3조원 공급 목표 | 공공 안전망·금융 다각화 | 2025년 기본재산 1조 1,246억원 | 2026 성과는 미관찰 | `ANNOUNCED` | SRC-026 | 계획과 실적 분리 |
| EVT-007 | 2026-07-09~07-23 | 보증 분야 청년인턴 140명 모집 | 영업점 운영 인력 | 전국 100개 영업점 배치 예정 채용 | 접수 진행 | `STARTED` | SRC-011, SRC-012 | 충원·배치·성과 미관찰 |

`ANNOUNCED`는 계획 또는 목표만 확인된 경우, `STARTED`는 협약·채용 절차가 개시됐으나 운영 결과가 없는 경우에만 부여했다. 사건이 있었다는 사실과 그 사건의 성과는 분리했다.
'@

$alignment = @'
---
run_id: CR-20260715-1539
company_data_package_id: CR-DATA-001
step: STEP_4
---

# STRATEGY-RESOURCE ALIGNMENT

| 전략 방향 | 공식 전략 근거 | 확인된 자원·행동 | 확인된 결과 | 상태 | 판단 근거 | 남은 검증 |
|---|---|---|---|---|---|---|
| 미래 성장동력 확충 | 혁신성장·스케일업·정책금융 | 분야별 보증 공급, ETRI 기술사업화 연계 | 2026년 1분기 공급 공시·설명회 운영 | `ALIGNED` | 자금 공급과 운영 활동이 모두 관찰됨 | 수혜기업 성장·고용 성과 |
| 금융서비스 혁신 선도 | 융복합 금융·자본시장 연계 | 직접발행 TF, 전산·업무 프로세스 | 2,690억원 직접 발행·111bp 절감 발표 | `ALIGNED` | 자원 투입에서 결과까지 연결됨 | 절감효과 외부 검증·후속 발행 |
| 데이터·플랫폼·DT | 데이터 개방·시스템 고도화 | BASA, NEST AI-Lab, 서울대 AI 자문 약정 | 협약 체결 | `PARTIALLY_ALIGNED` | 구체 자산·역할은 확인됐으나 운영 결과 없음 | 공동연구·시스템 개선·지원 실적 |
| 공공 안전망·지속가능 기반 | 시장안정·기금 건전성·SOC | 산업기반 보증 기본재산·2026 공급목표 | 2025 실적은 확인, 2026 결과 미확인 | `PARTIALLY_ALIGNED` | 재원과 계획은 있으나 2026 실행 결과 부족 | 일반보증 재무·손실·회수 시계열 |
| 영업점 운영과 고객 서비스 | 서비스 역량·기관 효율 | 100개 영업점에 인턴 140명 채용 진행 | 아직 배치 전 | `NOT_YET_EVIDENCED` | 사람 자원 확보 절차만 시작 | 실제 충원·업무·KPI·보고선 |

## 종합 판정

전체 정렬도는 `PARTIALLY_ALIGNED`다. 직접 발행은 전략-조직/시스템-결과의 연결이 가장 강하다. AI 협약과 청년인턴 채용은 구체 자원 또는 절차가 확인되지만 결과 단계에는 이르지 않았다. 일반보증의 재무건전성, 손실·회수, 현장 인력 성과는 STEP 5 이후에도 별도 검증이 필요하다.
'@

$status = @'
---
run_id: CR-20260715-1539
company_data_package_id: CR-DATA-001
step: STEP_4
execution_assessment: PARTIALLY_EVIDENCED
---

# STRATEGY EXECUTION STATUS

## 결론

신용보증기금은 전략을 발표하는 데 그치지 않고 일부 과제에서 시스템·조직·파트너십·자본시장 실행을 관찰 가능한 결과로 연결했다. 특히 유동화수익증권 직접 발행은 TF 구성, 프로세스 설계, 전산 개발, 실제 발행과 비용절감 발표까지 연결돼 `RESULT_OBSERVED`로 판정한다. 반면 AI 협약은 착수, 청년인턴 채용은 인력 확보 절차, 2026년 산업기반보증 3조원은 계획 단계다.

## 실행 증거 강도

- 강함: 직접 발행, 2026년 1분기 보증 현황.
- 중간: ETRI 설명회 운영과 실제 상담·컨설팅 제공.
- 제한적: AI 협약의 데이터·자문 약정, 인턴 채용 절차.
- 미확인: 일반보증의 예산·인력 배분, 손실·회수 시계열, 인턴의 실제 시스템·권한·KPI.

## 반대 증거와 해석 제한

- 확인된 지연·축소·취소 사건은 없다. 다만 부재를 실행 성공의 증거로 사용하지 않는다.
- 보도자료의 성과 수치는 공식 1차 발표이지만 외부 독립 검증과 동일하지 않다.
- 2026년 1분기 공급은 연간 수치와 직접 비교하지 않는다.
- 협약, 목표, 채용공고는 결과가 아니라 각각 착수·계획·인력 확보 절차다.

## 직무 연결

100개 영업점에 보증 분야 청년인턴 140명을 배치하려는 계획은 기한연장·상시관리 지원 수요가 넓게 존재한다는 인력 신호다. 다만 개별 영업점의 업무량, 시스템 접근권한, 고객 접점, 보고선과 오류 KPI는 여전히 `NEEDS_VERIFICATION`이다. 지원자는 자료 최신성 확인과 상태 기록을 직무 가설로만 말하고, 독립 심사·승인 권한으로 확대하면 안 된다.

## 게이트

- STEP 4: `COMPLETED_WITH_GAPS`
- 실행 종합: `PARTIALLY_EVIDENCED`
- HARD FAIL: `NOT_EVALUATED_AT_STEP_4`
- 최종 의사결정: `NOT_READY`
- 다음 단계: `STEP_5_FINANCIAL_ANALYSIS`

`company_research/final/`은 최종 게이트 전이므로 생성·수정하지 않는다.
'@

$sourcePackage = [ordered]@{ schema_version=1; step="STEP_4"; run_id=$RunId; company_data_package_id="CR-DATA-001"; checked_at=$AnalyzedAt; sources=$sources }
$claimPackage = [ordered]@{ schema_version=1; step="STEP_4"; run_id=$RunId; company_data_package_id="CR-DATA-001"; claim_count=$claims.Count; claims=$claims }

Write-Utf8NoBom (Join-Path $analysis "event_timeline.md") $timeline
Write-Utf8NoBom (Join-Path $analysis "strategy_resource_alignment.md") $alignment
Write-Utf8NoBom (Join-Path $analysis "strategy_execution_status.md") $status
Write-Utf8NoBom (Join-Path $out "source_addendum.json") ($sourcePackage | ConvertTo-Json -Depth 12)
Write-Utf8NoBom (Join-Path $out "claim_updates.json") ($claimPackage | ConvertTo-Json -Depth 12)

$claimLines = @("# STEP 4 CLAIM UPDATES", "", "| Claim ID | 영역 | 요약 | 상태 | 출처 | 제한 |", "|---|---|---|---|---|---|")
foreach ($claim in $claims) {
    $claimLines += "| $($claim.claim_id) | $($claim.domain) | $($claim.claim) | ``$($claim.verification_status)`` | $($claim.source_ids -join ', ') | $($claim.usage_restriction) |"
}
Write-Utf8NoBom (Join-Path $out "claim_updates.md") ($claimLines -join "`n")

$report = @"
---
run_id: $RunId
company_data_package_id: CR-DATA-001
step: STEP_4
step_status: COMPLETED_WITH_GAPS
---

# STEP 4 EVENT AND EXECUTION ANALYSIS REPORT

## 완료 범위

- 2025~2029 중장기 전략을 기준선으로 고정했다.
- 공식 공시와 보도자료의 사건을 계획·착수·운영·결과로 분리했다.
- 전략별 자원 투입과 관찰 결과를 연결하고 과대평가 제한을 기록했다.
- 영업점 인턴 채용을 사람 자원 신호로 연결하되 실제 배치·성과와 구분했다.

## 남은 공백

- 일반보증의 최근 3개년 재무·손실·회수 시계열
- 전략과제별 연도 예산·정원·조직 배분
- AI 협약의 공동 산출물과 후속 지원 실적
- 인턴의 실제 시스템·자료 권한·고객 접점·보고선·오류 KPI
- 확인된 실행에 대한 독립 외부 검증

## 단계 판정

- STEP 4: ``COMPLETED_WITH_GAPS``
- 실행 종합: ``PARTIALLY_EVIDENCED``
- HARD FAIL: ``NOT_EVALUATED_AT_STEP_4``
- 최종 의사결정: ``NOT_READY``
- 다음 단계: ``STEP_5_FINANCIAL_ANALYSIS``

``company_research/final/``은 최종 게이트 전이므로 생성·수정하지 않았다.
"@
Write-Utf8NoBom (Join-Path $out "step4_report.md") $report

$artifactPaths = @(
    "company_research/step4/analysis/event_timeline.md",
    "company_research/step4/analysis/strategy_resource_alignment.md",
    "company_research/step4/analysis/strategy_execution_status.md",
    "company_research/step4/source_addendum.json",
    "company_research/step4/claim_updates.json",
    "company_research/step4/claim_updates.md",
    "company_research/step4/step4_report.md"
)
$artifacts = foreach ($relative in $artifactPaths) {
    $full = Join-Path $root $relative
    [ordered]@{ path=$relative; sha256=(Sha256 $full) }
}
$manifest = [ordered]@{
    schema_version=1; step="STEP_4"; step_status="COMPLETED_WITH_GAPS"; run_id=$RunId; company_data_package_id="CR-DATA-001"; analyzed_at=$AnalyzedAt
    source_addendum_count=$sources.Count; claim_update_count=$claims.Count
    event_status_counts=[ordered]@{ ANNOUNCED=2; STARTED=2; OPERATING=1; RESULT_OBSERVED=2 }
    gates=[ordered]@{ execution_assessment="PARTIALLY_EVIDENCED"; final_decision="NOT_READY"; hard_fail_status="NOT_EVALUATED_AT_STEP_4"; next_step="STEP_5_FINANCIAL_ANALYSIS"; final_directory_written=$false }
    artifacts=$artifacts
}
Write-Utf8NoBom (Join-Path $out "manifest.json") ($manifest | ConvertTo-Json -Depth 10)

Write-Output "STEP 4 package created: $out"
