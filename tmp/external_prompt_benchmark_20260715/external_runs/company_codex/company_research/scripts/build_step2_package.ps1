param(
    [string]$RunId = "CR-20260715-1539",
    [string]$CollectedAt = "2026-07-15T16:45:00+09:00"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$frozen = Join-Path $root "company_research/frozen"
$out = Join-Path $root "company_research/step2"
New-Item -ItemType Directory -Force -Path $out | Out-Null

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    [IO.File]::WriteAllText($Path, $Content, [Text.UTF8Encoding]::new($false))
}

function Assert-Hash([string]$RelativePath, [string]$Expected) {
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $root $RelativePath)).Hash.ToLowerInvariant()
    if ($actual -ne $Expected) { throw "Frozen input changed: $RelativePath expected=$Expected actual=$actual" }
}

Assert-Hash "company_research/frozen/manifest.json" "d09f845393cb17f4f9ed2bb468852cc75d111f67f2359f020da8b94828bf8ae8"
Assert-Hash "company_research/frozen/entity_map.md" "f6d14e5194d86ff0119b264107c693f3ab9d79563ec7eabe203c1fb71055b93b"
Assert-Hash "company_research/frozen/input_inventory.md" "ff5ba98a4f8cb6557ac022c7c7a67ae77a373af33d32d2293e46d559e2e4b3b5"
Assert-Hash "input/career_run/00_채용공고원문/source.docx" "5b6f69118ca1eece39f284fb26c18e42422ba01088f978b9829c0501bc456779"
Assert-Hash "input/career_run/02_확정경험원장.json" "485c2fad17ec5cddf117b884e0baf61d4aa9bcfdc9c5b1cc96ab1435e2d3f2c4"
Assert-Hash "input/경험정리/경험정리.docx" "dbbed908faa6876fd4cab9ffa7e4728d0f9d5453bd1d18b4a5e26164f88607d1"

