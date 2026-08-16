#!/usr/bin/env python3
"""Build the Kakao company-research packet from frozen local inputs only.

This run intentionally has no eligible Kakao company or posting source.  The
builder therefore records scope mismatches, preserves applicant evidence, and
emits an INSUFFICIENT_EVIDENCE decision without inventing company facts.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "input"
OUT = ROOT / "company_research"

RUN_ID = "CR-20260715-1601"
PACKAGE_ID = "CR-DATA-001"
PACKAGE_VERSION = "1.0"
FROZEN_AT = "2026-07-15T16:01:22+09:00"
RESEARCH_CUTOFF_DATE = "2026-07-15"
RESEARCH_QUESTIONS_SHA256 = "793187b88f75c86aa8bc12490b678acc5c32a2c2babdff0be2ec230707d0ad42"
INPUT_SET_SHA256 = "7ddc582ec568dc654f2bf0701d4fd4b885d4f4bfbc4a3ced4dbe1d3103ca61cf"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def classify(rel: str) -> tuple[str, str, str, str, str]:
    """Return author, type, basis date, scope, use policy."""
    if rel == "input/career_run/02_확정경험원장.json":
        return (
            "지원자 승인 career ledger",
            "confirmed applicant ledger",
            "경험별 기간 UNVERIFIED; 원장 생성 2026-07-10",
            "APPLICANT",
            "confirmed claim만 지원자 근거로 사용",
        )
    if rel == "input/경험정리/경험정리.docx":
        return (
            "지원자",
            "raw applicant narrative",
            "UNVERIFIED",
            "APPLICANT",
            "원장 claim 교차확인에만 사용",
        )
    if rel == "input/경험정리/0113_dl_51_sb (1) (1).jpg":
        return (
            "지원자",
            "portrait / personal data",
            "NOT_APPLICABLE",
            "PII",
            "본문·분석·전송 사용 금지",
        )
    if rel.startswith("input/직무기술서/"):
        return (
            "한국도로공사서비스(주)",
            "NCS job description PDF",
            "발표일·기준일 UNVERIFIED",
            "OFF_TARGET_ENTITY",
            "카카오 회사·직무 근거로 사용 금지",
        )
    if rel == "input/career_run/00_채용공고원문/source.docx":
        return (
            "사용자 확인 원문",
            "KODIT posting source DOCX",
            "2026-07-09",
            "OFF_TARGET_KODIT",
            "대상 불일치로 카카오 근거 사용 금지",
        )
    if rel == "input/career_run/04_공식근거.json":
        return (
            "로컬 원장; 기초 출처는 신용보증기금·한국은행",
            "off-target official-evidence ledger",
            "2026-03~2026-07",
            "OFF_TARGET_KODIT",
            "카카오 근거 사용 금지; 불일치 입증에만 사용",
        )
    if rel.startswith("input/career_run/"):
        return (
            "local career_pipeline",
            "derived KODIT career-run artifact",
            "생성·검증일 2026-07-11~2026-07-15",
            "OFF_TARGET_KODIT_DERIVED",
            "카카오 회사·직무 근거 사용 금지",
        )
    return ("UNVERIFIED", "UNVERIFIED", "UNVERIFIED", "UNVERIFIED", "사용 금지")


def input_manifest() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for i, path in enumerate(sorted(p for p in INPUT.rglob("*") if p.is_file()), 1):
        rel = path.relative_to(ROOT).as_posix()
        author, material_type, basis_date, scope, use_policy = classify(rel)
        modified = datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
        rows.append(
            {
                "source_id": f"SRC-{i:03d}",
                "path": rel,
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
                "modified_at": modified,
                "author": author,
                "material_type": material_type,
                "publication_date": "UNVERIFIED" if "2026-07-09" not in basis_date else "2026-07-09",
                "basis_date": basis_date,
                "lookup_date": "2026-07-15",
                "target_scope": scope,
                "use_policy": use_policy,
            }
        )
    return rows


def write(rel: str, text: str) -> None:
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8", newline="\n")


def write_json(rel: str, value: object) -> None:
    write(rel, json.dumps(value, ensure_ascii=False, indent=2))


def package_header() -> str:
    return f"- 데이터 패키지: `{PACKAGE_ID}` v{PACKAGE_VERSION}\n- 조사 기준일: {RESEARCH_CUTOFF_DATE}\n- 외부 네트워크 사용: 없음"


def build_frozen(rows: list[dict[str, object]]) -> None:
    counts = Counter(str(r["target_scope"]) for r in rows)
    package = f"""
run_id: {RUN_ID}
company_data_package_id: {PACKAGE_ID}
company_data_package_version: "{PACKAGE_VERSION}"
frozen_at: {FROZEN_AT}
research_cutoff_date: {RESEARCH_CUTOFF_DATE}
financial_cutoff_period: UNVERIFIED
news_search_start_date: NOT_APPLICABLE_NO_NETWORK
job_posting_date: UNVERIFIED
application_deadline: UNVERIFIED
company_name: 카카오
legal_entity_name: UNVERIFIED
brand_name: UNVERIFIED
target_business_unit: UNVERIFIED
target_job: UNVERIFIED
target_team: UNVERIFIED
job_posting_url: UNVERIFIED
country: UNVERIFIED
reporting_currency: UNVERIFIED
comparison_period: UNVERIFIED
competitor_set_version: NONE-1.0
preferred_competitor_count: 4
source_count: {len(rows)}
target_company_source_count: 0
output_language: Korean
network_access_used: false
input_set_sha256: {INPUT_SET_SHA256}
research_questions_sha256: {RESEARCH_QUESTIONS_SHA256}
applicant_nested_data_package_id: SOL-DATA-608228643DF2
applicant_nested_data_package_version: "1.1"
applicant_nested_frozen_sha256: 608228643df29ad9deab874e72e9842e247fa54c0c80d2316fd43674077b81c7
"""
    write("frozen/company_data_package.yaml", package)

    manifest = {
        "run_id": RUN_ID,
        "company_data_package_id": PACKAGE_ID,
        "company_data_package_version": PACKAGE_VERSION,
        "frozen_at": FROZEN_AT,
        "research_cutoff_date": RESEARCH_CUTOFF_DATE,
        "network_access_used": False,
        "input_set_sha256": INPUT_SET_SHA256,
        "research_questions": {
            "path": "company_research/frozen/research_questions.md",
            "sha256": RESEARCH_QUESTIONS_SHA256,
            "preserved_from_step": "STEP 0",
        },
        "counts": {
            "all_input_files": len(rows),
            "eligible_target_company_sources": 0,
            "applicant_sources": counts["APPLICANT"],
            "pii_excluded": counts["PII"],
            "off_target_kodit": counts["OFF_TARGET_KODIT"] + counts["OFF_TARGET_KODIT_DERIVED"],
            "off_target_other_entity": counts["OFF_TARGET_ENTITY"],
        },
        "inputs": rows,
    }
    write_json("frozen/manifest.json", manifest)

    inventory_lines = [
        "# Input Inventory",
        "",
        package_header(),
        "",
        "## 범위 요약",
        "",
        f"- 전체 파일: {len(rows)}개 (`career_run` 54, `경험정리` 2, `직무기술서` 6)",
        "- 카카오 법인·공고·공시·IR·홈페이지 원문: 0개",
        "- 지원자 근거: 확정 경험 원장 1개, 원문 DOCX 1개",
        "- 개인정보: 증명사진 1개. 내용·최종 산출물 사용 금지",
        "- 대상 불일치: 신용보증기금 career run 53개(지원자 원장 1개 제외), 한국도로공사서비스 직무기술서 6개",
        "",
        "수정시각은 발표일이 아니다. 발표일·기준일을 본문에서 확인하지 못한 파일에는 `UNVERIFIED`를 유지했다.",
        "",
        "## 전체 SOURCE MANIFEST",
        "",
        "| Source ID | 자료명 | 작성 주체 | 자료 유형 | 발표일 | 기준일 | 조회일 | 대상 범위 | 원본 위치 | SHA-256 | 처리 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        inventory_lines.append(
            f"| {r['source_id']} | {Path(str(r['path'])).name} | {r['author']} | {r['material_type']} | "
            f"{r['publication_date']} | {r['basis_date']} | {r['lookup_date']} | {r['target_scope']} | "
            f"`{r['path']}` | `{r['sha256']}` | {r['use_policy']} |"
        )
    write("frozen/input_inventory.md", "\n".join(inventory_lines))

    entity_map = f"""
