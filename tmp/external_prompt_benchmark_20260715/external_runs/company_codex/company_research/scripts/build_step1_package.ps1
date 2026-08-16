[CmdletBinding()]
param(
    [string]$RunId = "CR-20260715-1539",
    [string]$DataPackageId = "CR-DATA-001",
    [string]$DataPackageVersion = "1.0",
    [string]$FrozenAt = "2026-07-15T16:00:22+09:00"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$inputRoot = Join-Path $repoRoot "input"
$frozenRoot = Join-Path $repoRoot "company_research\frozen"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-Utf8NoBom {
    param([string]$Path, [string]$Content)
    [IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Get-MediaType {
    param([string]$Extension)
    switch ($Extension.ToLowerInvariant()) {
        ".json" { "application/json" }
        ".md"   { "text/markdown" }
        ".docx" { "application/vnd.openxmlformats-officedocument.wordprocessingml.document" }
        ".pdf"  { "application/pdf" }
        ".png"  { "image/png" }
        ".jpg"  { "image/jpeg" }
        default  { "application/octet-stream" }
    }
}

function Get-Classification {
    param([string]$RelativePath)

    $p = $RelativePath.Replace("\", "/")
    $class = "DERIVED_OTHER"
    $role = "OTHER_DERIVED_ARTIFACT"
    $entity = "MIXED_OR_UNVERIFIED"
    $period = "UNVERIFIED"
    $usability = "CONTEXT_ONLY"
    $status = "DERIVED_NOT_EVIDENCE"
    $sensitivity = "NORMAL"
    $note = "기존 실행의 파생 산출물. 자체만으로 사실을 확정하지 않는다."

    if ($p -eq "input/career_run/00_채용공고원문/source.docx") {
        $class = "LOCAL_PRIMARY_SNAPSHOT"
        $role = "JOB_POSTING_EXCERPT"
        $entity = "신용보증기금"
        $period = "2026-07-09"
        $usability = "CORE_LOCAL_EVIDENCE"
        $status = "USER_ATTESTED_NEEDS_REVERIFICATION"
        $note = "기관명·채용분야·담당업무·문항을 담은 로컬 스냅샷. 전체 공고가 아니며 공식 원문 현재성은 미검증."
    }
    elseif ($p -eq "input/career_run/02_확정경험원장.json") {
        $class = "APPROVED_APPLICANT_LEDGER"
        $role = "APPLICANT_CLAIM_LEDGER"
        $entity = "지원자"
        $period = "UNVERIFIED"
        $usability = "APPLICANT_EVIDENCE_WITH_LINEAGE_GAPS"
        $status = "PARTIAL_LOCAL_LINEAGE"
        $sensitivity = "SENSITIVE_APPLICANT_DATA"
        $note = "20개 confirmed claim. 7개는 현재 포함된 경험정리.docx, 13개는 현재 없는 상위 원문 2개를 참조."
    }
    elseif ($p -eq "input/경험정리/경험정리.docx") {
        $class = "APPLICANT_SOURCE"
        $role = "APPLICANT_NARRATIVE_SOURCE"
        $entity = "지원자"
        $period = "UNVERIFIED"
        $usability = "APPLICANT_BRIDGE_ONLY"
        $status = "LOCAL_SOURCE_PRESENT"
        $sensitivity = "SENSITIVE_APPLICANT_DATA"
        $note = "경험원장 7개 claim의 직접 원문과 SHA-256이 일치. 문서 내 다른 수치·성과는 별도 검증 필요."
    }
    elseif ($p -eq "input/경험정리/0113_dl_51_sb (1) (1).jpg") {
        $class = "PII_IMAGE"
        $role = "APPLICANT_PORTRAIT"
        $entity = "지원자"
        $usability = "EXCLUDED"
        $status = "PROHIBITED_FOR_COMPANY_RESEARCH"
        $sensitivity = "DIRECT_PII"
        $note = "증명사진. 기업·직무 조사와 무관하며 사용 금지."
    }
    elseif ($p -like "input/직무기술서/*.pdf") {
        $class = "OUT_OF_SCOPE_OFFICIAL_DOCUMENT"
        $role = "OTHER_EMPLOYER_JOB_DESCRIPTION"
        $entity = "한국도로공사서비스(주)"
        $period = "UNVERIFIED"
        $usability = "EXCLUDED_ENTITY_MISMATCH"
        $status = "OUT_OF_SCOPE"
        $note = "렌더링과 텍스트 확인 결과 한국도로공사서비스 직무설명자료. 신용보증기금 분석에서 제외."
    }
    elseif ($p -like "input/career_run/rendered_docx/*" -or $p -like "input/career_run/rendered_docx_final/*") {
        $class = "DISPLAY_DERIVATIVE"
        $role = "APPLICATION_RENDER"
        $entity = "신용보증기금 지원서"
        $period = "2026-07-14..2026-07-15"
        $usability = "VISUAL_QA_ONLY"
        $status = "DERIVED_NOT_EVIDENCE"
        $sensitivity = "SENSITIVE_APPLICANT_DATA"
        $note = "자기소개서 DOCX의 PDF·이미지 렌더링. 원문 사실 근거로 사용하지 않는다."
    }
    elseif ($p -eq "input/career_run/00_채용공고분석.json" -or $p -eq "input/career_run/00_채용공고분석.md") {
        $class = "DERIVED_STRUCTURED_EXTRACTION"
        $role = "POSTING_EXTRACTION"
        $entity = "신용보증기금"
        $period = "2026-07-09"
        $usability = "SUPPORTING_TRACE_ONLY"
        $status = "TRACEABLE_TO_LOCAL_SNAPSHOT"
        $note = "공고 스냅샷에서 추출한 파생 구조화 자료. 원문 스냅샷이 우선한다."
    }
    elseif ($p -eq "input/career_run/01_자료목록.md") {
        $class = "DERIVED_WORKSPACE_INVENTORY"
        $role = "HISTORICAL_FILE_CATALOG"
        $entity = "다수 기관·지원자 자료"
        $period = "UNVERIFIED"
        $usability = "CATALOG_ONLY"
        $status = "REFERENCED_FILES_NOT_PRESENT"
        $sensitivity = "SENSITIVE_PATH_CATALOG"
        $note = "상위 취업 작업공간의 과거 목록. 목록에 적힌 파일을 현재 패키지의 실재 소스로 간주하지 않는다."
    }
    elseif ($p -eq "input/career_run/04_공식근거.json") {
        $class = "DERIVED_RESEARCH_LEDGER"
        $role = "EXTERNAL_SOURCE_LEADS"
        $entity = "신용보증기금·한국은행"
        $period = "2026-03-12..2026-07-13"
        $usability = "SOURCE_DISCOVERY_LEADS_ONLY"
        $status = "NEEDS_REVERIFICATION"
        $note = "기존 실행의 5개 claim과 4개 고유 URL. 이번 STEP 1에서 외부 원문을 재접속하지 않음."
    }
    elseif ($p -eq "input/career_run/04_기업직무조사.md" -or $p -eq "input/career_run/04_리서치실행.json") {
        $class = "DERIVED_RESEARCH_OUTPUT"
        $role = "PRIOR_COMPANY_RESEARCH"
        $entity = "신용보증기금·한국은행"
        $period = "2026-03..2026-07-13"
        $usability = "HYPOTHESIS_AND_SOURCE_DISCOVERY_ONLY"
        $status = "NEEDS_REVERIFICATION"
        $note = "기존 조사 결과·실행 기록. 현재 원문 검증 전에는 claim 근거가 아니다."
    }
    elseif ($p -like "input/career_run/03_경험직무매칭.*") {
        $class = "DERIVED_APPLICANT_ANALYSIS"
        $role = "EXPERIENCE_JOB_MATCHING"
        $entity = "지원자·신용보증기금"
        $usability = "HYPOTHESIS_ONLY"
        $status = "DERIVED_NOT_EVIDENCE"
        $sensitivity = "SENSITIVE_APPLICANT_DATA"
        $note = "지원자 경험과 직무의 기존 매칭. STEP 10 전 재검증 필요."
    }
    elseif ($p -like "input/career_run/05_*") {
        $class = "METHODOLOGY_GUIDANCE"
        $role = "WRITING_STRATEGY"
        $entity = "지원서 작성 프레임"
        $usability = "METHOD_ONLY"
        $status = "NOT_FACT_EVIDENCE"
        $note = "작성 전략·프레임. 회사 사실 또는 경험 사실의 근거가 아니다."
    }
    elseif ($p -like "input/career_run/rigorous/candidates/*") {
        $class = "MODEL_GENERATED_DERIVATIVE"
        $role = "APPLICATION_CANDIDATE"
        $entity = "신용보증기금 지원서"
        $period = "2026-07-14"
        $usability = "EXCLUDED_AS_EVIDENCE"
        $status = "MODEL_OUTPUT"
        $sensitivity = "SENSITIVE_APPLICANT_DATA"
        $note = "모델 생성 자기소개서 후보. 회사·경험 사실의 상위 근거로 승격 금지."
    }
    elseif ($p -like "input/career_run/rigorous/judges/*") {
        $class = "MODEL_EVALUATION_DERIVATIVE"
        $role = "APPLICATION_JUDGE_OUTPUT"
        $entity = "신용보증기금 지원서"
        $period = "2026-07-14"
        $usability = "PROCESS_AUDIT_ONLY"
        $status = "MODEL_OUTPUT"
        $sensitivity = "SENSITIVE_APPLICANT_DATA"
        $note = "모델 평가 결과. 사실 확인을 대체하지 않는다."
    }
    elseif ($p -like "input/career_run/rigorous/*") {
        $class = "PIPELINE_METADATA"
        $role = "RIGOROUS_SELECTION_LINEAGE"
        $entity = "신용보증기금 지원서"
        $period = "2026-07-14..2026-07-15"
        $usability = "PROCESS_LINEAGE_ONLY"
        $status = "DERIVED_NOT_EVIDENCE"
        $sensitivity = "SENSITIVE_APPLICANT_DATA"
        $note = "후보 선택·합성·패키지 메타데이터. 회사 사실 근거가 아니다."
    }
    elseif ($p -match "input/career_run/(06_자기소개서|08_면접대비팩|draft|draft_final)") {
        $class = "APPLICATION_OUTPUT"
        $role = "SELF_INTRODUCTION_OR_INTERVIEW_DRAFT"
        $entity = "신용보증기금 지원서"
        $period = "2026-07-14..2026-07-15"
        $usability = "CLAIM_DISCOVERY_ONLY"
        $status = "DERIVED_NOT_EVIDENCE"
        $sensitivity = "SENSITIVE_APPLICANT_DATA"
        $note = "기존 자기소개서·면접 산출물. 포함 claim은 상위 원문으로 재검증해야 한다."
    }
    elseif ($p -match "input/career_run/(09_|10_|11_|12_|run.json)") {
        $class = "PIPELINE_METADATA"
        $role = "QUALITY_OR_RUN_AUDIT"
        $entity = "신용보증기금 지원서"
        $period = "2026-07-14..2026-07-15"
        $usability = "PROCESS_AUDIT_ONLY"
        $status = "DERIVED_NOT_EVIDENCE"
        $sensitivity = "SENSITIVE_APPLICANT_DATA"
        $note = "품질·스타일·최종 산출물·실행 메타데이터. 공식 선발 결과나 회사 사실이 아니다."
    }

    [pscustomobject][ordered]@{
        source_class = $class
        provenance_role = $role
        entity_scope = $entity
        temporal_scope = $period
        usability = $usability
        verification_status = $status
        sensitivity = $sensitivity
        note = $note
    }
}

New-Item -ItemType Directory -Force -Path $frozenRoot | Out-Null

$files = @(Get-ChildItem -LiteralPath $inputRoot -Recurse -File | Sort-Object FullName)
$localRecords = @()
$firstPathByHash = @{}
$index = 0

foreach ($file in $files) {
    $index++
    $relativePath = $file.FullName.Substring($repoRoot.Length + 1).Replace("\", "/")
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
    $classification = Get-Classification -RelativePath $relativePath
    $duplicateOf = $null
    if ($firstPathByHash.ContainsKey($hash)) {
        $duplicateOf = $firstPathByHash[$hash]
    }
    else {
        $firstPathByHash[$hash] = $relativePath
    }

    $localRecords += [pscustomobject][ordered]@{
        source_id = "LOC-{0:D3}" -f $index
        source_kind = "LOCAL_FILE"
        path = $relativePath
        title = $file.Name
        media_type = Get-MediaType -Extension $file.Extension
        size_bytes = $file.Length
        sha256 = $hash
        file_modified_at = $file.LastWriteTime.ToString("yyyy-MM-ddTHH:mm:sszzz")
        source_class = $classification.source_class
        provenance_role = $classification.provenance_role
        publisher_or_origin = if ($classification.entity_scope -eq "지원자") { "지원자 로컬 자료" } else { "로컬 입력 패키지" }
        entity_scope = $classification.entity_scope
        temporal_scope = $classification.temporal_scope
        retrieved_or_checked_at = $null
        usability = $classification.usability
        verification_status = $classification.verification_status
        sensitivity = $classification.sensitivity
        duplicate_of = $duplicateOf
        note = $classification.note
    }
}

$officialLedgerPath = Join-Path $inputRoot "career_run\04_공식근거.json"
$parsedClaims = Get-Content -Raw -Encoding UTF8 -LiteralPath $officialLedgerPath | ConvertFrom-Json
$priorClaims = @()
foreach ($claim in $parsedClaims) {
    $priorClaims += $claim
}
$urlGroups = @($priorClaims | Group-Object source_url | Sort-Object Name)
$urlRecords = @()
$urlIndex = 0

foreach ($group in $urlGroups) {
    $urlIndex++
    $url = $group.Name
    $publisher = "UNVERIFIED"
    $entity = "UNVERIFIED"
    $title = "기존 조사 출처 후보"
    if ($url -like "https://www.kodit.co.kr/kodit/cm/*") {
        $publisher = "신용보증기금"
        $entity = "신용보증기금"
        $title = "신용보증제도 개요"
    }
    elseif ($url -like "https://www.kodit.co.kr/kodit/na/*") {
        $publisher = "신용보증기금"
        $entity = "신용보증기금"
        $title = "지역 수출기업 협약보증 관련 공식 자료"
    }
    elseif ($url -like "https://www.bok.or.kr/*") {
        $publisher = "한국은행"
        $entity = "대한민국 중소기업 정책환경"
        $title = "환율·중소기업 한시 특별지원 관련 공식 자료"
    }
    elseif ($url -like "https://kodit2.saramin.co.kr/*") {
        $publisher = "신용보증기금 채용접수 페이지(운영 법인 미확인)"
        $entity = "신용보증기금 채용"
        $title = "2026년 하반기 체험형 청년인턴 채용공고·접수 페이지"
    }

    $published = @($group.Group | ForEach-Object { $_.published_at } | Where-Object { $_ } | Sort-Object -Unique) -join ","
    $checked = @($group.Group | ForEach-Object { $_.checked_at } | Where-Object { $_ } | Sort-Object -Unique) -join ","
    $urlRecords += [pscustomobject][ordered]@{
        source_id = "URL-{0:D3}" -f $urlIndex
        source_kind = "EXTERNAL_URL_LEAD"
        path = $null
        title = $title
        url = $url
        media_type = "text/html"
        publisher_or_origin = $publisher
        entity_scope = $entity
        published_at = if ($published) { $published } else { "UNVERIFIED" }
        retrieved_or_checked_at = if ($checked) { $checked } else { "UNVERIFIED" }
        claim_ids = @($group.Group | ForEach-Object { $_.claim_id })
        source_class = "PRIOR_RUN_SOURCE_LEAD"
        provenance_role = "REVERIFY_BEFORE_CLAIM_USE"
        usability = "DISCOVERY_ONLY"
        verification_status = "NEEDS_REVERIFICATION"
        note = "04_공식근거.json에서 추출. STEP 1은 외부 접속을 수행하지 않았으므로 기존 verified 표시는 승계하지 않는다."
    }
}

$allSources = @($localRecords) + @($urlRecords)
$duplicateFileCount = @($localRecords | Where-Object { $_.duplicate_of }).Count
$categoryCounts = @(
    $localRecords |
        Group-Object source_class |
        Sort-Object Name |
        ForEach-Object {
            [pscustomobject][ordered]@{ source_class = $_.Name; count = $_.Count }
        }
)

$snapshotLines = @($localRecords | ForEach-Object { "{0}`t{1}" -f $_.path, $_.sha256 }) -join "`n"
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $snapshotHash = ([BitConverter]::ToString($sha.ComputeHash($utf8NoBom.GetBytes($snapshotLines)))).Replace("-", "").ToLowerInvariant()
}
finally {
    $sha.Dispose()
}

$manifest = [pscustomobject][ordered]@{
    schema_version = 1
    step = "STEP_1"
    step_status = "COMPLETED_WITH_GAPS"
    run_id = $RunId
    company_data_package_id = $DataPackageId
    company_data_package_version = $DataPackageVersion
    frozen_at = $FrozenAt
    research_cutoff_date = "2026-07-15"
    target = [pscustomobject][ordered]@{
        company_name = "신용보증기금"
        legal_entity_name = "신용보증기금"
        brand_name = "신용보증기금(KODIT)"
        target_business_unit = "보증 분야"
        target_job = "체험형 청년인턴1(보증)"
        target_team = "UNVERIFIED"
        country = "대한민국"
    }
    scope_policy = [pscustomobject][ordered]@{
        allowed_local_root = "input/"
        external_access_performed = $false
        prior_run_claims_auto_promoted = $false
        derived_outputs_are_fact_sources = $false
        pii_use_for_company_research = $false
    }
    counts = [pscustomobject][ordered]@{
        local_input_file_count = $localRecords.Count
        external_url_lead_count = $urlRecords.Count
        source_record_count = $allSources.Count
        duplicate_local_file_count = $duplicateFileCount
        missing_upstream_source_count = 2
        prior_claim_count = $priorClaims.Count
    }
    input_snapshot_sha256 = $snapshotHash
    category_counts = $categoryCounts
    missing_upstream_sources = @(
        [pscustomobject][ordered]@{
            path = "경험정리/경험요약정리.docx"
            expected_sha256 = "5ca8c41d4da09551084685fa29aaab0ab75312e9909c8ad5a030f32edd2cff59"
            referenced_claim_count = 7
            status = "MISSING_FROM_INPUT"
        },
        [pscustomobject][ordered]@{
            path = "경험정리/인생기술서.docx"
            expected_sha256 = "58e1fcb26cd3777c03be687c58f92a4ca22c3c28a3e376e7d4788d50d1be4775"
            referenced_claim_count = 6
            status = "MISSING_FROM_INPUT"
        }
    )
    quality_findings = @(
        "직접 회사 근거는 축약된 로컬 공고 스냅샷 1건이며 전체 공식 공고는 현재 패키지에 없다.",
        "기존 온라인 조사 5개 claim의 4개 고유 URL은 재검증 전까지 출처 후보일 뿐이다.",
        "확정 경험원장 20개 claim 중 13개는 현재 input에 없는 상위 원문 2개를 참조한다.",
        "한국도로공사서비스 직무기술서 PDF 6개는 엔터티 불일치로 제외한다.",
        "지원자 증명사진 1개는 직접 개인정보로 기업 조사 사용을 금지한다.",
        "정확히 동일한 파생 파일 4개는 최초 경로에 duplicate_of로 연결한다."
    )
    sources = $allSources
}

$manifestPath = Join-Path $frozenRoot "manifest.json"
$manifestJson = $manifest | ConvertTo-Json -Depth 12
Write-Utf8NoBom -Path $manifestPath -Content ($manifestJson + "`n")

$postingRecord = $localRecords | Where-Object { $_.path -eq "input/career_run/00_채용공고원문/source.docx" }
$postingId = [string]$postingRecord.source_id
$jobPdfIds = @($localRecords | Where-Object { $_.path -like "input/직무기술서/*.pdf" } | ForEach-Object { $_.source_id }) -join ", "
$jobUrlRecord = $urlRecords | Where-Object { $_.url -like "https://kodit2.saramin.co.kr/*" }
$jobUrlId = [string]$jobUrlRecord.source_id
$overviewUrlRecord = $urlRecords | Where-Object { $_.url -like "https://www.kodit.co.kr/kodit/cm/*" }
$overviewUrlId = [string]$overviewUrlRecord.source_id

$entityMap = @"
---
run_id: $RunId
company_data_package_id: $DataPackageId
company_data_package_version: "$DataPackageVersion"
step: STEP_1
step_status: COMPLETED_WITH_GAPS
frozen_at: $FrozenAt
---

# ENTITY MAP

## 판정 원칙

- 엔터티 이름과 법적 지위는 구분한다. 로컬 공고에서 기관명이 확인되어도 설립 근거와 법적 지위는 별도 공식 원문 확인 전까지 확정하지 않는다.
- KODIT, 보증 분야, 채용 접수 테넌트는 각각 브랜드·사업 범위·전달 채널 후보로 분리한다.
- 기존 자기소개서·기업조사·모델 평가에만 등장하는 관계는 엔터티 사실로 승격하지 않는다.
- 다른 기관 자료는 오염 방지를 위해 지도에 표시하되 조사 대상과 연결하지 않는다.

| ID | 이름 | 유형 | 법적 명칭 | 조사대상과 관계 | 근거 | 관계 상태 | 범위 | 비고 |
|---|---|---|---|---|---|---|---|---|
| ENT-001 | 신용보증기금 | LEGAL_ENTITY | 신용보증기금 | 조사 대상 루트 | $postingId, $jobUrlId, $overviewUrlId | NAME_CONFIRMED_LEGAL_STATUS_NEEDS_VERIFICATION | 대한민국 | 로컬 공고에서 기관명은 확인. 법적 지위·설립 목적·정책금융 체계 내 역할은 STEP 2 공식 원문 검증 필요. |
| ENT-002 | 신용보증기금(KODIT) | BRAND | UNVERIFIED | ENT-001의 브랜드 후보 | $overviewUrlId | NEEDS_VERIFICATION | 대한민국 | STEP 0 표기와 공식 도메인 출처 후보에 기반한 잠정 항목. 동일성·공식 영문명은 재검증 전 미확정. |
| ENT-003 | 보증 분야 | BUSINESS_UNIT | NOT_APPLICABLE | ENT-001 채용분야의 업무 범위 | $postingId, $jobUrlId | POSTING_CONFIRMED_ORG_LEVEL_UNVERIFIED | 채용분야 | 공고상 분야명은 확인되지만 본부·영업점·팀 등 조직단위인지 여부는 미확인. |
| ENT-004 | kodit2.saramin.co.kr 채용 접수 테넌트 | UNVERIFIED | UNVERIFIED | ENT-001 공고 전달·접수 채널 후보 | $jobUrlId | NEEDS_VERIFICATION | 채용 접수 | 도메인만으로 운영 법인·위탁 관계를 단정하지 않는다. 고용주 엔터티와 혼동 금지. |
| ENT-005 | 한국도로공사서비스(주) | LEGAL_ENTITY | 한국도로공사서비스(주) | 조사 대상과 무관한 별도 기관 | $jobPdfIds | OUT_OF_SCOPE | 대한민국 | 직무기술서 6개를 렌더링·텍스트 확인. 신용보증기금 분석에서 제외. |

## 확인되지 않은 관계

- ENT-001의 PARENT, SUBSIDIARY, AFFILIATE, JOINT_VENTURE: UNVERIFIED
- 정확한 목표 팀·영업점·근무부점: UNVERIFIED
- ENT-001과 접수 테넌트 운영 법인의 계약·위탁 관계: UNVERIFIED
- 보증 분야가 공식 조직도상의 독립 BUSINESS_UNIT인지 여부: UNVERIFIED

## 오염 방지 결론

input/직무기술서/의 한국도로공사서비스 자료, 01_자료목록.md에만 기재된 외부 작업공간 파일, 모델 생성 자기소개서·평가 결과는 신용보증기금의 엔터티·사업·재무·문화 claim 근거로 사용하지 않는다.
"@

$entityMapPath = Join-Path $frozenRoot "entity_map.md"
Write-Utf8NoBom -Path $entityMapPath -Content ($entityMap.TrimEnd() + "`n")

$inventoryLines = New-Object System.Collections.Generic.List[string]
$inventoryLines.Add("---")
$inventoryLines.Add("run_id: $RunId")
$inventoryLines.Add("company_data_package_id: $DataPackageId")
$inventoryLines.Add("company_data_package_version: `"$DataPackageVersion`"")
$inventoryLines.Add("step: STEP_1")
$inventoryLines.Add("step_status: COMPLETED_WITH_GAPS")
$inventoryLines.Add("frozen_at: $FrozenAt")
$inventoryLines.Add("---")
$inventoryLines.Add("")
$inventoryLines.Add("# INPUT INVENTORY")
$inventoryLines.Add("")
$inventoryLines.Add("## 1. 범위 요약")
$inventoryLines.Add("")
$inventoryLines.Add("- 허용된 로컬 범위: ``input/``만 사용")
$inventoryLines.Add("- 로컬 파일: $($localRecords.Count)개")
$inventoryLines.Add("- 기존 원장에서 추출한 외부 URL 후보: $($urlRecords.Count)개(이번 단계 미접속)")
$inventoryLines.Add("- 통합 source record: $($allSources.Count)개")
$inventoryLines.Add("- 내용이 정확히 동일한 중복 파생 파일: ${duplicateFileCount}개")
$inventoryLines.Add("- 누락된 경험원장 상위 원문: 2개, 영향 claim 13개")
$inventoryLines.Add("- 입력 스냅샷 SHA-256: ``$snapshotHash``")
$inventoryLines.Add("")
$inventoryLines.Add("## 2. 분류 결과")
$inventoryLines.Add("")
$inventoryLines.Add("| source_class | 파일 수 | 사용 규칙 |")
$inventoryLines.Add("|---|---:|---|")
foreach ($row in $categoryCounts) {
    $rule = switch ($row.source_class) {
        "LOCAL_PRIMARY_SNAPSHOT" { "핵심 로컬 근거. 단, 전체 공식 공고와 현재성은 재검증." }
        "APPROVED_APPLICANT_LEDGER" { "지원자 bridge 전용. 상위 원문 누락 claim은 보류." }
        "APPLICANT_SOURCE" { "지원자 bridge 전용. 수치·성과는 claim 단위 검증." }
        "OUT_OF_SCOPE_OFFICIAL_DOCUMENT" { "엔터티 불일치로 제외." }
        "PII_IMAGE" { "직접 개인정보. 사용 금지." }
        "DERIVED_RESEARCH_LEDGER" { "URL 발견용. 기존 verified 상태 자동 승계 금지." }
        "DERIVED_STRUCTURED_EXTRACTION" { "원문 추적 보조만 허용." }
        default { "파생 산출물. 사실 근거로 사용하지 않음." }
    }
    $inventoryLines.Add("| ``$($row.source_class)`` | $($row.count) | $rule |")
}
$inventoryLines.Add("")
$inventoryLines.Add("## 3. 핵심 입력과 계보 판단")
$inventoryLines.Add("")
$inventoryLines.Add("1. ``$($postingRecord.path)``는 기관명·채용분야·담당업무·자기소개서 문항을 직접 담고 있으며 SHA-256은 ``$($postingRecord.sha256)``이다. 다만 전체 채용공고가 아닌 축약 스냅샷이므로 일정·자격·근무조건은 확정할 수 없다.")
$inventoryLines.Add("2. ``input/career_run/02_확정경험원장.json``은 20개 경험 claim을 ``confirmed``로 기록한다. 그중 7개는 현재 포함된 ``input/경험정리/경험정리.docx``와 SHA-256이 일치한다.")
$inventoryLines.Add("3. 나머지 13개 claim은 ``경험정리/경험요약정리.docx``와 ``경험정리/인생기술서.docx``를 참조하지만 두 파일은 현재 ``input/``에 없다. 승인 원장의 값은 보존하되 이번 패키지에서 독립 재검증되었다고 표시하지 않는다.")
$inventoryLines.Add("4. ``input/career_run/04_공식근거.json``의 5개 claim은 2026-07-13 기존 실행의 결과다. 이번 STEP 1에서는 외부 접속을 하지 않았으므로 4개 고유 URL을 모두 ``NEEDS_REVERIFICATION``으로 등록했다.")
$inventoryLines.Add("5. ``input/career_run/01_자료목록.md``는 현재 패키지 밖의 다수 경로를 나열하는 과거 카탈로그다. 그 안의 파일명만으로 파일 존재·내용·해시를 인정하지 않는다.")
$inventoryLines.Add("")
$inventoryLines.Add("## 4. 제외·주의 항목")
$inventoryLines.Add("")
$inventoryLines.Add("- 한국도로공사서비스 직무기술서 PDF 6개: 대상 법인 불일치, ``EXCLUDED_ENTITY_MISMATCH``")
$inventoryLines.Add("- 지원자 증명사진 1개: 직접 개인정보, ``PROHIBITED_FOR_COMPANY_RESEARCH``")
$inventoryLines.Add("- 자기소개서·면접팩·모델 후보·심사 결과·렌더링: claim 발견과 실행 계보 확인에만 사용")
$inventoryLines.Add("- ``draft_final.json``/``rigorous/selected.json`` 및 세 심사자 raw/정규화 쌍: 각각 내용이 동일한 중복")
$inventoryLines.Add("")
$inventoryLines.Add("## 5. 외부 URL 출처 후보")
$inventoryLines.Add("")
$inventoryLines.Add("| Source ID | 제목 | 발행·운영 주체 | 기존 확인일 | 기존 게시일 | 상태 | URL |")
$inventoryLines.Add("|---|---|---|---|---|---|---|")
foreach ($source in $urlRecords) {
    $inventoryLines.Add("| $($source.source_id) | $($source.title) | $($source.publisher_or_origin) | $($source.retrieved_or_checked_at) | $($source.published_at) | ``$($source.verification_status)`` | $($source.url) |")
}
$inventoryLines.Add("")
$inventoryLines.Add("## 6. 전체 로컬 파일")
$inventoryLines.Add("")
$inventoryLines.Add("전체 SHA-256과 기계 판독 필드는 ``manifest.json``에도 동일하게 기록한다.")
$inventoryLines.Add("")
$inventoryLines.Add("| Source ID | 경로 | source_class | 역할 | 엔터티 범위 | 사용성 | 검증 상태 | 중복 원본 | SHA-256 |")
$inventoryLines.Add("|---|---|---|---|---|---|---|---|---|")
foreach ($source in $localRecords) {
    $duplicate = if ($source.duplicate_of) { $source.duplicate_of } else { "-" }
    $inventoryLines.Add("| $($source.source_id) | ``$($source.path)`` | ``$($source.source_class)`` | ``$($source.provenance_role)`` | $($source.entity_scope) | ``$($source.usability)`` | ``$($source.verification_status)`` | $duplicate | ``$($source.sha256)`` |")
}
$inventoryLines.Add("")
$inventoryLines.Add("## 7. STEP 1 게이트")
$inventoryLines.Add("")
$inventoryLines.Add("- 회사 법적 지위·브랜드 동일성·공식 사업 범위: ``NEEDS_VERIFICATION``")
$inventoryLines.Add("- 공고 원문의 기관명·채용분야·담당업무·문항: 로컬 스냅샷 범위에서 확인")
$inventoryLines.Add("- 지원 마감일·근무기간·근무지·자격·배치 조직: ``UNVERIFIED``")
$inventoryLines.Add("- 재무 비교기간·뉴스 검색 시작일·비교대상 집합: ``UNVERIFIED``")
$inventoryLines.Add("- STEP 11 HARD FAIL: ``NOT_EVALUATED_AT_STEP_1``")

$inventoryPath = Join-Path $frozenRoot "input_inventory.md"
Write-Utf8NoBom -Path $inventoryPath -Content (($inventoryLines -join "`n") + "`n")

$manifestHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $manifestPath).Hash.ToLowerInvariant()
$entityMapHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $entityMapPath).Hash.ToLowerInvariant()
$inventoryHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $inventoryPath).Hash.ToLowerInvariant()

$packageYaml = @"
run_id: $RunId
company_data_package_id: $DataPackageId
company_data_package_version: "$DataPackageVersion"
step: STEP_1
step_status: COMPLETED_WITH_GAPS
frozen_at: $FrozenAt
research_cutoff_date: 2026-07-15
financial_cutoff_period: UNVERIFIED
news_search_start_date: UNVERIFIED
job_posting_date: 2026-07-09
target_job: "체험형 청년인턴1(보증)"
competitor_set_version: UNVERIFIED
source_count: $($allSources.Count)
local_input_file_count: $($localRecords.Count)
external_source_lead_count: $($urlRecords.Count)
input_snapshot_sha256: "$snapshotHash"
artifacts:
  research_questions:
    path: company_research/frozen/research_questions.md
    status: FROZEN_STEP_0
  manifest:
    path: company_research/frozen/manifest.json
    sha256: "$manifestHash"
  entity_map:
    path: company_research/frozen/entity_map.md
    sha256: "$entityMapHash"
  input_inventory:
    path: company_research/frozen/input_inventory.md
    sha256: "$inventoryHash"
scope:
  allowed_local_root: input/
  external_access_performed: false
  prior_run_claims_auto_promoted: false
  target_legal_entity_status: NEEDS_VERIFICATION
gates:
  missing_upstream_sources: 2
  affected_applicant_claims: 13
  out_of_scope_entity_files: 6
  prohibited_pii_files: 1
  hard_fail_status: NOT_EVALUATED_AT_STEP_1
next_step: STEP_2_SOURCE_COLLECTION_AND_CLAIM_LEDGER
"@

$packagePath = Join-Path $frozenRoot "company_data_package.yaml"
Write-Utf8NoBom -Path $packagePath -Content ($packageYaml.TrimEnd() + "`n")

[pscustomobject][ordered]@{
    step_completed = "STEP_1"
    step_status = "COMPLETED_WITH_GAPS"
    files_created = @(
        "company_research/frozen/manifest.json",
        "company_research/frozen/company_data_package.yaml",
        "company_research/frozen/entity_map.md",
        "company_research/frozen/input_inventory.md"
    )
    local_input_file_count = $localRecords.Count
    external_source_lead_count = $urlRecords.Count
    source_count = $allSources.Count
    input_snapshot_sha256 = $snapshotHash
} | ConvertTo-Json -Depth 5