$sources = @(
    [ordered]@{ source_id="SRC-001"; title="신용보증기금법"; publisher="국가법령정보센터"; source_type="STATUTE"; grade="A1"; url="https://www.law.go.kr/LSW/lsInfoP.do?ancYnChk=0&chrClsCd=010202&efYd=20260102&lsiSeq=277263&urlMode=lsInfoP"; published_or_effective_at="2026-01-02"; checked_at=$CollectedAt; access_status="VERIFIED"; evidence_locator="제1조 및 제2조" },
    [ordered]@{ source_id="SRC-002"; title="신용보증제도 개요"; publisher="신용보증기금"; source_type="OFFICIAL_WEB"; grade="A2"; url="https://www.kodit.or.kr/kodit/cm/cntnts/cntntsView.do?cntntsId=11064&mi=2521"; published_or_effective_at="CURRENT_AT_ACCESS"; checked_at=$CollectedAt; access_status="VERIFIED"; evidence_locator="기본구조 및 보증운영 체계" },
    [ordered]@{ source_id="SRC-003"; title="보증이용 절차 - 업무흐름도"; publisher="신용보증기금"; source_type="OFFICIAL_WEB"; grade="A2"; url="https://www.kodit.or.kr/kodit/cm/cntnts/cntntsView.do?cntntsId=11066&mi=2525"; published_or_effective_at="CURRENT_AT_ACCESS"; checked_at=$CollectedAt; access_status="VERIFIED"; evidence_locator="STEP 01~보증서 발급" },
    [ordered]@{ source_id="SRC-004"; title="자료 수집 및 신용조사"; publisher="신용보증기금"; source_type="OFFICIAL_WEB"; grade="A2"; url="https://www.kodit.or.kr/kodit/cm/cntnts/cntntsView.do?cntntsId=11068&mi=2527"; published_or_effective_at="CURRENT_AT_ACCESS"; checked_at=$CollectedAt; access_status="VERIFIED"; evidence_locator="수집자료 및 신용조사" },
    [ordered]@{ source_id="SRC-005"; title="보증심사 및 승인"; publisher="신용보증기금"; source_type="OFFICIAL_WEB"; grade="A2"; url="https://www.kodit.or.kr/kodit/cm/cntnts/cntntsView.do?cntntsId=11069&mi=2528"; published_or_effective_at="CURRENT_AT_ACCESS"; checked_at=$CollectedAt; access_status="VERIFIED"; evidence_locator="보증심사 및 심사방법" },
    [ordered]@{ source_id="SRC-006"; title="신용보증 대상기업"; publisher="신용보증기금"; source_type="OFFICIAL_WEB"; grade="A2"; url="https://www.kodit.or.kr/kodit/cm/cntnts/cntntsView.do?cntntsId=11065&mi=2523"; published_or_effective_at="CURRENT_AT_ACCESS"; checked_at=$CollectedAt; access_status="VERIFIED"; evidence_locator="보증대상기업 및 업종" },
    [ordered]@{ source_id="SRC-007"; title="유동화보증 지원계획 및 담당조직"; publisher="신용보증기금"; source_type="OFFICIAL_WEB"; grade="A2"; url="https://www.kodit.or.kr/kodit/cm/cntnts/cntntsView.do?cntntsId=11078&mi=2539"; published_or_effective_at="2026"; checked_at=$CollectedAt; access_status="VERIFIED"; evidence_locator="2026년 지원규모" },
    [ordered]@{ source_id="SRC-008"; title="보증연계투자"; publisher="신용보증기금"; source_type="OFFICIAL_WEB"; grade="A2"; url="https://www.kodit.or.kr/kodit/cm/cntnts/cntntsView.do?mi=2541&cntntsId=11079"; published_or_effective_at="2026"; checked_at=$CollectedAt; access_status="VERIFIED"; evidence_locator="개요·지원규모·지원대상" },
    [ordered]@{ source_id="SRC-009"; title="KODIT 인재상"; publisher="신용보증기금"; source_type="OFFICIAL_WEB"; grade="A2"; url="https://www.kodit.or.kr/kodit/cm/cntnts/cntntsView.do?cntntsId=11180&mi=2513"; published_or_effective_at="CURRENT_AT_ACCESS"; checked_at=$CollectedAt; access_status="VERIFIED"; evidence_locator="기본인품 및 성장자질" },
    [ordered]@{ source_id="SRC-010"; title="경영환경 모니터링"; publisher="신용보증기금"; source_type="OFFICIAL_WEB"; grade="A2"; url="https://www.kodit.or.kr/kodit/cm/cntnts/cntntsView.do?cntntsId=11157&mi=2468"; published_or_effective_at="CURRENT_AT_ACCESS"; checked_at=$CollectedAt; access_status="VERIFIED"; evidence_locator="모니터링 채널" },
    [ordered]@{ source_id="SRC-011"; title="2026년도 하반기 체험형 청년인턴 채용공고"; publisher="신용보증기금 채용홈페이지"; source_type="OFFICIAL_RECRUITMENT_PAGE"; grade="A2"; url="https://kodit2.saramin.co.kr/service/kodit2/3872/applicant/apply/recruit_default.asp"; published_or_effective_at="2026-07-09"; checked_at=$CollectedAt; access_status="VERIFIED"; evidence_locator="채용분야·지원자격·근무조건·전형·기타사항" },
    [ordered]@{ source_id="SRC-012"; title="붙임1 채용단위 운영현황"; publisher="신용보증기금 채용홈페이지"; source_type="OFFICIAL_RECRUITMENT_ATTACHMENT"; grade="A2"; url="https://dym-upload.saramin.co.kr/upload/dym2_5/578/3872/filedown/2026-06-24/03kodit2_260624_01.pdf"; published_or_effective_at="2026-07-09"; checked_at=$CollectedAt; access_status="VERIFIED"; evidence_locator="3쪽 전체" },
    [ordered]@{ source_id="SRC-013"; title="붙임2 신용보증기금 채용제한 사유"; publisher="신용보증기금 채용홈페이지"; source_type="OFFICIAL_RECRUITMENT_ATTACHMENT"; grade="A2"; url="https://dym-upload.saramin.co.kr/upload/dym2_5/578/3872/filedown/2026-06-24/03kodit2_260624_02.pdf"; published_or_effective_at="2026-07-09"; checked_at=$CollectedAt; access_status="VERIFIED"; evidence_locator="1쪽 전체" },
    [ordered]@{ source_id="SRC-014"; title="붙임3 블라인드 위반 세부 기준"; publisher="신용보증기금 채용홈페이지"; source_type="OFFICIAL_RECRUITMENT_ATTACHMENT"; grade="A2"; url="https://dym-upload.saramin.co.kr/upload/dym2_5/578/3872/filedown/2026-06-24/03kodit2_260624_03.pdf"; published_or_effective_at="2026-07-09"; checked_at=$CollectedAt; access_status="VERIFIED"; evidence_locator="1쪽 전체" },
    [ordered]@{ source_id="SRC-015"; title="중장기 재무관리계획 공시 색인"; publisher="ALIO"; source_type="OFFICIAL_DISCLOSURE_INDEX"; grade="A2"; url="https://www.alio.go.kr/upload/disclosure/2025/10/14/2025101403061603/doc.html"; published_or_effective_at="2025-09-30"; checked_at=$CollectedAt; access_status="INDEX_ONLY"; evidence_locator="2021~2025 첨부 목록" },
    [ordered]@{ source_id="SRC-016"; title="확정 경험원장"; publisher="지원자 승인 로컬 원장"; source_type="LOCAL_APPROVED_LEDGER"; grade="L2"; path="input/career_run/02_확정경험원장.json"; sha256="485c2fad17ec5cddf117b884e0baf61d4aa9bcfdc9c5b1cc96ab1435e2d3f2c4"; checked_at=$CollectedAt; access_status="PARTIAL_LINEAGE"; evidence_locator="20개 경험 claim" },
    [ordered]@{ source_id="SRC-017"; title="경험정리 원문"; publisher="지원자 로컬 원문"; source_type="LOCAL_APPLICANT_SOURCE"; grade="L1"; path="input/경험정리/경험정리.docx"; sha256="dbbed908faa6876fd4cab9ffa7e4728d0f9d5453bd1d18b4a5e26164f88607d1"; checked_at=$CollectedAt; access_status="VERIFIED_PRESENT"; evidence_locator="원장 연결 claim 7개 문자열 재확인" }
)