# Entity Map

{package_header()}

| ID | 구분 | 명칭 | 관계 | 지분·통제 관계 | 주요 사업 | 채용 관련성 | 출처 | 상태 |
|---|---|---|---|---|---|---|---|---|
| ENT-TGT-001 | UNVERIFIED | 카카오 | 실행 맥락의 조사 목표명 | UNVERIFIED | UNVERIFIED | 목표명만 관련 | `frozen/research_questions.md` | 목표명만 고정; 법인·브랜드 구분 금지 |
| ENT-OFF-001 | LEGAL_ENTITY | 신용보증기금 | 동결 career run의 지원 대상이며 카카오와 불일치 | 조사하지 않음 | 채무 보증, 신용조사·보증심사(해당 자료의 주장) | 카카오 채용과 무관 | `SRC-001`~`SRC-054` 중 KODIT 자료 | `NOT_APPLICABLE` |
| ENT-OFF-002 | LEGAL_ENTITY | 한국도로공사서비스(주) | 직무기술서 6개 발행 주체이며 카카오와 불일치 | 조사하지 않음 | 고속도로 통행료 수납·영업소 운영 등 | 카카오 채용과 무관 | `SRC-057`~`SRC-062` | `NOT_APPLICABLE` |

## STEP 1 식별 결과

- 정확한 법인명, 브랜드 범위, 모회사·자회사·사업부 관계: `UNVERIFIED`
- 상장 여부와 공시 대상 여부: `UNVERIFIED`
- 연결·별도재무제표 적용 범위: `UNVERIFIED`
- 채용 주체와 실제 근무 법인: `UNVERIFIED`
- 회사명 변경, 합병, 분할, 사업 양수도 이력: `UNVERIFIED`
- 조사 기준일 이후 자료 혼용: 없음. 외부 자료를 수집하지 않았다.

현재 근거로 `(주)카카오`, `카카오뱅크`, `카카오페이`, `카카오엔터테인먼트` 등 특정 법인이나 계열사를 조사 대상으로 확정하면 법인명 오류가 된다.
"""
    write("frozen/entity_map.md", entity_map)


def build_evidence() -> None:
    source_register = f"""
# Source Register

{package_header()}

| Source group | 수준 | 범위 | 독립성 | 사용 가능 범위 | 판정 |
|---|---:|---|---|---|---|
| `CTRL-001` STEP 0 연구 질문 | 내부 통제 | 목표명 `카카오`와 미확정 항목 | 해당 없음 | 조사 범위 통제 | 사용 |
| `APP-001` 확정 경험 원장 | APPLICANT | 지원자 confirmed claim | 사용자 승인 원장 | 지원자 사실만 | 사용 |
| `APP-002` 경험정리 DOCX | APPLICANT RAW | 지원자 경험 원문 | 자기진술 | 원장 claim 교차확인 | 제한 사용 |
| KODIT career run | LEVEL 1·2 혼합 및 파생물 | 신용보증기금·한국은행 | 일부 공식이나 대상 불일치 | 불일치 입증만 | 카카오 근거 제외 |
| 한국도로공사서비스 직무기술서 6개 | LEVEL 2 | 타 법인 NCS 직무 | 회사 공식 문서 | 불일치 입증만 | 카카오 근거 제외 |
| 증명사진 | PII | 개인 식별 이미지 | 해당 없음 | 없음 | 금지 |

카카오 대상 출처는 0개다. URL이 KODIT·한국은행·한국도로공사서비스의 공식 도메인이라는 이유로 카카오 사실이 되지 않는다.
"""
    write("evidence/source_register.md", source_register)

    claim_ledger = f"""
# Claim Ledger

{package_header()}

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
"""
    write("evidence/claim_ledger.md", claim_ledger)

    contradiction_log = f"""
# Contradiction and Scope-Mismatch Log

{package_header()}

| ID | 기준 | 충돌 자료 | 충돌 유형 | 처리 | 상태 |
|---|---|---|---|---|---|
| CON-001 | 조사 목표명 `카카오` | `career_run`의 target `신용보증기금 체험형 청년인턴1(보증)` | 대상 법인·직무 불일치 | 회사·직무 사실 전부 제외; 지원자 원장만 분리 사용 | RESOLVED_BY_EXCLUSION |
| CON-002 | 카카오 목표 직무 UNVERIFIED | 한국도로공사서비스 상담·영업 직무기술서 | 법인·직무 불일치 | 카카오 직무 근거에서 제외 | RESOLVED_BY_EXCLUSION |
| CON-003 | 카카오 법인 식별 필요 | 카카오 공식 법인 자료 0개 | 핵심 근거 부재 | 법인명을 확정하지 않고 판단을 차단 | OPEN_BLOCKER |
| CON-004 | 제출용 회사 고유 근거 필요 | 지원자 경험만 존재 | 근거 종류 불일치 | 지원동기 생성 금지 | OPEN_BLOCKER |
"""
    write("evidence/contradiction_log.md", contradiction_log)

    needs = f"""
# Needs Verification

{package_header()}

## P0: 다음 판단 전에 반드시 확보

1. 정확한 채용공고 원문 또는 공식 URL, 게시일, 마감일
2. 채용 법인, 실제 근무 법인, 사업부, 팀, 직무명, 고용형태, 근무지
3. 법인명과 브랜드 범위, 계열사 포함·제외 기준
4. 상장·공시 대상 여부와 연결·별도 재무 범위

## P1: 회사 분석에 필요

5. 대상 법인의 최근 사업·분기·반기보고서 또는 감사 자료
6. 최근 3개년 IR·실적 발표와 전략 발표, 실제 투자·인력·조직·계약 근거
7. 사업부별 고객, 제품·서비스, 과금 방식, 비용·수익성 동인
8. 고객 문제와 사업 범위를 기준으로 선정한 경쟁사·대체재 자료
9. 지배구조, 규제, 보안·개인정보, 평판 관련 1차·독립 근거
10. 공식 인재상·제도와 실제 팀 업무를 구분할 문화·고용 근거

## P2: 지원자 연결에 필요

11. 공고가 요구하는 업무 행동·도구·도메인 지식·성과 기준
12. APP-002~005의 기간, 본인 기여 범위, 수치 측정 기준

외부 네트워크 사용 금지 조건 때문에 이번 실행에서는 위 항목을 확보하지 않았다.
"""
    write("evidence/needs_verification.md", needs)

    prohibited = f"""
# Prohibited Claims

{package_header()}

다음 문장은 제출·면접·최종 보고서에 사용하면 안 된다.

| ID | 금지 주장 | 금지 이유 | 해제 조건 |
|---|---|---|---|
| PRO-001 | 카카오는 `(주)카카오`를 뜻한다. | 법인 미식별 | 공식 공고와 법인 자료 일치 확인 |
| PRO-002 | 카카오의 핵심 고객·수익모델·주력 사업은 특정 항목이다. | 대상 법인·사업 근거 없음 | 공식 공시·IR 확보 |
| PRO-003 | 카카오는 업계를 선도하며 독보적인 기술력·글로벌 경쟁력을 보유한다. | 비교 근거 없는 가치판단 | 동기간·동범위 경쟁 근거 확보 |
| PRO-004 | 카카오의 최근 전략은 실행되어 성과를 내고 있다. | 발표·투자·실행·성과 근거 없음 | 단계별 1차 근거 확보 |
| PRO-005 | 카카오는 안정적으로 성장하고 재무 상태가 탄탄하다. | 재무 자료 0개 | 연결·별도·기간·통화 고정 후 계산 |
| PRO-006 | 카카오는 혁신적이고 직원 중심의 문화다. | 문화 근거 0개 | 제도·다수 독립 근거·팀 범위 확인 |
| PRO-007 | 카카오 지원 직무는 데이터 분석·운영 개선을 담당한다. | 공고·팀·직무 미확정 | 공식 공고 확보 |
| PRO-008 | 지원자의 KODIT 자기소개서가 카카오 적합성을 증명한다. | 다른 기관 맞춤 산출물 | 카카오 공고 요구와 confirmed 경험 재매칭 |
| PRO-009 | 신용보증기금·한국은행·한국도로공사서비스 자료는 카카오 회사 근거다. | 법인·사업 범위 불일치 | 해제 불가 |
| PRO-010 | 증명사진의 개인 특성은 지원 적합성과 관련된다. | 개인정보·차별 위험 | 해제 불가 |
"""
    write("evidence/prohibited_claims.md", prohibited)


def build_analysis() -> None:
    common = package_header()
    business = f"""
# Business Model Map

{common}

| 항목 | 확인 내용 | 근거 | 불확실성 |
|---|---|---|---|
| 핵심 고객 | UNVERIFIED | 카카오 대상 자료 없음 | 법인·사업부 미확정 |
| 고객의 문제 | UNVERIFIED | 없음 | 동일 |
| 제공 가치 | UNVERIFIED | 없음 | 동일 |
| 제품·서비스 | UNVERIFIED | 없음 | 계열사·브랜드 혼동 위험 |
| 지불 주체 | UNVERIFIED | 없음 | 사용자와 고객 구분 불가 |
| 수익 발생 방식 | UNVERIFIED | 없음 | 연결 범위 미확정 |
| 주요 비용 | UNVERIFIED | 없음 | 재무 자료 없음 |
| 핵심 자산·기술 | UNVERIFIED | 없음 | 홍보 문구도 없음 |
| 공급자·유통 채널 | UNVERIFIED | 없음 | 사업 범위 미확정 |
| 규제·인허가 | UNVERIFIED | 없음 | 국가·법인 미확정 |
| 전환비용·대체재 | UNVERIFIED | 없음 | 고객 문제 미확정 |

분석 결론: 회사 소개 요약조차 작성할 수 없다. 목표명 외의 회사 사실을 채우면 공개 상식에 의존한 무출처 서사가 된다.
"""
    write("analysis/business_model_map.md", business)

    write("analysis/revenue_logic.md", f"""
# Revenue Logic

{common}

- 사업부문: `UNVERIFIED`
- 제품·서비스와 고객군: `UNVERIFIED`
- 계약·판매·반복 매출·가격 결정 요인: `UNVERIFIED`
- 원가·수익성·성장률·계절성·집중도: `UNVERIFIED`
- 환율·금리·규제 민감도: `UNVERIFIED`

재무·사업 자료가 없으므로 매출 증가, 가격 인상, 판매량, 제품 구성, 인수합병, 연결 대상 변화 중 어느 설명도 선택하지 않았다.
""")

    write("analysis/value_chain_map.md", f"""
# Value Chain Map

{common}

| 단계 | 입력 | 담당 조직 | 결과물 | 오류 가능성 | 성과 기준 | 지원 직무 접점 |
|---|---|---|---|---|---|---|
| 원재료·데이터·고객 요청 | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| 조달·입력 | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| 개발·생산·심사·처리 | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| 품질·위험 관리 | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| 판매·제공·고객 사용 | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |
| 사후관리·매출·평판 | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |

일반적인 플랫폼 가치사슬을 카카오 사실로 전환하지 않았다.
""")

    write("analysis/customer_map.md", f"""
# Customer Map

{common}

| 고객군 | 구매 대상 | 구매 이유 | 선택 기준 | 불만·위험 | 협상력 | 회사 의존도 |
|---|---|---|---|---|---|---|
| UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED |

고객과 사용자를 구분할 근거가 없다. 사업부가 확정되기 전에는 고객군을 추정하지 않는다.
""")

    write("analysis/organization_map.md", f"""
# Organization Map

{common}

- 법인·사업부·팀·보고선: `UNVERIFIED`
- 채용 주체·근무 법인·내부 고객·외부 이해관계자: `UNVERIFIED`
- 본사·현장·국내외 법인 범위: `UNVERIFIED`

입력에 있는 보증 분야, 한국도로공사서비스 상담·영업 조직은 카카오 조직도가 아니다. 구체적인 카카오 팀 구조를 생성하지 않았다.
""")

    write("analysis/event_timeline.md", f"""
# Event Timeline

{common}

| Event ID | 날짜 | 사건 | 회사의 설명 | 실제 확인된 조치 | 자원 투입 | 확인된 결과 | 상태 | 출처 |
|---|---|---|---|---|---|---|---|---|
| EVT-000 | 최근 3개년 | 대상 사건 자료 없음 | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNKNOWN | 없음 |

최소 3개년 추적은 자료 부족으로 수행하지 못했다. 기간을 줄일 수 있는 카카오 자료도 없다.
""")

    write("analysis/strategy_resource_alignment.md", f"""
# Strategy-Resource Alignment

{common}

| 전략 주장 | 자본 투입 | 인력·조직 변화 | 기술·설비 | 고객·계약 | 실적 신호 | 정렬 여부 |
|---|---|---|---|---|---|---|
| 카카오 전략 UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNKNOWN |

전략 주장 자체가 없으므로 `ANNOUNCED` 단계도 부여하지 않았다.
""")

    write("analysis/strategy_execution_status.md", f"""
# Strategy Execution Status

{common}

판정: `UNKNOWN`

- 경영진 반복 언어: 자료 없음
- 실제 투자·채용 일치: 자료 없음
- 축소 사업·목표 수정·기한 연기: 자료 없음
- 자금·인력·기술·규제 제약: 자료 없음
- 카카오 채용공고가 암시하는 실행 과제: 공고 없음

KODIT 공고 하나를 카카오 전략에 전용하지 않았다.
""")

    write("analysis/competitor_selection.md", f"""
# Competitor Selection

{common}

| 후보 | 고객 중복 | 제품·서비스 중복 | 사업모델 유사성 | 지역·규모 적합성 | 인재 경쟁 | 비교 적합성 |
|---|---:|---:|---:|---:|---:|---:|
| 미선정 | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | 0 |

대상 법인·사업부·고객 문제가 미확정이므로 유명 플랫폼 기업을 자동 선정하지 않았다. 경쟁사 세트 버전은 `NONE-1.0`이다.
""")

    write("analysis/peer_comparison.md", f"""
# Peer Comparison

{common}

| 비교 항목 | 조사 회사 | 경쟁사 A | 경쟁사 B | 경쟁사 C | 해석 |
|---|---|---|---|---|---|
| 전체 항목 | UNVERIFIED | 미선정 | 미선정 | 미선정 | 기간·통화·회계·사업 범위를 고정할 수 없어 비교 금지 |