function Claim($id,$rq,$domain,$text,$status,$confidence,$sourceIds,$locator,$counter,$use,$restriction) {
    [ordered]@{ claim_id=$id; rq_ids=@($rq); domain=$domain; claim=$text; verification_status=$status; confidence=$confidence; source_ids=@($sourceIds); evidence_locator=$locator; counterevidence_or_limit=$counter; application_use=$use; usage_restriction=$restriction }
}

$claims = @(
    (Claim "CLM-COMP-001" "RQ-01" "ENTITY" "신용보증기금은 신용보증기금법에 따라 기업의 자금융통과 건전한 신용질서 확립을 통해 국민경제 발전에 기여하도록 설립된 기금이다." "CONFIRMED_PRIMARY" "HIGH" @("SRC-001") "신용보증기금법 제1조" "법률상 목적은 개별 사업의 실제 성과를 뜻하지 않는다." "기관 역할과 지원동기의 사실 기반" "법률 목적을 성과 실적으로 바꾸어 표현하지 말 것"),
    (Claim "CLM-COMP-002" @("RQ-01","RQ-02") "BUSINESS_MODEL" "법정 목적 범위에는 기업 채무보증, 회사채 등 유동화, 신용정보의 관리·운용이 포함된다." "CONFIRMED_PRIMARY" "HIGH" @("SRC-001") "제1조·제2조" "세부 사업별 2026년 집행 실적은 별도 검증이 필요하다." "기관 사업 범위 설명" "사업 규모 수치를 임의 결합하지 말 것"),
    (Claim "CLM-COMP-003" @("RQ-02","RQ-04") "VALUE_CHAIN" "일반적인 신용보증 흐름은 신청·상담, 자료수집·신용조사, 보증심사·승인, 약정·보증서 발급으로 이어진다." "CONFIRMED_PRIMARY" "HIGH" @("SRC-002","SRC-003","SRC-004","SRC-005") "각 공식 업무안내의 단계" "공고상 인턴이 이 모든 단계를 독립 수행한다는 근거는 없다." "기한연장·상시관리 업무의 전후 맥락" "인턴의 심사·승인 권한으로 확대 금지"),
    (Claim "CLM-COMP-004" "RQ-03" "CUSTOMER" "보증대상은 일정 요건을 갖춘 개인기업·법인기업·기업단체이며 대기업·상장기업은 특정자금에 한해 제한적으로 허용된다." "CONFIRMED_PRIMARY" "HIGH" @("SRC-006") "보증대상기업" "개별 신청기업의 지원 가능 여부는 심사 전 확정할 수 없다." "고객군 설명" "모든 중소기업이 자동 지원대상이라는 표현 금지"),
    (Claim "CLM-COMP-005" @("RQ-04","RQ-10","RQ-12") "OPERATIONS" "신용조사에는 등기·행정·금융거래·국세·세무회계 자료가 사용되고, 최근 3년 재무제표 등도 수집 대상이다." "CONFIRMED_PRIMARY" "HIGH" @("SRC-004") "수집자료 표" "자료 접근 권한과 인턴의 실제 취급 범위는 확인되지 않았다." "정확한 자료 확인·개인정보 주의의 직무 맥락" "인턴이 모든 민감자료를 조회한다고 단정 금지"),
    (Claim "CLM-COMP-006" @("RQ-04","RQ-10") "RISK_CONTROL" "보증심사는 사업성·미래성장성·기업가치·기술력·기업가 정신 등을 고려하고 보증금액에 따라 심사 수준이 구분된다." "CONFIRMED_PRIMARY" "HIGH" @("SRC-005") "보증심사 및 심사방법" "내부 세부 기준과 개별 평가 결과는 공개 근거로 확인하지 못했다." "오류 예방과 판단 근거의 중요성 설명" "비공개 평가모형 추정 금지"),
    (Claim "CLM-COMP-007" "RQ-07" "PROGRAM" "신용보증기금은 2026년 유동화보증 신규자금 지원규모를 2.8조원으로 안내한다." "CONFIRMED_PRIMARY" "HIGH" @("SRC-007") "2026년 지원규모" "계획 수치이며 실제 집행액이 아니다." "기관 사업 다각화의 최신 사례" "실적 또는 달성액으로 표현 금지"),
    (Claim "CLM-COMP-008" "RQ-07" "PROGRAM" "2026년 보증연계투자 지원규모는 673억원으로 안내되며, 신용보증과 투자를 연계해 중소기업 자금조달·재무구조 개선을 지원한다." "CONFIRMED_PRIMARY" "HIGH" @("SRC-008") "개요·지원규모" "계획 수치이며 실제 집행액이 아니다." "보증 외 복합금융 이해" "체험형 인턴의 직접 업무로 연결 금지"),
    (Claim "CLM-COMP-009" "RQ-11" "CULTURE" "공식 인재상은 기본인품과 성장자질을 축으로 책임감·열정, 혁신·소통, 논리적 사고, 문제해결 등을 제시한다." "CONFIRMED_PRIMARY" "HIGH" @("SRC-009") "인재상 항목" "공식 가치 문구만으로 실제 조직문화를 확정할 수 없다." "지원서 행동 기준과 면접 답변 점검" "실제 문화가 동일하다고 단정 금지"),
    (Claim "CLM-COMP-010" @("RQ-07","RQ-10") "GOVERNANCE" "공식 경영환경 모니터링 체계에는 거시경제·중소기업·정책·내부환경과 VOC, 고객자문단, 리스크준법실, 성과관리시스템 등이 제시된다." "CONFIRMED_PRIMARY" "MEDIUM_HIGH" @("SRC-010") "모니터링 채널" "채널의 운영 빈도·효과·2026 성과는 확인되지 않았다." "상시관리와 피드백 체계 이해" "통제 효과를 수치화하지 말 것"),
    (Claim "CLM-JOB-001" @("RQ-12","RQ-13") "JOB_POSTING" "체험형 청년인턴1(보증)은 140명을 모집하며 약 3개월 동안 전국 영업점 100개에서 신용보증 기한연장과 기업신용 상시관리 등을 수행한다." "CONFIRMED_PRIMARY" "HIGH" @("SRC-011","SRC-012") "채용분야 및 채용단위 운영현황" "'등'의 세부업무와 개별 배치 부점은 미확정이다." "직무 선택 및 수행계획" "심사·승인·독립판단 업무로 확대 금지"),
    (Claim "CLM-JOB-002" "RQ-13" "EMPLOYMENT_TERMS" "근무기간은 2026-09-17부터 2026-12-16까지이고, 주 5일·1일 8시간, 월 225만원 수준(세전)이다." "CONFIRMED_PRIMARY" "HIGH" @("SRC-011") "근무조건" "세후 실수령액과 개별 근무시간 선택 결과는 확정할 수 없다." "지원 가능성 판단" "세후 금액 추정 금지"),
    (Claim "CLM-JOB-003" "RQ-13" "APPLICATION" "접수기간은 2026-07-09부터 2026-07-23 16:00까지이며 채용홈페이지 온라인 접수만 허용된다." "CONFIRMED_PRIMARY" "HIGH" @("SRC-011") "원서접수" "사이트 장애 가능성이 안내되어 있고 최종 제출 완료가 필요하다." "제출 일정 관리" "임시저장을 제출 완료로 간주 금지"),
    (Claim "CLM-JOB-004" "RQ-13" "ELIGIBILITY" "학력·성별·전공 제한은 없지만 신용보증기금 청년인턴 근무경험자는 지원할 수 없고, 마감일 기준 만 18~34세 및 채용일부터 출퇴근 가능 요건이 있다." "CONFIRMED_PRIMARY" "HIGH" @("SRC-011") "지원자격" "지원자의 생년월일·과거 근무 여부·출퇴근 가능성은 이 조사에서 확인하지 않았다." "자가 자격 점검" "지원자 개인정보를 추정하지 말 것"),
    (Claim "CLM-JOB-005" "RQ-13" "SELECTION" "서류는 업무수행계획서와 약식논술의 충실도·논리력·혁신적 사고를 평가하고, 면접은 기본인성과 직무능력을 평가한다." "CONFIRMED_PRIMARY" "HIGH" @("SRC-011") "전형절차 및 방법" "내부 배점표와 합격 가능성은 공개되지 않았다." "작성·면접 검토 기준" "내부 품질점수를 공식 전형점수로 표현 금지"),
    (Claim "CLM-JOB-006" "RQ-13" "BLIND_RECRUITMENT" "업무수행계획서와 약식논술에는 이름·나이·출신지·가족관계·학교명·성별 등 블라인드 위반 정보를 기재하면 안 된다." "CONFIRMED_PRIMARY" "HIGH" @("SRC-011","SRC-014") "기타사항 및 붙임3" "기업명·기관명은 직무 관련 경력 확인을 위해 허용되지만 학교·지역 식별 표현은 금지된다." "최종 원고 블라인드 점검" "군경험 등 간접 성별 식별도 주의"),
    (Claim "CLM-JOB-007" "RQ-12" "PLACEMENT" "복수 근무부점 채용단위는 희망 순위를 참고하되 희망 외 부점 배치가 가능하고, 배치 후 같은 채용단위 내 타 부점 이동도 가능하다." "CONFIRMED_PRIMARY" "HIGH" @("SRC-011","SRC-012") "붙임1 안내 및 기타사항" "정확한 배치 지점·팀·보고선은 합격 전 확정되지 않는다." "근무지 유연성 판단" "특정 영업점 배치를 전제로 쓰지 말 것"),
    (Claim "CLM-APP-001" "RQ-14" "APPLICANT_EVIDENCE" "지원자는 3,000페이지 규모 자료를 분류해 2일 만에 정리했다는 경험 문장을 현재 포함된 원문에서 확인할 수 있다." "CONFIRMED_LOCAL" "MEDIUM_HIGH" @("SRC-016","SRC-017") "clm_88cfeab230789e5b0d5f; XML 검색 문단 456" "자료량·기간의 외부 기록이나 산식은 별도로 확인되지 않았다." "자료 분류·마감 준수 브리지" "객관적 외부 검증 수치처럼 표현 금지"),
    (Claim "CLM-APP-002" "RQ-14" "APPLICANT_EVIDENCE" "지원자는 상인 50명 인터뷰와 5개 시장 비교분석 경험 문장을 현재 포함된 원문에서 확인할 수 있다." "CONFIRMED_LOCAL" "MEDIUM_HIGH" @("SRC-016","SRC-017") "clm_abaa19a532d1aabc9140; XML 검색 문단 152" "인터뷰 명단·비교표 등 별도 산출물은 현재 입력에 없다." "고객 관점·비교분석 브리지" "조사 품질이나 성과를 과장하지 말 것"),
    (Claim "CLM-APP-003" "RQ-14" "APPLICANT_EVIDENCE" "지원자는 엑셀 자동화로 급여 산정 속도를 30% 향상했다는 경험 문장을 현재 포함된 원문에서 확인할 수 있다." "PARTIAL_LOCAL" "MEDIUM" @("SRC-016","SRC-017") "clm_353c575898c6254492e8; XML 검색 문단 570" "30%의 기준선·측정기간·산식이 원장과 원문에 없다." "결과 대조·업무개선 브리지" "30% 수치는 검증방법 질문에 답할 수 있을 때만 제한적으로 사용"),
    (Claim "CLM-APP-004" "RQ-14" "LINEAGE_GAP" "승인 경험원장 20개 claim 중 13개는 현재 input에 없는 경험요약정리.docx 또는 인생기술서.docx를 상위 원문으로 참조한다." "BLOCKED_MISSING_SOURCE" "HIGH" @("SRC-016") "frozen manifest missing_upstream_sources" "승인 상태는 보존되지만 이번 패키지에서 독립 재검증할 수 없다." "사용 가능한 경험 범위 제한" "해당 13개 claim을 신규 검증 완료로 표시 금지"),
    (Claim "CLM-FIN-001" @("RQ-05","RQ-06") "FINANCIALS" "최근 3개 공시연도 및 2026 최신 가용 시점의 보증공급·보증잔액·대위변제·회수·사고율 추세는 이번 단계에서 확정하지 못했다." "BLOCKED_SOURCE_NOT_EXTRACTED" "HIGH" @("SRC-015") "ALIO 색인만 확인" "첨부 재무관리계획·감사보고서의 동일 범위 수치를 추출·대조해야 한다." "재무 결론 보류" "추세·증감률·건전성 결론 사용 금지"),
    (Claim "CLM-ROLE-001" "RQ-12" "JOB_REALITY" "인턴이 실제로 사용하는 시스템, 고객 접점 빈도, 보고선, 자료 접근권한, 오류 KPI는 공식 공고에서 확인되지 않았다." "UNVERIFIED" "HIGH" @("SRC-011") "공고 기재 범위와 공백" "공식 FAQ·직무설명·현장 근거가 필요하다." "면접 질문 및 온보딩 확인 항목" "구체 시스템명·권한·KPI 추정 금지"),
    (Claim "CLM-COMPARE-001" "RQ-09" "COMPARISON" "기술보증기금·지역신보·무역보험공사·기업은행과의 법적 역할·고객·재원·성과 비교는 이번 단계에서 검증 완료되지 않았다." "UNVERIFIED" "HIGH" @() "비교기관별 공식 1차 출처 미수집" "동일 기준일·동일 단위의 비교 원장이 필요하다." "기관 선택 이유 보류" "차별점 단정 및 순위화 금지"),
    (Claim "CLM-DECISION-001" "RQ-15" "DECISION_GATE" "채용 기본조건과 직무 표면은 확인됐지만 재무·실제 직무 권한·현장문화·비교기관 근거가 남아 있어 최종 지원 우선순위는 아직 확정할 수 없다." "NOT_READY" "HIGH" @("SRC-011","SRC-015") "STEP 2 게이트" "지원자 본인의 자격·희망 근무지·기회비용도 별도 확인이 필요하다." "후속 조사 우선순위 설정" "최종 지원 권고로 사용 금지")
)