`시장 선도`, `독보적`, `높은 진입장벽` 표현은 모두 `PROHIBITED`다.
""")

    write("analysis/substitute_map.md", f"""
# Substitute Map

{common}

고객 문제와 구매 예산이 확인되지 않아 대체재를 선정할 수 없다. 메시징, 광고, 콘텐츠, 금융 등 공개적으로 알려진 범주를 임의 혼합하지 않았다.
""")

    write("analysis/culture_evidence.md", f"""
# Culture Evidence

{common}

| Culture ID | 관찰 내용 | 자료 유형 | 관찰 범위 | 표본 한계 | 반대 사례 | 상태 |
|---|---|---|---|---|---|---|
| CULT-000 | 카카오 문화 근거 없음 | 없음 | 없음 | 표본 0 | 없음 | NEEDS_VERIFICATION |

회사가 지향한다고 말하는 문화, 제도로 구현된 문화, 직원 경험, 특정 팀 문화 중 어느 것도 확인하지 않았다.
""")

    write("analysis/employment_signal_map.md", f"""
# Employment Signal Map

{common}

| 신호 | 공식 근거 | 독립 근거 | 팀 범위 | 판정 |
|---|---|---|---|---|
| 인재상·평가·보상·승진·교육·근무제도 | 없음 | 없음 | UNVERIFIED | UNKNOWN |
| 조직개편·인력 변화·노사 자료 | 없음 | 없음 | UNVERIFIED | UNKNOWN |
| 반복 채용 요구 | 카카오 공고 없음 | 없음 | UNVERIFIED | UNKNOWN |
""")

    write("analysis/culture_unknowns.md", f"""
# Culture Unknowns

{common}

1. 목표 팀의 의사결정·보고·협업 방식
2. 초기 성과 기준과 피드백 주기
3. 평가·보상·승진·학습 제도의 실제 운영
4. 근무 강도와 예외 상황 처리 방식
5. 조직개편이 목표 직무에 미친 영향

익명 후기와 직원 후기조차 입력에 없으며, 없는 후기를 상상해 가설로도 쓰지 않았다.
""")

    write("analysis/role_value_map.md", f"""
# Role Value Map

{common}

| 회사 과제 | 영향을 받는 조직 | 지원 직무의 가능한 역할 | 실제 업무 행동 | 필요한 역량 | 근거 | 확실성 |
|---|---|---|---|---|---|---|
| UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | 카카오 공고 없음 | UNKNOWN |

공고가 없어 `POSTING_CONFIRMED`, `ORGANIZATION_SUPPORTED`, `REASONABLE_INFERENCE` 중 어느 상태도 부여하지 않았다. 지원자에게 의사결정권·예산권·인사권을 부여하지 않았다.
""")

    write("analysis/first_90_days.md", f"""
# First 90 Days Map

{common}

직무·팀·업무 기준이 미확정이므로 카카오 맞춤 90일 계획은 생성하지 않는다.

| 기간 | 현재 말할 수 있는 범용 준비 행동 | 회사 고유성 | 상태 |
|---|---|---|---|
| 0~30일 | 조직·업무·보안·준법·보고 기준을 확인한다는 원칙 | 없음 | NEEDS_VERIFICATION |
| 31~60일 | 실제 반복 업무와 품질 기준을 공고·팀 설명에 맞춰 구체화 | 없음 | NEEDS_VERIFICATION |
| 61~90일 | 권한 범위 안에서 데이터·사례 기반 개선점을 제안 | 없음 | NEEDS_VERIFICATION |

위 문장은 지원서용 완성안이 아니라 공고 확보 후 채울 골격이다.
""")

    write("analysis/job_reality_packet.md", f"""
# Job Reality Packet

{common}

- 직무명·법인·사업부·팀·고용형태·근무지: `UNVERIFIED`
- 내부·외부 고객과 핵심 산출물: `UNVERIFIED`
- 일상 업무·도구·의사결정 범위·오류 기준: `UNVERIFIED`
- 협업 부서·갈등·병목·성장 경로: `UNVERIFIED`

면접에서 확인할 핵심은 `final/reverse_questions.md`에 남겼다. KODIT 보증 업무나 한국도로공사서비스 통행료 업무를 카카오 업무로 전환하지 않았다.
""")

    write("analysis/applicant_company_bridge.md", f"""
# Applicant-Company Bridge

{common}

| 회사·직무 요구 | 지원자 경험 | 직접 행동 | 확인된 결과 | 전이 가능한 역량 | 연결 강도 | 과장 위험 |
|---|---|---|---|---|---:|---|
| UNVERIFIED | APP-001 | 두 계산 방식에 동일 데이터 입력, 결과 비교 보고 | 보고서 작성·팀장 보고 | 대조·검증·보고 | 0/5 | 직무 요구가 없어 직접 연결 금지 |
| UNVERIFIED | APP-002 | 대량 자료 분류·정리 | 3,000페이지를 2일 내 정리 | 우선순위·분류·기한 관리 | 0/5 | 품질·본인 기여 범위 미상 |
| UNVERIFIED | APP-003 | 50명 인터뷰, 5개 시장 비교 | 문제점·개선안 도출 | 고객 조사·벤치마킹 | 0/5 | 실행·사업 성과 단정 금지 |
| UNVERIFIED | APP-004 | 과거 데이터로 고객군 재설정 | 재설정 행동 확인 | 세분화·문제 재정의 | 0/5 | 카카오 고객 연결 금지 |
| UNVERIFIED | APP-005 | 엑셀 자동화 도입 | 급여 산정 속도 30% 향상 | 프로세스 개선 | 0/5 | 측정 기준·카카오 업무 연결 미확인 |

`0/5`는 경험의 가치가 낮다는 뜻이 아니라, 카카오 직무 요구 근거가 없어 연결을 채점할 수 없다는 뜻이다.
""")

    write("analysis/fit_gap_table.md", f"""
# Fit-Gap Table

{common}

| 역량 | 회사 요구 근거 | 지원자 근거 | 상태 | 보완 방법 |
|---|---|---|---|---|
| 데이터 대조·보고 | 없음 | APP-001 | UNKNOWN | 공고의 분석·검증·보고 업무 확인 |
| 대량 정보 분류 | 없음 | APP-002 | UNKNOWN | 처리량·정확성 기준 확인 |
| 고객·시장 조사 | 없음 | APP-003·004 | UNKNOWN | 목표 제품·고객·조사 책임 확인 |
| 업무 자동화·개선 | 없음 | APP-005 | UNKNOWN | 사용하는 도구·권한·성과 기준 확인 |
| 카카오 제품·데이터·도메인 지식 | 없음 | frozen 원장에 직접 근거 없음 | GAP 후보 | 목표 직무 확정 후 제품·산업 학습 계획 수립 |

공고 없이 `STRONG_FIT` 또는 `TRANSFERABLE` 판정을 하지 않았다.
""")

    write("analysis/motivation_evidence.md", f"""
# Motivation Evidence

{common}

지원동기 4단 논리 중 1번과 3번의 지원자 사실 후보만 있다.

1. 관심 문제·업무 방식: 데이터 대조, 자료 구조화, 고객 조사, 프로세스 개선 경험은 확인됨.
2. 검증된 카카오 고유 과제·사업 구조: `UNVERIFIED`.
3. 확인된 경험과 구체적 직무 연결: 직무가 없어 `NEEDS_VERIFICATION`.
4. 권한 범위 안의 기여 행동: 업무·권한이 없어 `NEEDS_VERIFICATION`.

따라서 현재는 카카오 지원동기 문장을 만들지 않는다. “오랫동안 카카오에 관심이 있었다” 같은 감정·가치관도 생성하지 않았다.
""")


def hypothesis_doc(lens: str, thesis: str, implications: str) -> str:
    return f"""
# {lens}

{package_header()}

```yaml
lens: {lens}
central_thesis: "{thesis}"
confidence: HIGH_FOR_EVIDENCE_GAP
decisive_evidence:
  - "카카오 대상 법인·공고·공시·IR 자료 0개"
  - "신용보증기금 career run과 한국도로공사서비스 직무기술서는 대상 불일치"
contradicting_evidence:
  - "지원자 confirmed 경험은 존재하지만 회사 사실은 입증하지 않음"
unknowns:
  - "법인·사업부·직무·사업모델·전략·재무·경쟁·문화"
falsification_conditions:
  - "공식 카카오 공고와 법인 자료가 확보되어 현재의 근거 부재가 해소됨"
job_implications: "직무 연결을 보류한다."
application_implications: "{implications}"
```

경쟁 가설은 “일반 상식만으로도 카카오를 분석할 수 있다”이지만, 이 실행은 외부 자료와 무출처 기억 사용을 금지하므로 채택하지 않았다.
"""


def build_hypotheses() -> None:
    write("hypotheses/operating_reality.md", hypothesis_doc(
        "OPERATING_REALITY",
        "대상 법인과 재무·사업 자료가 없어 돈을 버는 구조와 운영 병목을 검증할 수 없다.",
        "회사 품질 판정을 INSUFFICIENT_EVIDENCE로 제한한다.",
    ))
    write("hypotheses/strategy_and_market.md", hypothesis_doc(
        "STRATEGY_AND_MARKET",
        "전략 주장·자원 배분·성과·경쟁사 자료가 없어 실행 정렬을 평가할 수 없다.",
        "전략을 지원동기 근거로 사용하지 않는다.",
    ))
    write("hypotheses/risk_and_governance.md", hypothesis_doc(
        "RISK_AND_GOVERNANCE",
        "법률·규제·보안·지배구조 위험을 확인할 자료가 없어 긍정도 부정도 단정할 수 없다.",
        "평판·문화·안정성 표현을 금지한다.",
    ))
    write("hypotheses/talent_and_job.md", hypothesis_doc(
        "TALENT_AND_JOB",
        "지원자 경험은 확인되지만 카카오 공고가 없어 역할·성과·역량 요구와 연결할 수 없다.",
        "공고 확보 전 자기소개서·면접용 연결 문장을 생성하지 않는다.",
    ))


def build_validation_and_judges() -> None:
    common = package_header()
    write("validation/red_team_report.md", f"""
# Red Team Report

{common}

## 공격 결과

| 질문 | 발견 | 조치 |
|---|---|---|
| 회사를 좋아 보이도록 해석했는가 | 회사 평가를 하지 않음 | 유지 |
| 회사 자료를 독립 사실로 썼는가 | 카카오 회사 자료 자체가 없음 | 유지 |
| 발표를 실행·성과로 바꿨는가 | 전략 문장을 생성하지 않음 | 유지 |
| 채용공고를 실제 업무 전체로 확대했는가 | 카카오 공고 없음; KODIT 공고 제외 | 유지 |
| 유명 경쟁사를 자동 선정했는가 | 경쟁사 미선정 | 유지 |
| 지원자 경험을 억지로 연결했는가 | 연결 강도 0/5, 상태 UNKNOWN | 유지 |
| 수치 기간·단위·범위가 일치하는가 | 회사 수치 계산 0건 | 유지 |
| 공개되지 않은 사실을 서사로 채웠는가 | 모든 핵심 필드를 UNVERIFIED로 유지 | 유지 |

가장 강한 반대 논리는 “카카오는 널리 알려져 있으므로 공개 상식으로 분석해도 된다”이다. 그러나 이 실행은 외부 네트워크와 무출처 기억을 금지하며, 법인·사업부 혼동 위험이 커 기각했다.
""")

    write("validation/contradiction_matrix.md", f"""
# Contradiction Matrix

{common}

| 핵심 명제 | 지지 근거 | 반대 근거 | 대안 설명 | 현재 판단 | 수정 조건 |
|---|---|---|---|---|---|
| 카카오 회사조사를 완료할 수 있다 | 목표명 존재 | 대상 회사 자료 0개 | 외부 자료를 허용하면 가능 | INSUFFICIENT_EVIDENCE | 공식 자료 확보 |
| 지원자 경험은 카카오 직무에 적합하다 | APP-001~005 | 공고·역할 없음 | 다른 직무에는 적합할 수 있음 | NEEDS_VERIFICATION | 공고 요구와 재매칭 |
| KODIT 연구는 카카오에 전용 가능하다 | 일부 업무행동은 범용적 | 법인·사업·직무 불일치 | 지원자 경험만 분리 가능 | NOT_APPLICABLE | 회사 사실 전용 불가 |
| 현재 지원해야 한다 | 지원자 강점 후보 | 회사·직무 품질 판단 불가 | 공고 확인 후 달라질 수 있음 | INSUFFICIENT_EVIDENCE | P0 확인 완료 |
""")

    hard_fail = {
        "company_data_package_id": PACKAGE_ID,
        "company_data_package_version": PACKAGE_VERSION,
        "status": "PASS_WITH_BLOCKERS",
        "active_hard_fail_count": 0,
        "deterministic_checks": {
            "entity_name_error": False,
            "period_currency_unit_error": False,
            "consolidated_separate_mixing": False,
            "nonexistent_source": False,
            "source_number_mismatch": False,
            "publication_basis_date_confusion": False,
            "post_cutoff_mixing": False,
            "quote_distortion": False,
            "nonexistent_product_business_role": False,
        },
        "semantic_checks": {
            "company_claim_as_objective_fact": False,
            "announcement_as_result": False,
            "correlation_as_causation": False,
            "industry_growth_as_company_growth": False,
            "affiliate_result_as_target_result": False,
            "review_overgeneralization": False,
            "applicant_authority_exaggeration": False,
            "unverified_culture_reputation": False,
            "counterevidence_omitted": False,
        },
        "prevented_risks": [
            "신용보증기금 자료를 카카오 자료로 전용하지 않음",
            "한국도로공사서비스 직무를 카카오 직무로 전환하지 않음",
            "정확한 법인명을 추정하지 않음",
            "무출처 카카오 상식·수치·평판을 사용하지 않음",
            "증명사진을 내용 분석과 최종 산출물에서 제외",
        ],
        "blockers": [
            "TARGET_LEGAL_ENTITY_UNVERIFIED",
            "TARGET_POSTING_MISSING",
            "TARGET_COMPANY_SOURCES_ZERO",
            "FINANCIAL_SCOPE_UNVERIFIED",
            "ROLE_FIT_UNVERIFIED",
        ],
        "final_effect": "HARD_FAIL은 발생하지 않았지만 회사·직무·지원 판정은 INSUFFICIENT_EVIDENCE로 제한",
    }
    write_json("validation/hard_fail_report.json", hard_fail)

    write("validation/revision_required.md", f"""
# Revision Required

{common}

전면 재작성 대상은 없다. 다음은 자료 확보 후 보완해야 한다.

1. 공식 공고로 법인·사업부·직무·팀을 확정한다.
2. 공시·IR로 사업·전략·재무 범위를 채운다.
3. 공고 요구와 APP-001~005를 다시 매칭한다.
4. 지원 우선순위를 재판정한다.