$sourcePackage = [ordered]@{ schema_version=1; step="STEP_2"; run_id=$RunId; company_data_package_id="CR-DATA-001"; collected_at=$CollectedAt; source_count=$sources.Count; sources=$sources }
$claimPackage = [ordered]@{ schema_version=1; step="STEP_2"; run_id=$RunId; company_data_package_id="CR-DATA-001"; research_cutoff_date="2026-07-15"; claim_count=$claims.Count; status_vocabulary=@("CONFIRMED_PRIMARY","CONFIRMED_LOCAL","PARTIAL_LOCAL","UNVERIFIED","BLOCKED_MISSING_SOURCE","BLOCKED_SOURCE_NOT_EXTRACTED","NOT_READY"); claims=$claims }

$sourcePath = Join-Path $out "source_ledger.json"
$claimPath = Join-Path $out "claim_ledger.json"
Write-Utf8NoBom $sourcePath (($sourcePackage | ConvertTo-Json -Depth 20) + "`n")
Write-Utf8NoBom $claimPath (($claimPackage | ConvertTo-Json -Depth 20) + "`n")

$statusCounts = $claims | Group-Object { $_["verification_status"] } | Sort-Object Name
$md = New-Object Collections.Generic.List[string]
$md.Add("---"); $md.Add("run_id: $RunId"); $md.Add("company_data_package_id: CR-DATA-001"); $md.Add("step: STEP_2"); $md.Add("step_status: COMPLETED_WITH_GAPS"); $md.Add("collected_at: $CollectedAt"); $md.Add("---"); $md.Add("")
$md.Add("# STEP 2 CLAIM LEDGER"); $md.Add("")
$md.Add("## 상태 요약"); $md.Add("")
foreach($g in $statusCounts){$md.Add("- ``$($g.Name)``: $($g.Count)개")}
$md.Add(""); $md.Add("## Claim 목록"); $md.Add("")
$md.Add("| Claim ID | RQ | 영역 | 주장 | 상태 | 근거 | 제한 |"); $md.Add("|---|---|---|---|---|---|---|")
foreach($c in $claims){
    $rq=($c.rq_ids -join ", "); $src=if($c.source_ids.Count){$c.source_ids -join ", "}else{"-"};
    $safeClaim=$c.claim -replace "\|","/"; $safeLimit=$c.counterevidence_or_limit -replace "\|","/";
    $md.Add("| $($c.claim_id) | $rq | $($c.domain) | $safeClaim | ``$($c.verification_status)`` | $src | $safeLimit |")
}
$md.Add(""); $md.Add("## 사용 게이트"); $md.Add("")
$md.Add("- ``CONFIRMED_PRIMARY``만 회사·채용의 확정 사실로 사용한다.")
$md.Add("- ``CONFIRMED_LOCAL``과 ``PARTIAL_LOCAL``은 지원자 경험으로만 사용하며 회사 사실과 섞지 않는다.")
$md.Add("- ``UNVERIFIED``와 ``BLOCKED_*``는 질문·공백 목록에만 사용하고 자기소개서의 단정 문장에 사용하지 않는다.")
$md.Add("- STEP 11 HARD FAIL은 이 단계에서 평가하지 않는다.")
Write-Utf8NoBom (Join-Path $out "claim_ledger.md") (($md -join "`n") + "`n")