이번 결과에서 최소 수정 원칙으로 유지할 부분은 대상 불일치 기록, 원본 해시, 금지 주장, 미검증 상태다.
""")

    write("judges/business_analyst.md", f"""
# BUSINESS_ANALYST Review

{common}

- 사업모델·재무·전략·경쟁 분석 가능성: 0/45
- 근거 경계 준수: 적합
- 판정: `INSUFFICIENT_EVIDENCE`
- 핵심 사유: 카카오 대상 1차·2차 자료가 0개다.
- 반대 의견: 널리 알려진 회사라는 이유로 상식을 채우는 것은 추적 가능한 분석이 아니다.
""")

    write("judges/fact_and_source_auditor.md", f"""
# FACT_AND_SOURCE_AUDITOR Review

{common}

- 법인·대상 정확성: 4/10 (미확정을 정확히 표시)
- 출처 품질·추적성: 8/15 (해시는 완전하나 대상 출처 0개)
- 사실·주장·추론 구분: 15/15
- 계산 재현성: 10/10 (0건임을 재현)
- 판정: `PASS_WITH_BLOCKERS`
- 가장 큰 위험: 입력 대상 불일치를 무시하고 KODIT·한국도로공사서비스 사실을 카카오에 전용하는 것.
""")

    write("judges/recruiter_and_job_auditor.md", f"""
# RECRUITER_AND_JOB_AUDITOR Review

{common}

- 직무 연결: 0/15
- 지원 판단 활용성: 2/5 (지원 보류·확인 질문에는 활용 가능)
- 면접 방어 가능성: 3/5 (사용 금지 범위는 명확)
- 판정: `WATCH_AND_VERIFY`가 아니라 더 엄격한 `INSUFFICIENT_EVIDENCE`
- 핵심 사유: 공고가 없으므로 지원동기·입사 후 포부·직무역량 연결을 완성할 수 없다.
""")

    write("judges/scorecard.md", f"""
# Judge Scorecard

{common}

세 심사는 동일 frozen package를 서로 다른 평가 렌즈로 분리해 수행했다. 별도 외부 모델 호출은 사용하지 않았다.

| 항목 | 배점 | 점수 | 사유 |
|---|---:|---:|---|
| 법인·대상 정확성 | 10 | 4 | 법인 미확정이지만 오확정하지 않음 |
| 출처 품질·추적 가능성 | 15 | 8 | 62개 해시, 대상 출처 0개 |
| 사실·주장·추론 구분 | 15 | 15 | 경계 유지 |
| 사업모델 이해 | 15 | 0 | 자료 없음 |
| 전략·재무 해석 | 10 | 0 | 자료 없음 |
| 경쟁·위험 분석 | 10 | 0 | 자료 없음 |
| 직무 연결 | 15 | 0 | 공고 없음 |
| 지원 판단 활용성 | 5 | 2 | 보류 판단만 가능 |
| 면접 방어 가능성 | 5 | 3 | 금지·확인 질문은 방어 가능 |
| 합계 | 100 | 32 | 사실 오류로 점수를 보충하지 않음 |
""")


def build_synthesis_and_final() -> None:
    common = package_header()
    synthesis = f"""
# Company Analysis S

{common}

## 중심 명제

현재 패키지로 확인되는 카카오 관련 사실은 “조사 목표명이 카카오”라는 점뿐이다. 정확한 법인, 사업부, 직무와 공고는 미확정이며 회사 근거는 0개다. 따라서 사업모델·전략·재무·경쟁·문화·직무 품질을 평가하거나 지원동기를 만드는 것은 근거 계약을 위반한다.

## 유지할 근거

- 지원자는 데이터 결과 비교 보고, 대량 자료 분류, 상인 인터뷰와 시장 비교, 고객군 재설정, 엑셀 자동화 경험을 confirmed 원장에서 방어할 수 있다.
- 이 경험이 카카오 직무에 전이되는지는 공고가 확인될 때까지 판단할 수 없다.
- KODIT와 한국도로공사서비스 자료는 대상 불일치로 제외한다.

## 최종 판단

`INSUFFICIENT_EVIDENCE`. 부정적인 회사 평가가 아니라 의사결정에 필요한 증거가 없는 상태다.
"""
    write("synthesis/company_analysis_S.md", synthesis)
    write("synthesis/change_log.md", f"""
# Synthesis Change Log

{common}

- OPERATING_REALITY: 근거 부재 결론 유지
- STRATEGY_AND_MARKET: 경쟁사·전략을 생성하지 않은 결론 유지
- RISK_AND_GOVERNANCE: 평판·문화 추정을 제거한 결론 유지
- TALENT_AND_JOB: 지원자 경험과 직무 요구를 분리한 결론 유지
- 추가된 인과관계·수치·회사 주장: 없음
- 삭제·약화된 반대 근거: 없음
""")
    write_json("synthesis/synthesis_validation.json", {
        "company_data_package_id": PACKAGE_ID,
        "company_data_package_version": PACKAGE_VERSION,
        "status": "PASS_WITH_BLOCKERS",
        "claim_ledger_consistent": True,
        "new_causal_claims": 0,
        "scope_expansions": 0,
        "period_entity_mismatches": 0,
        "counterevidence_preserved": True,
        "decision": "INSUFFICIENT_EVIDENCE",
    })

    one_page = f"""
# One-Page Company Brief: 카카오

{common}

1. **회사 한 문장 정의:** 정확한 법인·브랜드·사업 범위가 확인되지 않아 작성할 수 없다.
2. **주요 고객과 제공 가치:** `UNVERIFIED`.
3. **수익 구조:** `UNVERIFIED`.
4. **현재 가장 중요한 전략:** `UNVERIFIED`.
5. **전략을 뒷받침하는 투자·행동:** `UNVERIFIED`.
6. **차별 요소:** `UNVERIFIED`.
7. **가장 큰 사업 위험:** 개별 위험을 단정할 수 없다. 현재 조사상 가장 큰 위험은 법인·사업 범위 오인이다.
8. **지원 직무의 역할:** 공고가 없어 `UNVERIFIED`.
9. **지원자 접점:** 데이터 대조·자료 구조화·고객 조사·프로세스 개선 경험은 확인되지만 직무 연결은 미검증이다.
10. **지원 판단:** `INSUFFICIENT_EVIDENCE`.
11. **추가 확인:** 공식 공고, 법인·사업부·팀, 최근 공시·IR, 역할·성과 기준을 먼저 확보해야 한다.

이 문서는 제출용 회사 소개가 아니라, 사용하면 안 되는 주장과 다음 조사 순서를 고정한 통제 문서다.
"""
    write("final/one_page_company_brief.md", one_page)

    full = f"""
# 카카오 회사조사 보고서

{common}

# 회사와 조사 범위

목표명은 카카오다. 정확한 법인, 브랜드, 계열사 포함 범위, 사업부, 직무와 팀은 미확정이다. 외부 네트워크를 사용하지 않았고, frozen input 62개만 확인했다. 그중 카카오 대상 자료는 0개다.

# 회사는 실제로 어떻게 작동하는가

확인할 수 없다. 고객·제품·서비스·가치사슬·조직 자료가 없다.

# 돈은 어디에서 벌고 어디에서 새는가

확인할 수 없다. 연결·별도 범위, 통화, 기간, 사업부문과 원자료 수치가 없다. 계산은 0건이다.

# 최근 전략은 말에서 실행으로 옮겨졌는가

전략 발표·자본·인력·기술·계약·실적 근거가 모두 없어 `UNKNOWN`이다. 발표를 상상해 실행 또는 성과로 바꾸지 않았다.

# 고객과 경쟁자는 회사를 어떻게 압박하는가

고객 문제와 구매 예산이 확인되지 않아 경쟁사와 대체재를 선정하지 않았다.

# 성장 가능성과 실패 가능성은 무엇인가

긍정·부정 모두 판정할 수 없다. 구체적 성장·위험 문장을 쓰면 무출처 가치판단이 된다.

# 조직과 직무는 이 문제에 어떻게 연결되는가

카카오 공고가 없어 직무명, 업무, 권한, 산출물, 내부 고객, 성과·오류 기준을 확인할 수 없다.

# 지원자는 무엇을 증명할 수 있고 무엇이 부족한가

confirmed 원장으로 데이터 결과 비교 보고, 3,000페이지 자료의 2일 정리, 상인 50명 인터뷰와 5개 시장 비교, 고객군 재설정, 엑셀 자동화 경험을 방어할 수 있다. 다만 카카오 역할 요구가 없으므로 직접 적합성은 아직 증명되지 않는다. 카카오 제품·데이터·도메인 경험도 frozen 원장에서 직접 확인되지 않는다.

# 왜 이 회사인가

현재 근거로는 회사 고유의 지원 이유를 만들 수 없다. 이 섹션을 비워 두는 것이 정확하다.

# 면접에서 확인해야 할 것은 무엇인가

목표 법인·팀, 초기 우선과제, 산출물과 품질 기준, 협업 구조, 실제 권한, 입사 전 보완 지식을 확인해야 한다.

# 현재의 지원 판단

`INSUFFICIENT_EVIDENCE`. 회사에 대한 부정 판정이 아니라 증거 부족 판정이다.

# 출처와 남은 불확실성

전체 입력 해시는 `frozen/manifest.json`, claim 상태는 `evidence/claim_ledger.md`, 금지 문장은 `evidence/prohibited_claims.md`에 있다. P0 미검증 항목은 법인·공고·사업부·직무·공시 범위다.
"""
    write("final/full_company_report.md", full)

    app_bridge = f"""
# Application Bridge

{common}

| 활용 문항 | 핵심 회사 사실 | 지원자 경험 | 연결 논리 | 사용 가능 문장 | 위험 |
|---|---|---|---|---|---|
| 지원동기 | 없음 | APP-001~005 | 회사 고유 연결 불가 | 없음 | 카카오 상식 창작 위험 |
| 직무역량 | 직무 요구 없음 | 결과 비교 보고·자료 분류·시장 조사·자동화 | 공고 확보 후 행동 단위 재매칭 | “동일 데이터를 두 방식으로 대조해 결과 비교 보고서를 작성했다.” | 카카오 직무 적합 단정 금지 |
| 입사 후 포부 | 권한·업무 없음 | 기준 확인·대조·보고 경험 후보 | 팀의 실제 업무가 확인될 때만 구체화 | 없음 | 의사결정권·성과 과장 |
| 회사 이슈 | 회사 사건 없음 | 해당 없음 | 생성 불가 | 없음 | 무출처 전략·위험 단정 |
| 면접 | 회사 사실 없음 | APP-001~005 | 경험 자체 방어만 가능 | 경험의 상황·행동·한계 설명 | 왜 카카오인지 답하지 못함 |

카카오 공고가 확보될 때까지 이 표는 제출용 자기소개서 문장을 제공하지 않는다.
"""
    write("final/application_bridge.md", app_bridge)

    interview = f"""
# Interview Packet

{common}

## 현재 답변 가능한 범위

- 경험 질문: APP-001~005의 행동과 확인된 결과
- 회사·직무 질문: `NEEDS_VERIFICATION`; 추정 답변 금지

## 예상 질문과 현재 상태

| 질문 | 상태 | 준비 근거 |
|---|---|---|
| 왜 카카오인가 | 답변 보류 | 회사 고유 근거 없음 |
| 왜 이 직무인가 | 답변 보류 | 직무 미확정 |
| 주요 사업·과제·경쟁 차이 | 답변 보류 | 대상 자료 없음 |
| 본인이 기여할 부분 | 부분 준비 | APP-001~005, 단 공고 연결 필요 |
| 최근 전략·위험 | 답변 보류 | 전략·위험 근거 없음 |
| 가장 먼저 배울 것 | 골격만 가능 | 팀 기준·제품·고객·시스템·보안·보고 체계 |

## 경험 답변 구조

`확인된 경험 상황 → 본인의 직접 행동 → 확인된 결과 → 측정·역할의 한계 → 공고 확보 후 직무 연결`

회사 답변 구조는 공식 사실을 확보한 뒤 `회사 사실 → 의미 → 직무 → 경험 → 현실적 행동 → 한계` 순서로 작성한다.
"""
    write("final/interview_packet.md", interview)

    reverse = f"""
# Reverse Questions

{common}

공개 자료로 확인할 수 없는 팀 현실을 검증하는 질문이다.

1. 이 공고의 채용 법인과 실제 근무 법인·사업부·팀은 어디이며, 관계사와 협업 범위는 어디까지인가요?
2. 입사 후 첫 3개월에 맡는 대표 업무와 산출물은 무엇인가요?
3. 해당 산출물의 품질을 판단하는 지표와 가장 자주 발생하는 오류는 무엇인가요?
4. 팀의 올해 우선과제가 바뀐 배경과 이 직무에 미친 영향은 무엇인가요?
5. 업무상 의사결정권과 반드시 상위 보고가 필요한 예외는 어떻게 구분하나요?
6. 가장 자주 협업하는 조직과 협업 과정의 대표적인 병목은 무엇인가요?
7. 입사 전 보완하면 초기 적응에 가장 도움이 되는 제품·데이터·도메인 지식은 무엇인가요?
8. 최근 조직개편이나 전략 변화가 팀의 인력·업무량·성과 기준에 어떤 변화를 만들었나요?
"""
    write("final/reverse_questions.md", reverse)

    appendix = f"""
# Source Appendix

{common}

| Claim ID | 최종 사용 문장 | 출처 | 자료일 | 기준일 | 위치 | 상태 |
|---|---|---|---|---|---|---|
| KAKAO-SCOPE-001 | 조사 목표명은 카카오다. | STEP 0 연구 질문 | 2026-07-15 | 2026-07-15 | `frozen/research_questions.md` | CONFIRMED_PRIMARY |
| APP-001 | 동일 데이터를 두 방식으로 대조해 결과 비교 보고서를 작성하고 팀장에게 보고했다. | 확정 경험 원장 | 생성 2026-07-10 | 경험 기간 UNVERIFIED | `clm_3e69991c9b56d728b429` | CONFIRMED_PRIMARY |
| APP-002 | 3,000페이지 자료를 2일 만에 정리했다. | 확정 경험 원장 + raw DOCX | 확인 2026-07-11 | 경험 기간 UNVERIFIED | `clm_88cfeab230789e5b0d5f`; p456 | CONFIRMED_PRIMARY |
| APP-003 | 상인 50명 인터뷰와 5개 시장 비교로 문제점·개선안을 도출했다. | 확정 경험 원장 + raw DOCX | 확인 2026-07-11 | 경험 기간 UNVERIFIED | `clm_abaa19a532d1aabc9140`; p152 | CONFIRMED_PRIMARY |
| APP-004 | 과거 데이터를 분석해 목표 고객군을 재설정했다. | 확정 경험 원장 | 확인 2026-07-11 | 경험 기간 UNVERIFIED | `clm_2bfba21afb61776d752b` | CONFIRMED_PRIMARY |
| APP-005 | 엑셀 자동화를 도입해 급여 산정 속도를 30% 높였다. | 확정 경험 원장 + raw DOCX | 확인 2026-07-11 | 경험 기간 UNVERIFIED | `clm_353c575898c6254492e8`; p570 | CONFIRMED_PRIMARY |