$report = @"
---
run_id: $RunId
company_data_package_id: CR-DATA-001
step: STEP_2
step_status: COMPLETED_WITH_GAPS
collected_at: $CollectedAt
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

- STEP 2: ``COMPLETED_WITH_GAPS``
- 최종 의사결정: ``NOT_READY``
- HARD FAIL: ``NOT_EVALUATED_AT_STEP_2``
- 다음 단계: ``STEP_3_BUSINESS_AND_FINANCIAL_ANALYSIS``

``company_research/final/``은 현재 비어 있으며 최종 단계 전에는 채우지 않는다. 현재 원장은 중간 검증 산출물이며, ``UNVERIFIED``·``BLOCKED_*`` claim을 확정 사실로 승격하지 않는다.
"@
Write-Utf8NoBom (Join-Path $out "step2_report.md") ($report.TrimEnd()+"`n")

$artifactNames=@("source_ledger.json","claim_ledger.json","claim_ledger.md","step2_report.md")
$artifacts=@(); foreach($name in $artifactNames){$p=Join-Path $out $name; $artifacts += [ordered]@{path="company_research/step2/$name"; sha256=(Get-FileHash -Algorithm SHA256 $p).Hash.ToLowerInvariant()}}
$manifest=[ordered]@{schema_version=1;step="STEP_2";step_status="COMPLETED_WITH_GAPS";run_id=$RunId;company_data_package_id="CR-DATA-001";collected_at=$CollectedAt;source_count=$sources.Count;claim_count=$claims.Count;status_counts=[ordered]@{};gates=[ordered]@{final_decision="NOT_READY";hard_fail_status="NOT_EVALUATED_AT_STEP_2";next_step="STEP_3_BUSINESS_AND_FINANCIAL_ANALYSIS"};artifacts=$artifacts}
foreach($g in $statusCounts){$manifest.status_counts[$g.Name]=$g.Count}
Write-Utf8NoBom (Join-Path $out "manifest.json") (($manifest|ConvertTo-Json -Depth 20)+"`n")
$manifest