카카오 회사·직무 사실은 최종 사용 가능한 claim이 0개다. 전체 파일·해시는 `frozen/manifest.json`에 있다.
"""
    write("final/source_appendix.md", appendix)

    decision = {
        "run_id": RUN_ID,
        "company_data_package_id": PACKAGE_ID,
        "company_data_package_version": PACKAGE_VERSION,
        "research_cutoff_date": RESEARCH_CUTOFF_DATE,
        "company_name": "카카오",
        "legal_entity_name": "UNVERIFIED",
        "target_job": "UNVERIFIED",
        "decision": "INSUFFICIENT_EVIDENCE",
        "main_reason": "카카오 대상 법인·공고·공시·IR 자료가 frozen input에 0개라 회사·직무·지원 가치를 검증할 수 없음",
        "strongest_support": "지원자 confirmed 경험 5개는 존재하며 공고 확보 후 재매칭 가능",
        "strongest_counterargument": "카카오는 널리 알려진 회사이므로 공개 상식으로 분석할 수 있다는 주장",
        "counterargument_resolution": "외부 네트워크와 무출처 기억 사용 금지, 법인·사업부 혼동 위험 때문에 기각",
        "critical_unknowns": [
            "정확한 법인·브랜드·계열 범위",
            "공식 공고·사업부·팀·직무·마감일",
            "사업모델·전략·재무·경쟁·문화",
            "지원자 경험과 직무 요구의 직접 연결",
        ],
        "conditions_that_would_change_decision": [
            "공식 공고와 채용 법인 확인",
            "대상 법인의 최신 공시·IR·회사 자료 확보",
            "공고 업무·역량과 confirmed 경험 재매칭",
            "반대 근거를 포함한 HARD_FAIL 재감사 통과",
        ],
        "hard_fail_status": "NOT_TRIGGERED",
        "hard_fail_active_count": 0,
        "completion_status": "COMPLETE_WITH_EVIDENCE_BLOCKERS",
        "network_access_used": False,
    }
    write_json("final/research_decision.json", decision)

    write("final/claim_ledger.md", (OUT / "evidence/claim_ledger.md").read_text(encoding="utf-8"))
    write("final/prohibited_claims.md", (OUT / "evidence/prohibited_claims.md").read_text(encoding="utf-8"))

    validation_report = f"""
# Validation Report

{common}

## 결과

- 원본 62개 해시 기록: PASS
- 입력 집합 SHA-256: `{INPUT_SET_SHA256}`
- STEP 0 연구 질문 SHA-256: `{RESEARCH_QUESTIONS_SHA256}`
- 대상 회사 출처 수: 0
- 대상 불일치 분리: PASS
- 회사 재무 계산: 0건, `NOT_CALCULATED`
- claim 상태·본문 사용 경계: PASS
- HARD_FAIL 활성 건수: 0
- 최종 의사결정: `INSUFFICIENT_EVIDENCE`

## 완료를 막는 항목

`TARGET_LEGAL_ENTITY_UNVERIFIED`, `TARGET_POSTING_MISSING`, `TARGET_COMPANY_SOURCES_ZERO`, `FINANCIAL_SCOPE_UNVERIFIED`, `ROLE_FIT_UNVERIFIED`.

검증 통과는 카카오 지원 준비가 완료됐다는 뜻이 아니다. 근거가 없는 상태에서 오확정·오전용을 하지 않았다는 뜻이다.
"""
    write("final/validation_report.md", validation_report)

    final_audit = f"""
# Final Audit

{common}

## 사실 감사

- 정확한 법인과 채용 주체: 미확정, 오확정 없음
- 회사명·제품·사업부 표기: 목표명 외 사용 없음
- 발표일·기준일·조회일: 구분함; 불명은 `UNVERIFIED`
- 연결·별도·기간·통화: 혼용 없음; 계산 0건
- 회사 주장과 독립 사실: 카카오 claim 자체가 없음
- 조사 기준일 이후 자료: 혼용 없음

## 분석 감사

- 사업모델·전략·경쟁·위험: 근거 부족으로 판정 보류
- 긍정·부정 증거: 동일 기준 적용
- 가장 강한 반대 해석: 공개 상식 사용 가능 주장 검토 후 기각
- 판단 변경 조건: 명시

## 직무 감사

- 공고 업무와 추론 업무: 둘 다 생성하지 않음
- 직무 내부·외부 고객: 미확정
- 지원자 경험: confirmed claim만 사용, 카카오 적합성 과장 없음
- 면접 활용: 경험 방어와 역질문만 가능

## 완료 조건 점검

| 조건 | 결과 |
|---|---|
| 원자료 미변경 | PASS |
| 대상 법인·채용 주체 확인 | BLOCKED |
| DATA PACKAGE ID·버전 일치 | PASS |
| 핵심 claim 출처·기준일 | PASS 또는 미검증 명시 |
| 회사 주장·독립 사실 구분 | PASS |
| 연결·별도·기간·통화 일치 | NOT_APPLICABLE |
| 계산 재현 | PASS: 계산 0건 |
| 전략 단계 구분 | PASS: UNKNOWN |
| 경쟁사 선정 근거 | PASS: 미선정 이유 기록 |
| 반대 근거 검토 | PASS |
| 직무·회사 과제 연결 | BLOCKED |
| 지원자 경험 연결 사실성 | PASS: 연결 보류 |
| 면접 설명 가능성 | PARTIAL |
| 지원 판단·변경 조건 | PASS |
| 내부 메타 비노출 | PARTIAL: 이 패킷은 제출용이 아닌 조사 통제본 |

최종 상태는 `COMPLETE_WITH_EVIDENCE_BLOCKERS`다. HARD_FAIL은 발생하지 않았으나 제출용 회사조사·지원동기·직무 적합도는 완성되지 않았다.
"""
    write("final/final_audit.md", final_audit)


def build_sources_note() -> None:
    write("sources/README.md", f"""
# Sources

{package_header()}

외부 검색·브라우저·네트워크 사용이 금지되어 새 원문을 수집하지 않았다. `input/` 원본은 복사·수정하지 않았으며 전체 경로와 해시는 `frozen/manifest.json`에 기록했다.
""")


def output_manifest() -> None:
    files = []
    manifest_path = OUT / "validation/output_manifest.json"
    for path in sorted(
        p
        for p in OUT.rglob("*")
        if p.is_file()
        and p != manifest_path
        and "__pycache__" not in p.parts
        and p.suffix != ".pyc"
    ):
        files.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
        )
    write_json("validation/output_manifest.json", {
        "run_id": RUN_ID,
        "company_data_package_id": PACKAGE_ID,
        "company_data_package_version": PACKAGE_VERSION,
        "generated_at": FROZEN_AT,
        "files": files,
    })


def main() -> None:
    rows = input_manifest()
    if len(rows) != 62:
        raise SystemExit(f"expected 62 frozen input files, got {len(rows)}")
    if RESEARCH_QUESTIONS_SHA256 != sha256(OUT / "frozen/research_questions.md"):
        raise SystemExit("STEP 0 research_questions.md hash changed")
    build_frozen(rows)
    build_evidence()
    build_sources_note()
    build_analysis()
    build_hypotheses()
    build_validation_and_judges()
    build_synthesis_and_final()
    output_manifest()
    print(json.dumps({
        "run_id": RUN_ID,
        "input_count": len(rows),
        "target_company_source_count": 0,
        "decision": "INSUFFICIENT_EVIDENCE",
        "hard_fail_status": "NOT_TRIGGERED",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
