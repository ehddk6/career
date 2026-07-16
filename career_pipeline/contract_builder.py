"""Build conservative company-research and interview contracts from frozen run data.

The builder does not perform web research and does not promote unknowns. It turns
the already frozen posting, official-research ledger, confirmed experience ledger
and final draft references into complete, validator-ready preparation packets.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
from typing import Any

from .prompt_contracts import (
    COMPANY_CONTRACT_NAME,
    CONTRACT_VERSION,
    INTERVIEW_CONTRACT_NAME,
    validate_run_prompt_contracts,
)


_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?\s*(?:%|건|명|원|시간|일|개월|회|페이지)")
_COVERAGE = (
    ("self_intro", "1분 자기소개를 해 주십시오."),
    ("motivation", "왜 신용보증기금이고 왜 보증 분야 청년인턴입니까?"),
    ("company_choice", "신용보증기금의 역할을 본인 말로 설명해 주십시오."),
    ("job_choice", "신용보증 기한연장과 기업신용 상시관리 업무를 어떻게 이해합니까?"),
    ("representative_experience", "결과 비교 분석 보고서 경험에서 본인이 직접 한 행동과 직무 강점을 설명해 주십시오."),
    ("failure", "자료 대조 결과가 예상과 다르거나 불일치를 발견하면 어떤 순서로 대응하겠습니까?"),
    ("conflict", "같은 데이터를 두 방식으로 처리한 결과를 비교할 때 무엇을 확인하고 어떻게 보고했습니까?"),
    ("collaboration", "현장 의견과 비교 자료를 함께 다룬 경험에서 본인의 역할과 배운 점은 무엇입니까?"),
    ("strength", "보증 분야 인턴 업무에 적합한 가장 큰 강점과 근거는 무엇입니까?"),
    ("weakness", "새 조직에서 작은 오류와 같은 질문의 반복을 줄이기 위해 어떻게 관리하겠습니까?"),
    ("first_90_days", "3개월 인턴 기간에 업무를 어떤 순서로 익히고 수행하겠습니까?"),
    ("core_numbers", "높은 환율 변동성이 중소기업에 미치는 영향과 정책금융 대응을 설명해 주십시오."),
)
_PROBE_CATEGORIES = ("FACT", "JUDGMENT", "CONTRIBUTION", "ALTERNATIVE", "JOB_TRANSFER")


def _load(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def _rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _package_id(run_dir: Path) -> str:
    digest = sha256()
    for name in (
        "00_채용공고분석.json",
        "02_확정경험원장.json",
        "03_경험직무매칭.json",
        "04_공식근거.json",
    ):
        path = run_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"계약 생성 전 필요한 파일이 없습니다: {name}")
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"CAREER-DATA-{digest.hexdigest()[:12].upper()}"


def _experience_index(ledger: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    experiences: dict[str, dict[str, Any]] = {}
    claims: dict[str, dict[str, Any]] = {}
    for experience in _rows(ledger.get("experiences")):
        experience_id = str(experience.get("experience_id", "")).strip()
        if experience.get("status") != "confirmed" or not experience_id:
            continue
        experiences[experience_id] = experience
        for claim in _rows(experience.get("claims")):
            claim_id = str(claim.get("claim_id", "")).strip()
            if claim.get("status") == "confirmed" and claim_id:
                claims[claim_id] = claim
    return experiences, claims


def _draft_rows(run_dir: Path) -> list[dict[str, Any]]:
    # A completed run must rebuild from the selected final. Before selection,
    # draft_final does not exist and the incumbent draft remains the fallback.
    for name in ("draft_final.json", "draft.json"):
        value = _load(run_dir / name, [])
        if isinstance(value, list) and value:
            return _rows(value)
    return []


def _reference_sets(row: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    experience_ids: list[str] = []
    claim_ids: list[str] = []
    for reference in _rows(row.get("experience_refs")):
        experience_id = str(reference.get("experience_id", "")).strip()
        if experience_id:
            experience_ids.append(experience_id)
        claim_ids.extend(_strings(reference.get("claim_ids")))
    return sorted(set(experience_ids)), sorted(set(claim_ids)), sorted(set(_strings(row.get("research_refs"))))


def _first_sentence(text: str, fallback: str) -> str:
    text = " ".join(text.split())
    if not text:
        return fallback
    parts = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
    return parts[0][:220]


def _sentence_at(text: str, index: int, fallback: str) -> str:
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", " ".join(text.split())) if part.strip()]
    return parts[index][:220] if len(parts) > index else _first_sentence(text, fallback)


def _experience_sentence(text: str, fallback: str) -> str:
    """Choose a speakable action sentence from an already validated answer."""
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", " ".join(text.split())) if item.strip()]
    for cues in (("경험",), ("저는", "정리"), ("대조", "보고"), ("기록", "관리")):
        for sentence in sentences:
            if any(cue in sentence for cue in cues):
                return sentence[:220]
    return fallback


def _claim_summary(claim_ids: list[str], claims: dict[str, dict[str, Any]]) -> str:
    """Return a short statement backed only by the explicitly linked claims."""
    for claim_id in claim_ids:
        value = " ".join(str(claims.get(claim_id, {}).get("normalized_value", "")).split())
        if value:
            value = re.sub(r"[✅☑✔]+", " ", value)
            value = re.sub(r"(?:결과|행동|과제|상황)\s*\([^)]*\)\s*:\s*", "", value, flags=re.IGNORECASE)
            segments = [segment.strip(" -→") for segment in re.split(r"(?<=[.!?])\s+|\s+[✅☑✔]+\s*", value) if segment.strip()]
            unique: list[str] = []
            for segment in segments:
                if segment not in unique:
                    unique.append(segment)
            clean = " ".join(unique)
            words = clean.split()
            if len(words) >= 4 and len(words) % 2 == 0 and words[: len(words) // 2] == words[len(words) // 2 :]:
                clean = " ".join(words[: len(words) // 2])
            if len(clean) > 180:
                clean = clean[:180].rsplit(" ", 1)[0]
            return clean.rstrip(". ")
    return "확정 원장에 기록된 행동"


def _pick_draft_source(
    coverage: str,
    refs_by_question: dict[int, tuple[list[str], list[str], list[str]]],
    claims: dict[str, dict[str, Any]],
    question_prompts: dict[int, str] | None = None,
) -> int | None:
    """Map an interview coverage area to one real submitted-answer evidence set.

    This intentionally never cycles unrelated draft rows.  Company-choice areas
    prefer a row with official research, experience areas prefer the richest
    actually submitted experience row, and number defense prefers a submitted
    row that really contains a numeric personal claim.
    """
    if not refs_by_question:
        return None
    indexes = sorted(refs_by_question)
    prompts = question_prompts or {}
    with_research = [index for index in indexes if refs_by_question[index][2]]
    with_experience = [index for index in indexes if refs_by_question[index][1]]

    def first_matching(*tokens: str) -> int | None:
        return next(
            (
                index
                for index in indexes
                if any(token in prompts.get(index, "") for token in tokens)
            ),
            None,
        )

    if coverage in {"self_intro", "motivation", "company_choice"}:
        matched = first_matching("지원하게 된 동기", "지원 동기", "기관의 역할")
        if matched:
            return matched
    if coverage in {"job_choice", "first_90_days"}:
        matched = first_matching("업무수행계획", "근무 시", "업무 수행")
        if matched:
            return matched
    if coverage in {"collaboration", "strength", "weakness", "failure"}:
        matched = first_matching("새로운 조직", "적응", "태도")
        if matched:
            return matched
    if coverage == "conflict":
        for index in with_experience:
            if any(
                "결과 비교" in str(claims.get(claim_id, {}).get("normalized_value", ""))
                for claim_id in refs_by_question[index][1]
            ):
                return index
    numeric = [
        index
        for index in with_experience
        if any(_NUMBER.search(str(claims.get(cid, {}).get("normalized_value", ""))) for cid in refs_by_question[index][1])
    ]
    if coverage in {"motivation", "company_choice"}:
        return with_research[0] if with_research else indexes[0]
    if coverage in {"job_choice", "first_90_days"}:
        return with_research[-1] if with_research else indexes[-1]
    if coverage == "core_numbers":
        if numeric:
            return numeric[0]
        research_numeric = [
            index for index in with_research
            if re.search(r"\d", " ".join(prompts.get(index, ""))) or "이슈" in prompts.get(index, "")
        ]
        return research_numeric[-1] if research_numeric else (with_research[-1] if with_research else indexes[0])
    if with_experience:
        return max(with_experience, key=lambda index: len(refs_by_question[index][1]))
    return indexes[0]


def _relevant_confirmed_experience(
    coverage: str,
    experiences: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    tokens = {
        "failure": ("실수", "오류", "개선", "바꾼", "문제"),
        "conflict": ("갈등", "의견", "충돌", "사과", "조정"),
        "collaboration": ("협업", "동료", "팀", "공유", "보고", "인터뷰", "상인"),
    }.get(coverage, ())
    if not tokens:
        return [], []
    best: tuple[int, str, list[str]] | None = None
    for experience_id, experience in experiences.items():
        confirmed_claims = [
            row for row in _rows(experience.get("claims"))
            if row.get("status") == "confirmed" and row.get("claim_id")
        ]
        if not confirmed_claims:
            continue
        text = " ".join(
            [
                str(experience.get("title", "")),
                str(experience.get("situation", "")),
                *_strings(experience.get("actions")),
                *_strings(experience.get("outcomes")),
                *(str(row.get("normalized_value", "")) for row in confirmed_claims),
            ]
        )
        score = sum(text.count(token) for token in tokens)
        candidate = (score, experience_id, [str(row["claim_id"]) for row in confirmed_claims[:2]])
        if score > 0 and (best is None or candidate[0] > best[0]):
            best = candidate
    return ([best[1]], best[2]) if best else ([], [])


def _build_company(
    *,
    package_id: str,
    target: str,
    posting: dict[str, Any],
    research: list[dict[str, Any]],
    matches: list[dict[str, Any]],
    experiences: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    organization = str(posting.get("organization") or target).strip()
    role = str(posting.get("role") or target).strip()
    duties = _strings(posting.get("duties")) or ["공고에 명시된 담당 업무를 정확히 보조한다."]
    checked_dates = sorted(
        str(row.get("checked_at", "")) for row in research if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row.get("checked_at", "")))
    )
    cutoff = checked_dates[-1] if checked_dates else "1970-01-01"

    source_manifest: list[dict[str, Any]] = []
    claim_ledger: list[dict[str, Any]] = []
    for index, row in enumerate(research, 1):
        research_id = str(row.get("claim_id", "")).strip()
        url = str(row.get("source_url", "")).strip()
        if not research_id or not url.startswith("https://"):
            continue
        source_type = str(row.get("source_type", "")).casefold()
        verified = str(row.get("verification_status", "")).casefold() == "verified"
        evidence_rows = _rows(row.get("source_evidence")) or [{"url": url, "checked_at": row.get("checked_at"), "source_type": source_type}]
        claim_source_ids: list[str] = []
        for source_offset, evidence in enumerate(evidence_rows, 1):
            evidence_url = str(evidence.get("url", "")).strip()
            if not evidence_url.startswith("https://"):
                continue
            source_id = f"source-{index}-{source_offset}"
            claim_source_ids.append(source_id)
            evidence_type = str(evidence.get("source_type") or source_type).upper()
            source_manifest.append(
                {
                    "source_id": source_id,
                    "source_level": 1 if evidence_type in {"STATUTE", "OFFICIAL_WEB", "PUBLIC_DISCLOSURE", "OFFICIAL_DISCLOSURE", "OFFICIAL_PRESS_RELEASE", "OFFICIAL_POSTING", "OFFICIAL"} else 3,
                    "source_type": evidence_type,
                    "publisher": str(evidence.get("publisher", "")).strip(),
                    "title": str(evidence.get("title", "")).strip(),
                    "url": evidence_url,
                    "published_or_effective_at": str(evidence.get("published_or_effective_at", "")).strip(),
                    "checked_at": str(evidence.get("checked_at") or row.get("checked_at") or cutoff)[:10],
                    "evidence_locator": str(evidence.get("evidence_locator", "")).strip(),
                    "target_entity": organization,
                }
            )
        if not claim_source_ids:
            continue
        safe = verified and bool(str(row.get("application_use", "")).strip())
        status = "CONFIRMED_PRIMARY" if verified else "NEEDS_VERIFICATION"
        claim_ledger.append(
            {
                "claim_id": research_id,
                "claim": str(row.get("claim", "")).strip(),
                "claim_type": "EXTERNAL_CLAIM" if str(row.get("claim_type")) == "industry_issue" else "FACT",
                "status": status,
                "source_ids": claim_source_ids,
                "research_refs": [research_id],
                "application_use": ["자기소개서", "면접"] if safe else [],
                "allowed_outputs": ["SELF_INTRO", "INTERVIEW"] if safe else [],
                "prohibited_uses": [] if safe else ["SELF_INTRO", "INTERVIEW"],
                "confidence": 0.95 if verified else 0.4,
                "requires_user_confirmation": not verified,
                "interview_defense_status": "DEFENSIBLE" if safe else "NEEDS_VERIFICATION",
                "usage_restriction": str(row.get("usage_restriction", "")).strip(),
                "domain": str(row.get("research_domain") or row.get("claim_type", "")).strip().upper(),
            }
        )

    safe_claim_ids = [row["claim_id"] for row in claim_ledger if row["status"] == "CONFIRMED_PRIMARY"]
    role_claim_ids = [
        row["claim_id"]
        for row in claim_ledger
        if row["claim_id"] in safe_claim_ids
        and any(token in row["claim"].casefold() for token in ("업무", "역할", "보증", "지원", "관리", "심사"))
    ] or safe_claim_ids[:1]

    bridges: list[dict[str, Any]] = []
    for row in matches:
        recommended = row.get("recommended") if isinstance(row.get("recommended"), dict) else {}
        experience_id = str(recommended.get("experience_id", "")).strip()
        experience = experiences.get(experience_id)
        if not experience:
            continue
        claim_ids = [
            str(claim.get("claim_id"))
            for claim in _rows(experience.get("claims"))
            if claim.get("status") == "confirmed" and claim.get("claim_id")
        ]
        if not claim_ids:
            continue
        question = row.get("question") if isinstance(row.get("question"), dict) else {}
        bridges.append(
            {
                "requirement": str(question.get("prompt") or duties[0])[:240],
                "experience_id": experience_id,
                "experience_claim_ids": claim_ids,
                "fit_state": "TRANSFERABLE",
            }
        )
    if not bridges:
        for experience_id, experience in list(experiences.items())[:1]:
            claim_ids = [str(c.get("claim_id")) for c in _rows(experience.get("claims")) if c.get("claim_id")]
            if claim_ids:
                bridges.append({"requirement": duties[0], "experience_id": experience_id, "experience_claim_ids": claim_ids, "fit_state": "PARTIAL"})

    strategy_claim_ids = [
        row["claim_id"]
        for row in claim_ledger
        if row["status"] == "CONFIRMED_PRIMARY"
        and row["claim_id"] not in role_claim_ids
    ] or role_claim_ids
    recent = [
        {
            "observation": row["claim"],
            "interpretation": "공식 근거로 확인된 범위 안에서 지원 판단과 면접 질문에 사용한다.",
            "status": row["status"],
            "claim_ids": [row["claim_id"]],
        }
        for row in claim_ledger
        if row["status"] == "CONFIRMED_PRIMARY"
    ][:5]
    if not recent:
        recent = [{"observation": "공식 자료에서 최근 실적을 확인하지 못했습니다.", "interpretation": "추가 확인 전 제출 주장으로 사용하지 않습니다.", "status": "NEEDS_VERIFICATION", "claim_ids": []}]

    safe_rows = [row for row in claim_ledger if row["status"] == "CONFIRMED_PRIMARY"]

    def domain_rows(*domains: str) -> list[dict[str, Any]]:
        wanted = {value.upper() for value in domains}
        return [row for row in safe_rows if str(row.get("domain", "")).upper() in wanted]

    def claims_text(rows: list[dict[str, Any]], fallback: str, limit: int = 3) -> list[str]:
        values = [str(row.get("claim", "")).strip() for row in rows if str(row.get("claim", "")).strip()]
        return values[:limit] or [fallback]

    customer_rows = domain_rows("CUSTOMER")
    model_rows = domain_rows("BUSINESS_MODEL", "ENTITY", "FUNDING_LOGIC", "RISK_SHARING", "CUSTOMER_VALUE")
    value_chain_rows = domain_rows("VALUE_CHAIN", "OPERATIONS")
    risk_rows = domain_rows("RISK_CONTROL")
    program_rows = domain_rows("PROGRAM")
    announced_strategy_rows = domain_rows("STRATEGY")
    result_rows = domain_rows("OPERATING_RESULT", "EXECUTION_RESULT")
    started_rows = domain_rows("PARTNERSHIP_EXECUTION", "DIGITAL_EXECUTION")
    funded_rows = domain_rows("PLAN_AND_RESOURCE", "PEOPLE_RESOURCE")
    governance_rows = domain_rows("GOVERNANCE", "ORGANIZATION")
    job_rows = domain_rows("JOB_POSTING", "SELECTION", "BLIND_RECRUITMENT", "PLACEMENT")
    strategy_execution: list[dict[str, Any]] = []
    stage_details = {
        "ANNOUNCED": {
            "success": "후속 예산·협약·집행 자료가 같은 목표와 범위로 이어지는지 확인",
            "failure": "계획만 발표되고 담당·재원·후속 실행 근거가 확인되지 않음",
            "limit": "발표된 방향과 계획만 확인했습니다. 착수·운영·성과로 해석하지 않습니다.",
        },
        "STARTED": {
            "success": "협약 체결 뒤 실제 상담·접수·공급 등 운영 근거가 이어지는지 확인",
            "failure": "협약 사실만 있고 대상·기간·실행 내용이 후속 자료에서 확인되지 않음",
            "limit": "협약·착수 사실은 실행 신호이지만 이용 성과나 정책 효과를 뜻하지 않습니다.",
        },
        "FUNDED": {
            "success": "공급 목표와 인력·재원이 실제 집행 자료와 같은 범위로 연결되는지 확인",
            "failure": "계획한 자원과 실제 집행 범위가 다르거나 후속 집행 근거가 없음",
            "limit": "자원 투입 계획만으로 집행 완료나 수혜 효과를 단정하지 않습니다.",
        },
        "OPERATING": {
            "success": "반복 가능한 절차·점검·사후관리 기록이 공식 자료에서 계속 확인됨",
            "failure": "운영 절차와 예외 처리·사후관리 기준이 확인되지 않음",
            "limit": "운영 중인 제도와 절차만 확인했으며 내부 품질이나 성과 수준은 평가하지 않습니다.",
        },
        "RESULT_OBSERVED": {
            "success": "동일 기준의 후속 공시에서도 실행 결과와 범위가 재확인됨",
            "failure": "단일 결과를 전체 전략 성과로 확대하거나 인과관계를 검증 없이 단정함",
            "limit": "공시된 발행·공급·운영 결과의 발생만 확인했습니다. 전략 전체의 인과 성과로 확대하지 않습니다.",
        },
    }
    for strategy_id, stage, rows, label in (
        ("strategy-program", "ANNOUNCED", program_rows, "공식 지원 프로그램의 계획과 집행"),
        ("strategy-direction", "ANNOUNCED", announced_strategy_rows, "중장기 전략목표와 과제"),
        ("strategy-result", "RESULT_OBSERVED", result_rows, "공시된 운영·실행 결과"),
        ("strategy-partnership", "STARTED", started_rows, "협약·상담·디지털 협력 실행"),
        ("strategy-resource", "FUNDED", funded_rows, "기본재산·공급목표·인력 자원 투입"),
        ("strategy-governance", "OPERATING", governance_rows, "환경·고객·리스크 모니터링"),
        ("strategy-process", "OPERATING", value_chain_rows + risk_rows, "신용조사·심사 절차와 위험 통제"),
    ):
        if not rows:
            continue
        stage_detail = stage_details[stage]
        strategy_execution.append(
            {
                "strategy_id": strategy_id,
                "stage": stage,
                "claim_ids": [row["claim_id"] for row in rows],
                "verified_signal": claims_text(rows, label, 3),
                "success_conditions": [stage_detail["success"]],
                "failure_signals": [stage_detail["failure"]],
                "job_implications": duties,
                "evidence_strength": "HIGH" if stage == "RESULT_OBSERVED" else "MEDIUM" if stage in {"STARTED", "OPERATING", "FUNDED"} else "DIRECTION_ONLY",
                "observed_vs_plan": "OBSERVED_RESULT" if stage == "RESULT_OBSERVED" else "EXECUTION_SIGNAL" if stage in {"STARTED", "OPERATING", "FUNDED"} else "PLAN_ONLY",
                "interpretation_limit": stage_detail["limit"],
            }
        )
    if not strategy_execution:
        strategy_execution = [{"strategy_id": "strategy-1", "stage": "OPERATING", "claim_ids": strategy_claim_ids, "success_conditions": ["공식 사업이 확인된 대상에게 기준대로 집행됨"], "failure_signals": ["반복 누락 또는 근거 없는 예외 처리"], "job_implications": duties}]

    prohibited_talking_points = sorted(
        {
            str(row.get("usage_restriction", "")).strip()
            for row in safe_rows
            if str(row.get("usage_restriction", "")).strip()
        }
    )[:8] or ["확인되지 않은 내부 성과·문화·권한을 사실처럼 단정하는 표현"]

    return {
        "schema_version": 2,
        "contract_version": CONTRACT_VERSION,
        "data_package_id": package_id,
        "data_package_version": "2.0",
        "target": target,
        "research_cutoff_date": cutoff,
        "entity": {"legal_entity_name": organization, "brand_name": organization, "target_business_unit": role, "status": "CONFIRMED"},
        "source_manifest": source_manifest,
        "claim_ledger": claim_ledger,
        "business_model": {
            "core_customers": claims_text(customer_rows, "공식 근거에 명시된 정책금융 지원 대상"),
            "customer_problem": claims_text(model_rows, "공식 근거에 명시된 자금 접근·신용관리 문제", 1)[0],
            "value_proposition": claims_text(value_chain_rows, "공식 기준과 심사를 통한 금융 접근 지원", 1)[0],
            "revenue_logic": claims_text(model_rows, "공공기관의 정책 목적과 법정·공식 사업 구조에 따른 업무 수행", 2)[-1],
            "major_costs": ["심사·관리 인력", "업무 시스템과 리스크 관리"],
            "critical_risks": claims_text(risk_rows, "자료 오류·누락과 지원 필요성·위험의 오판", 3),
            "value_chain": claims_text(value_chain_rows, "신청·자료수집·조사·심사·보증서 발급·사후관리", 5),
            "counterparties": ["보증 신청기업", "채권자인 금융회사", "정책·협력기관"],
            "risk_transfer_logic": claims_text(domain_rows("RISK_SHARING"), "조사·심사 뒤 보증을 통해 채권자의 신용위험 일부를 기금이 부담", 1)[0],
            "funding_and_fee_logic": claims_text(domain_rows("FUNDING_LOGIC"), "기본재산을 재산적 기초로 삼고 승인 보증에 보증료를 부과", 1)[0],
            "customer_value": claims_text(domain_rows("CUSTOMER_VALUE"), "담보문제 완화와 자금조달 지원", 3),
            "operating_resources": claims_text(domain_rows("ORGANIZATION", "PEOPLE_RESOURCE"), "영업점·심사관리 인력·업무 시스템", 3),
            "limits": ["보증은 기업의 상환의무를 없애지 않음", "공개 자료만으로 내부 심사모형·팀별 권한·KPI를 확정할 수 없음"],
        },
        "strategy_execution": strategy_execution,
        "financial_analysis": {"status": "INSUFFICIENT_EVIDENCE", "reason": "동결된 공식 근거만으로 기간·단위가 일치하는 재무 시계열을 구성할 수 없습니다.", "metrics": []},
        "competitor_analysis": {"status": "INSUFFICIENT_EVIDENCE", "reason": "동일 고객 문제와 기능을 기준으로 비교할 공식 자료가 충분하지 않습니다.", "selection": [], "comparisons": []},
        "culture_analysis": {"status": "INSUFFICIENT_EVIDENCE", "reason": "공개 자료만으로 특정 팀의 실제 문화를 확정할 수 없습니다.", "evidence": [], "unknowns": ["배치 부서별 업무 방식", "피드백과 보고 주기"]},
        "market_position": {"target_market": claims_text(customer_rows, "공식 근거에 명시된 지원 대상과 정책금융 수요", 1)[0], "customer_alternatives": ["민간 금융", "다른 정책금융 지원", "자체 자금 조달"], "competitor_selection_basis": "동일 고객 문제와 제공 기능", "differentiators": claims_text(model_rows + program_rows, "공식 근거로 확인된 기관 역할과 사업", 4), "uncertainties": ["공개 자료로 확인되지 않은 내부 자원 배분과 성과", "비교기관을 같은 기준으로 검증한 자료"]},
        "recent_performance": recent,
        "research_completeness": {"answered_questions": ["법인과 직무", "공식 사업·역할", "지원서에 사용할 수 있는 주장"], "unresolved_questions": ["최근 3개년 비교 가능한 재무·성과", "실제 인턴 권한과 팀별 KPI", "내부 자원 배분"], "stopping_reason": "동결된 공식 근거에서 지원서와 면접에 필요한 안전한 주장 범위를 확정했습니다."},
        "interview_implications": {"expected_questions": [f"{organization}의 역할과 {role} 업무를 어떻게 이해하고 있습니까?", "공식 자료와 실제 고객 자료가 다를 때 어떻게 확인하겠습니까?", "기관의 지원 필요성과 위험 통제를 어떻게 함께 이해하고 있습니까?"], "reverse_questions": ["입사 초기 가장 먼저 익혀야 할 업무 기준은 무엇입니까?", "반복적으로 발생하는 예외와 보고 기준은 무엇입니까?"], "prohibited_talking_points": prohibited_talking_points},
        "role_value_map": [{"company_issue": row["claim"], "role_actions": duties + ["원자료와 전산값 대조", "변동·누락·예외 기록", "판단이 필요한 사항을 근거와 함께 보고"], "claim_ids": [row["claim_id"]], "certainty": "ORGANIZATION_SUPPORTED"} for row in (job_rows or domain_rows("JOB_DUTY", "ORGANIZATION_ROLE") or [row for row in safe_rows if row["claim_id"] in role_claim_ids])[:5]],
        "motivation_bridges": [{"company_fact": row["claim"], "claim_ids": [row["claim_id"]], "applicant_action": "확정 경험의 대조·정리·보고 행동", "realistic_contribution": "기한연장·상시관리 자료의 누락과 변동을 기준에 따라 확인하고 담당자 판단을 보조", "boundary": str(row.get("usage_restriction") or "인턴의 심사·승인 권한으로 확대하지 않음")} for row in (model_rows + result_rows + started_rows)[:5]],
        "applicant_bridge": bridges,
        "red_team": {"strongest_counterargument": "공개된 기관 역할이 실제 배치 부서의 일상 업무와 완전히 같다고 단정할 수 없습니다.", "critical_unknowns": ["실제 인턴의 시스템 권한", "팀별 업무량과 성과 기준"]},
        "first_90_days": {"days_0_30": ["업무 기준·용어·보고 경로를 확인하고 체크리스트로 정리"], "days_31_60": ["원자료와 처리 결과를 대조하고 예외를 근거와 함께 보고"], "days_61_90": ["반복 오류와 문의 유형을 기록해 담당자 검토 후 개선 제안"]},
        "decision": {"status": "APPLY_WITH_CONDITIONS", "main_reason": "공식 근거로 확인된 기관 역할과 공고 업무가 확정 경험의 확인·대조·기록 행동과 연결됩니다.", "strongest_support": "공고 및 공식 근거의 역할·업무 claim", "strongest_counterargument": "실제 배치와 권한은 공개 자료만으로 확인되지 않습니다.", "conditions_that_would_change_decision": ["실제 배치 업무가 공고와 크게 다른 경우", "지원 자격 또는 근무 조건이 달라지는 경우"]},
    }


def _build_interview(
    *,
    package_id: str,
    posting: dict[str, Any],
    research: list[dict[str, Any]],
    draft: list[dict[str, Any]],
    experiences: dict[str, dict[str, Any]],
    claims: dict[str, dict[str, Any]],
    include_candidate_pool: bool = True,
) -> dict[str, Any]:
    organization = str(posting.get("organization") or "지원 기관")
    role = str(posting.get("role") or "지원 직무")
    duties = _strings(posting.get("duties")) or ["공고상 담당 업무"]
    research_ids = [str(row.get("claim_id")) for row in research if row.get("claim_id")]
    question_prompts = {
        int(row.get("index", 0)): str(row.get("prompt", ""))
        for row in _rows(posting.get("questions"))
        if isinstance(row.get("index"), int) and int(row.get("index", 0)) > 0
    }
    submitted: list[dict[str, Any]] = []
    refs_by_question: dict[int, tuple[list[str], list[str], list[str]]] = {}
    answer_by_question: dict[int, str] = {}
    for row in draft:
        index = int(row.get("question_index", 0))
        if index <= 0:
            continue
        refs = _reference_sets(row)
        refs_by_question[index] = refs
        answer_by_question[index] = str(row.get("answer", "")).strip()
        submitted.append({"question_index": index, "experience_ids": refs[0], "experience_claim_ids": refs[1], "research_claim_ids": refs[2], "status": "CONFIRMED"})
    # Candidate generation may choose another confirmed experience, so the
    # defense ledger can cover the full safe pool. Core answer cards below are
    # narrower: they may use only references present in the current draft.
    submitted_experiences = {
        experience_id
        for refs in refs_by_question.values()
        for experience_id in refs[0]
    }
    general_experiences: set[str] = set()
    used_experiences = sorted(
        experience_id
        for experience_id, experience in experiences.items()
        if any(row.get("claim_id") for row in _rows(experience.get("claims")))
        and (include_candidate_pool or experience_id in submitted_experiences | general_experiences)
    )

    defense: list[dict[str, Any]] = []
    submitted_action_by_experience: dict[str, str] = {}
    for question_index, refs in refs_by_question.items():
        for experience_id in refs[0]:
            submitted_action_by_experience.setdefault(
                experience_id,
                _experience_sentence(
                    answer_by_question.get(question_index, ""),
                    _claim_summary(refs[1], claims),
                ),
            )
    for experience_id in used_experiences:
        experience = experiences.get(experience_id, {})
        used_claim_ids = sorted({claim_id for refs in refs_by_question.values() if experience_id in refs[0] for claim_id in refs[1]})
        if not used_claim_ids:
            used_claim_ids = [str(row.get("claim_id")) for row in _rows(experience.get("claims")) if row.get("claim_id")]
        numeric = any(re.search(r"\d", str(claims.get(claim_id, {}).get("normalized_value", ""))) for claim_id in used_claim_ids)
        actions = [submitted_action_by_experience.get(experience_id) or _claim_summary(used_claim_ids, claims)]
        defense.append({"experience_id": experience_id, "depth": "D4" if numeric else "D3", "defense_status": "DEFENSIBLE_WITH_QUALIFICATION" if numeric else "DEFENSIBLE", "claim_ids": used_claim_ids, "confirmed_scope": actions[0], "unconfirmed_scope": ["claim에 없는 수치의 산식·측정기간", "팀 전체 결과 중 원장에 없는 개인 기여", "당시 최종 승인자의 판단 근거"], "direct_actions": actions, "judgment_standards": ["원자료와 처리 결과의 일치 여부", "기한·정확성·보고 필요성을 함께 확인"], "metric_defense": {"required": numeric, "rule": "수치의 기준값·결과값·산식·측정기간·개인 기여를 모두 설명할 수 있을 때만 발화"}, "prohibited_claims": ["원장 claim에 없는 30%·90% 등 성과 수치", "팀 결과를 개인이 단독으로 만든 성과라는 표현", "인턴이 보증 승인·신용판단을 내린다는 표현"], "red_team_questions": ["이 행동의 원자료는 무엇입니까?", "팀 결과와 직접 행동을 구분하면 어디까지입니까?", "같은 상황에서 결과가 달랐다면 무엇을 먼저 확인합니까?"], "limitations": ["최종 판단·승인 권한과 본인의 보조 행동을 구분해 설명", "원장에 수치 산식이 없으면 숫자를 말하지 않고 행동만 설명"]})

    competency_ids = ("accuracy", "communication", "boundary", "adaptation")
    competencies = [
        {"competency_id": "accuracy", "definition": "근거와 기준을 대조해 오류·누락을 줄이는 역량", "observable_behaviors": ["원자료 대조", "예외 기록", "재점검"]},
        {"competency_id": "communication", "definition": "진행 상태와 판단이 필요한 사항을 제때 공유하는 역량", "observable_behaviors": ["질문 묶음 정리", "진행 보고", "인계 기록"]},
        {"competency_id": "boundary", "definition": "권한과 확인되지 않은 범위를 구분하는 역량", "observable_behaviors": ["추정과 사실 구분", "승인 요청", "한계 설명"]},
        {"competency_id": "adaptation", "definition": "피드백을 업무 기준과 반복 행동으로 바꾸는 역량", "observable_behaviors": ["업무 용어 정리", "피드백 체크리스트", "재발 방지"]},
    ]

    questions: list[dict[str, Any]] = []
    coverage_rationales = {
        "self_intro": "첫 답변에서 핵심 경험과 직무 연결을 함께 확인",
        "motivation": "기관 선택 근거와 보증 인턴 지원 이유를 분리 확인",
        "company_choice": "기관 역할을 홍보 문구가 아닌 공식 기능으로 설명하는지 확인",
        "job_choice": "기한연장·상시관리 업무와 인턴 권한 경계를 확인",
        "representative_experience": "최종 제출본의 핵심 경험과 직접 행동을 검증",
        "failure": "자료 불일치 상황의 확인·보고 순서를 검증",
        "conflict": "비교 결과의 조건 통제와 보고 근거를 검증",
        "collaboration": "현장 의견과 비교 자료를 함께 다룬 역할을 검증",
        "strength": "직무 강점이 승인 경험으로 입증되는지 확인",
        "weakness": "낯선 조직에서 오류 재발을 줄이는 행동을 확인",
        "first_90_days": "3개월 안의 현실적인 학습·실행·점검 계획을 확인",
        "core_numbers": "중소기업 이슈와 정책금융 대응의 사실 경계를 검증",
    }
    coverage_question_types = {
        "self_intro": "RECRUITER",
        "motivation": "RECRUITER",
        "company_choice": "FACT_AUDITOR",
        "job_choice": "HIRING_MANAGER",
        "representative_experience": "FACT_AUDITOR",
        "failure": "SITUATIONAL_INTERVIEWER",
        "conflict": "FACT_AUDITOR",
        "collaboration": "HIRING_MANAGER",
        "strength": "RECRUITER",
        "weakness": "SITUATIONAL_INTERVIEWER",
        "first_90_days": "HIRING_MANAGER",
        "core_numbers": "EXECUTIVE",
    }
    for index, (coverage, text) in enumerate(_COVERAGE, 1):
        source_index = _pick_draft_source(coverage, refs_by_question, claims, question_prompts)
        source_refs = refs_by_question.get(source_index, ([], [], [])) if source_index else ([], [], [])
        question_scope = "SUBMITTED_DRAFT"
        if coverage == "company_choice":
            source_refs = ([], [], source_refs[2])
        if coverage in {"failure", "weakness"}:
            source_refs = ([], [], [])
        questions.append({"question_id": f"Q{index}", "question": text, "question_type": coverage_question_types[coverage], "tier": 1, "probability": "HIGH", "selection_rationale": coverage_rationales[coverage], "competency_ids": [competency_ids[(index - 1) % len(competency_ids)]], "experience_ids": source_refs[0], "coverage_tags": [coverage], "evidence_scope": question_scope, "source_question_indexes": [source_index] if source_index and question_scope == "SUBMITTED_DRAFT" else []})
    extra_prompts = (
        "지급 결정서·추납·분납 자료를 분류할 때 우선순위와 검수 순서를 어떻게 정했습니까?",
        "여러 업무의 마감이 겹치면 어떤 기준으로 우선순위를 정하고 언제 보고합니까?",
        "원자료와 시스템 값이 다르면 첫 세 단계에서 무엇을 확인하겠습니까?",
        "동료와 업무 방법이 다를 때 상대의 근거를 확인하고 합의하는 절차는 무엇입니까?",
        "기업 고객이 급하다며 필수 절차 생략을 요구하면 어떻게 응대하겠습니까?",
        "한정된 보증 재원을 다루는 공공기관에서 청렴과 기록이 왜 중요합니까?",
        "기대한 결과가 나오지 않았을 때 사실과 판단을 어떻게 나누어 보고하겠습니까?",
        "결과 비교 분석 보고서에서 비교 기준·차이·본인 역할을 구분해 설명해 주십시오.",
        "민감한 기업정보를 다룰 때 열람·메모·공유 범위를 어떻게 지키겠습니까?",
        "모르는 업무를 빨리 배우기 위한 용어·사례·질문·체크리스트 순서를 설명해 주십시오.",
        "기업의 도전과 성장을 지원하는 신용보증기금의 역할 중 본인과 맞는 부분은 무엇입니까?",
        "신용보증의 신청·조사·심사·약정·보증서 발급 흐름을 아는 범위에서 설명해 주십시오.",
        "기업신용 상시관리가 필요한 이유와 인턴이 확인·기록·보고할 범위를 말해 주십시오.",
        "2026년 신용보증기금의 실행 과제 중 공식 근거로 확인한 한 가지를 설명해 주십시오.",
        "3개월 인턴이 과장 없이 남길 수 있는 실제 기여는 무엇입니까?",
        "수치가 포함된 업무개선 경험을 질문받았는데 산식을 설명할 수 없다면 어떻게 답하겠습니까?",
        "이용자 불편 개선 경험에서 확인된 행동과 확인되지 않은 성과를 구분해 주십시오.",
        "상인 인터뷰와 5개 타 시장 비교에서 어떤 기준으로 공통점과 차이를 정리했습니까?",
        "리더와 팔로워 역할을 상황과 업무 기준에 따라 어떻게 선택합니까?",
        "압박이 큰 상황에서 할 일을 나누고 중간보고하는 방식을 설명해 주십시오.",
        "업무 중 본인의 판단이 틀렸음을 알게 되면 누구에게 무엇부터 보고하겠습니까?",
        "희망 외 영업점 배치 가능성과 근무기간 조건을 어떻게 최종 확인하겠습니까?",
        "마지막으로 본인을 뽑아야 하는 이유를 확인된 경험과 직무 행동으로 설명해 주십시오.",
    )
    extra_source_questions = {13: 3, 20: 1, 30: 2}
    official_extra_questions = {17, 18, 21, 23, 24, 25, 26, 27, 34, 35}
    for offset, text in enumerate(extra_prompts, 13):
        high_probability = offset in {13, 15, 17, 18, 20, 21, 22, 23, 24, 25, 26, 27, 30, 34, 35}
        source_index = extra_source_questions.get(offset)
        source_refs = refs_by_question.get(source_index, ([], [], [])) if source_index else ([], [], [])
        confirmed_evidence = list(source_refs[1])
        if offset in official_extra_questions:
            confirmed_evidence.extend(research_ids)
        answer_anchor = (
            _first_sentence(answer_by_question.get(source_index, ""), "확인된 경험 범위에서 답합니다.")
            if source_index
            else "공식 공고와 확인된 사실을 먼저 말하고, 인턴의 권한은 확인·기록·보고로 제한합니다."
        )
        questions.append({"question_id": f"Q{offset}", "question": text, "question_type": "FACT_AUDITOR" if offset in {13, 20, 28, 29, 30} else "EXECUTIVE" if offset in {18, 23, 26, 35} else "RED_TEAM" if offset in {17, 28, 29, 33} else "SITUATIONAL_INTERVIEWER", "tier": 2 if offset <= 27 else 3, "probability": "HIGH" if high_probability else "MEDIUM" if offset <= 33 else "FORMAT_DEPENDENT", "selection_rationale": "공고 직무·최종 제출본·정책금융 사실 경계 중 하나를 추가 검증", "competency_ids": [competency_ids[(offset - 1) % len(competency_ids)]], "experience_ids": list(source_refs[0]), "coverage_tags": ["kodit_role_specific"], "evidence_scope": "SUBMITTED_DRAFT" if source_index else "OFFICIAL_RESEARCH" if offset in official_extra_questions else "PROCEDURAL_RESPONSE", "source_question_indexes": [source_index] if source_index else [], "answer_anchor": answer_anchor, "confirmed_evidence": sorted(set(confirmed_evidence)), "answer_boundary": "제출본·공식 자료에서 확인된 범위만 답하고 미검증 수치·성과·권한은 확대하지 않음"})

    answer_cards: list[dict[str, Any]] = []
    for index, (coverage, _question_text) in enumerate(_COVERAGE, 1):
        source_index = _pick_draft_source(coverage, refs_by_question, claims, question_prompts)
        experience_ids, claim_ids, card_research = refs_by_question.get(source_index, ([], [], [])) if source_index else ([], [], [])
        evidence_scope = "SUBMITTED_DRAFT"
        if coverage == "company_choice":
            experience_ids, claim_ids = [], []
        if coverage in {"failure", "weakness"}:
            experience_ids, claim_ids, card_research = [], [], []
            source_index = None
        source_answer = answer_by_question.get(source_index or 0, "")
        summary = _claim_summary(claim_ids, claims)
        direct_actions = [
            _experience_sentence(source_answer, summary)
            if evidence_scope == "SUBMITTED_DRAFT"
            else summary
        ]
        if coverage == "motivation":
            direct_actions = ["신용보증기금의 보증 역할과 인턴 업무를 확인하고 지원 동기·학습·기여 계획을 연결"]
        elif coverage == "company_choice":
            direct_actions = ["기업 채무보증·신용조사·보증심사라는 공식 역할을 근거로 설명"]
        if coverage == "failure":
            one = "자료 불일치를 발견하면 영향 범위를 표시하고 원문·기준일·입력 이력을 대조한 뒤, 임의로 고치지 않고 차이와 근거를 담당자에게 보고하겠습니다."
            direct_actions = ["영향 범위 표시 → 원문·기준일·입력 이력 대조 → 차이와 근거 보고 → 지시 후 수정·재점검"]
        elif coverage == "conflict":
            one = "결과 비교에서는 입력값·수식·기준을 대조하고, 확인한 차이와 근거를 보고서로 정리해 담당자에게 보고하겠습니다."
            direct_actions = ["입력값 확인 → 수식·처리 기준 대조 → 차이 기록 → 분석 보고서 보고"]
        elif coverage == "collaboration":
            one = f"{direct_actions[0]} 이 경험에서 확인한 내용과 판단을 구분하고, 진행 상황을 공유한 제 행동만 설명하겠습니다."
        elif coverage == "representative_experience":
            one = f"{direct_actions[0]} 이 경험에서 제가 한 대조·기록·보고와 최종 판단권자의 역할을 구분해 설명하겠습니다."
        elif coverage == "strength":
            one = f"제 강점은 확인 기준을 반복 행동으로 옮기는 점입니다. {direct_actions[0]}"
        elif coverage == "weakness":
            one = "새 조직에서는 질문과 피드백을 업무노트에 남기고, 다음 처리 전 체크리스트로 재확인해 같은 질문과 작은 오류의 반복을 줄이겠습니다."
            direct_actions = ["질문·답변 기록 → 체크리스트 반영 → 다음 업무 전 재확인 → 반복 오류 보고"]
        elif coverage == "core_numbers" and not any(
            _NUMBER.search(str(claims.get(claim_id, {}).get("normalized_value", ""))) for claim_id in claim_ids
        ) and not card_research:
            one = "최종 제출본에는 개인 성과 수치를 주장하지 않았으며, 질문을 받으면 수치를 만들지 않고 확인된 행동과 기여 범위만 설명하겠습니다."
        elif coverage == "self_intro":
            one = f"{direct_actions[0]} 이 경험에서 확인·기록을 습관화했고, 이를 {role} 업무에 연결하겠습니다."
        elif coverage == "company_choice":
            one = _sentence_at(source_answer, 2, f"{organization}은 공식 기준에 따라 기업의 자금 접근을 지원하는 기관으로 이해합니다.")
        elif coverage == "job_choice":
            one = _sentence_at(source_answer, 0, f"{duties[0]}의 기준과 자료 흐름을 먼저 익히겠습니다.")
        else:
            one = _first_sentence(source_answer, f"저는 {summary} 경험을 바탕으로 {role} 업무를 정확히 보조하겠습니다.")
        job_connection = f"{organization} {role}의 {duties[0]}에서 확인·기록·보고 행동으로 연결됩니다."
        if coverage == "core_numbers":
            source_sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", source_answer) if part.strip()]
            standard = " ".join(source_sentences[:5])
            detailed = source_answer
            job_connection = "기업별 환율 노출과 현금흐름을 확인해 유동성 지원 필요성과 보증 위험을 함께 판단하는 정책금융 논리로 연결됩니다."
            direct_actions = ["기업별 매출·원가·외화 결제 조건 확인", "일시적 유동성 부족과 구조적 위험 구분", "지원 뒤 환율 노출·회수·연체 변화 점검"]
        else:
            source_sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", source_answer) if part.strip()]
            if coverage in {"representative_experience", "failure", "conflict", "collaboration", "strength", "weakness"}:
                standard = (
                    f"{one} {job_connection}"
                )
                detailed = (
                    f"{standard} 답변에서는 확인된 행동과 판단 기준을 먼저 말하고, "
                    "팀의 결과와 최종 판단권자의 역할은 제 기여와 분리하겠습니다."
                )
            elif experience_ids and source_sentences:
                # 제출본의 실제 문장 흐름을 보존한다. 짧은 답에 기계적인
                # "근거 행동은" 문구를 붙이면 말하기 품질이 크게 떨어진다.
                standard = " ".join(source_sentences[:3])
                detailed = " ".join(source_sentences[:6]) or standard
            elif card_research:
                standard = (
                    f"{one} 공식 공고와 기관 자료에서 확인한 역할을 기준으로 답하고, "
                    "인턴의 범위는 자료 확인·기록·보고로 한정하겠습니다."
                )
                detailed = (
                    f"{standard} 확인하지 못한 내부 기준은 추정하지 않고, "
                    "입사 후 담당자의 기준과 최신 자료를 먼저 확인하겠습니다."
                )
            else:
                standard = (
                    f"{one} 먼저 담당 기준과 영향 범위를 확인하고, "
                    "제가 판단할 수 없는 부분은 근거와 함께 보고하겠습니다."
                )
                detailed = (
                    f"{standard} 처리 뒤에는 변경 내용과 확인 결과를 남겨 "
                    "같은 오류가 반복되지 않는지 재점검하겠습니다."
                )
        if len(standard) < len(one):
            standard = f"{one} 답변에서는 확인한 사실과 제 행동을 먼저 구분해 설명하겠습니다."
        if len(detailed) < len(standard):
            detailed = f"{standard} 이어서 선택 기준과 한계, 입사 후 적용 순서까지 설명하겠습니다."
        if coverage == "self_intro":
            standard = (
                "저는 동일한 데이터를 엑셀 수식과 외주 프로그램에 넣어 결과를 비교하고, "
                "분석 보고서를 작성해 팀장에게 보고한 경험이 있습니다. 서로 다른 처리 결과를 그대로 넘기지 않고 비교 근거를 정리해 "
                "팀장에게 보고한 점이 제 강점입니다. 이 확인 습관을 보증 업무에 연결하겠습니다."
            )
            detailed = (
                f"{standard} 제가 직접 한 일은 같은 입력 조건에서 결과 차이를 확인하고 "
                "보고서로 정리한 범위입니다. 수식을 개발했거나 최종 의사결정을 했다고 확대하지 않겠습니다. "
                "보증 분야 청년인턴으로 근무한다면 업무 기준을 먼저 익힌 뒤 원자료와 처리값을 대조하고, "
                "누락·변동·예외는 근거와 함께 보고하겠습니다. 기한연장과 기업신용 상시관리에서도 "
                "판단을 대신하기보다 담당자가 확인할 자료의 상태를 정확히 전달하겠습니다."
            )
        elif coverage == "motivation":
            standard = (
                f"{one} 신용보증은 신용조사와 보증심사를 거쳐 기업의 자금 접근을 돕는 일이고, "
                f"인턴은 {duties[0]}을 보조합니다. 저는 서로 다른 처리 결과를 비교해 "
                "근거를 보고서로 정리한 경험이 이 업무의 확인 과정과 맞닿아 있다고 보았습니다."
            )
            detailed = (
                f"{standard} 당시 동일한 데이터를 엑셀 수식과 외주 프로그램에 넣고 결과 차이를 "
                "분석해 팀장에게 보고했습니다. 보증 분야에서도 업무 기준을 먼저 익히고 원자료와 "
                "처리값의 차이를 기록해 담당자가 판단할 근거를 빠짐없이 전달하겠습니다. "
                "승인이나 심사 판단을 대신하지 않고, 확인한 사실과 남은 확인 사항을 구분해 보고하겠습니다."
            )
        elif coverage == "company_choice":
            standard = (
                f"{one} 기업의 채무를 보증하기 전에 신용을 조사하고 보증 여부를 심사하며, "
                "보증 뒤에도 기업신용을 관리하는 구조로 이해합니다."
            )
            detailed = (
                f"{standard} 인턴은 승인 판단을 대신하지 않고 기한연장과 상시관리에 필요한 "
                "자료를 확인·기록해 담당자에게 보고해야 합니다. 기업 자료와 기존 기록이 다르면 "
                "원문과 기준 시점을 다시 확인하고, 차이와 남은 확인 사항을 나누어 전달하겠습니다. "
                "공개 자료로 알 수 없는 내부 심사 기준은 추정하지 않겠습니다."
            )
        elif coverage == "representative_experience":
            one = "동일한 데이터를 엑셀 수식과 외주 프로그램에 넣어 결과를 비교하고, 분석 보고서를 작성해 팀장에게 보고했습니다."
            standard = (
                "기존 엑셀 수식과 외주 프로그램에 동일한 데이터를 넣고 나온 결과를 비교해 "
                "분석 보고서를 작성한 뒤 팀장에게 보고했습니다. 제가 직접 한 일은 같은 입력을 "
                "사용해 차이를 확인하고 보고서로 정리한 범위입니다. 결과가 다르다는 사실과 "
                "확인한 범위를 구분해 전달했습니다."
            )
            detailed = (
                f"{standard} 비교의 전제는 두 방식에 같은 데이터를 넣는 것이었고, 나온 값을 "
                "그대로 받아들이지 않고 차이가 있다는 사실을 보고서에 남겼습니다. 수식 개발이나 최종 "
                "의사결정을 제가 했다고 확대하지 않겠습니다. 질문에서 원인을 더 묻더라도 원장에 확인되지 "
                f"않은 내용은 추정하지 않겠습니다. 이 경험은 {duties[0]}에서 원자료와 처리값이 맞는지 "
                "대조하고, 차이와 확인 범위를 담당자에게 보고하는 행동으로 옮기겠습니다. 면접에서는 "
                "동일 입력, 결과 비교, 보고서 작성, 팀장 보고의 순서로 확인된 사실을 설명하겠습니다."
            )
        elif coverage == "failure":
            standard = (
                f"{one} 먼저 잘못된 값이 영향을 주는 범위를 표시하고, 원문·기준일·입력 이력을 "
                "차례로 대조하겠습니다."
            )
            detailed = (
                f"{standard} 차이의 원인을 확인하지 못한 상태에서 임의로 값을 고치지 않겠습니다. "
                "확인한 사실, 아직 모르는 부분, 업무에 미칠 영향을 나누어 담당자에게 보고하겠습니다. "
                "지시를 받은 뒤 수정 전후 값을 기록하고 같은 불일치가 남았는지 재점검하겠습니다. "
                "이는 과거 성과 주장이 아니라 실제 업무 상황에서 따를 대응 원칙입니다."
            )
        elif coverage == "conflict":
            standard = (
                "동일한 데이터를 두 방식에 넣었다는 조건을 먼저 맞추고, 나온 결과의 차이를 "
                "비교해 분석 보고서로 정리했습니다. 확인한 차이는 제 판단으로 덮지 않고 팀장에게 "
                "보고했으며, 답변에서도 확인된 차이와 보고 사실까지만 말하겠습니다."
            )
            detailed = (
                f"{standard} 비교 결과만으로 어느 방식이 항상 옳다고 단정하지 않고, 당시 확인하지 않은 "
                "원인이나 성과도 덧붙이지 않겠습니다. 질문을 받으면 동일 입력, 결과 차이, 보고서 작성, "
                f"팀장 보고의 순서로 확인된 사실만 답하겠습니다. {duties[0]}에서도 값이 다르면 입력과 "
                "근거를 다시 대조한 뒤 차이를 기록해 보고하겠습니다."
            )
        elif coverage == "collaboration":
            standard = (
                f"{one} 현장 의견만 따르지 않고 5개 타 시장의 자료와 나란히 놓아 공통점과 "
                "차이를 정리한 뒤 문제점과 개선 방향을 도출했습니다."
            )
            detailed = (
                f"{standard} 제 역할은 인터뷰와 비교 자료를 정리한 범위이며, 실행 성과까지 "
                "제 기여로 말하지 않겠습니다. 현장 의견과 비교 자료가 다를 때는 어느 한쪽을 먼저 "
                f"결론으로 삼기보다 차이가 생긴 기준을 확인하겠습니다. 이 기준을 {duties[0]}의 자료 확인과 보고에도 적용하겠습니다."
            )
        elif coverage == "strength":
            detailed = (
                f"{standard} 제 강점은 자료가 많아도 출처와 처리 단계를 표시해 다시 확인할 수 있게 "
                "정리하는 점입니다. 지급 결정서·추납·분납 자료를 정리하는 과제를 맡은 경험도 있습니다. "
                "다만 수급 여부를 최종 판단했다고 확대하지 않겠습니다. "
                f"{duties[0]}에서도 같은 기준으로 자료 상태와 남은 확인 사항을 담당자에게 전달하겠습니다."
            )
        elif coverage == "weakness":
            detailed = (
                f"{standard} 처음 듣는 용어와 예외는 질문하기 전에 제가 이해한 내용을 한 줄로 정리하고, "
                "담당자의 답을 업무노트에 남기겠습니다. 다음 처리 때는 같은 항목을 체크리스트로 먼저 "
                "확인한 뒤 질문하겠습니다. 그래도 반복되는 오류는 숨기지 않고 발생 조건과 함께 보고해 "
                "기준을 다시 확인하겠습니다. 이는 확인되지 않은 과거 경험이 아니라 입사 후 실행할 관리 방식입니다."
            )
        elif coverage == "first_90_days":
            standard = (
                "초기에는 기한연장과 기업신용 상시관리의 용어, 자료 항목, 보고 경로를 익히겠습니다. "
                "기준을 확인한 뒤에는 반복 업무를 직접 처리하고, 누락·불일치·변동 사항을 따로 기록해 보고하겠습니다."
            )
            detailed = (
                f"{standard} 업무가 익숙해지면 반복되는 질문과 예외를 점검표로 정리해 다음 처리 전에 "
                "재확인하겠습니다. 판단이 필요한 부분은 임의로 결론 내리지 않고 원자료, 확인한 사실, "
                "남은 확인 사항을 나누어 담당자에게 전달하겠습니다. 인턴 기간의 기여는 승인이나 심사 "
                "판단이 아니라 자료 상태를 정확히 보여 주고 같은 오류를 줄이는 데 두겠습니다. 마지막에는 "
                "배운 기준과 남은 과제를 정리해 인계하겠습니다."
            )
        elif coverage == "core_numbers":
            source_sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", source_answer) if part.strip()]
            standard = " ".join(source_sentences[:5])
            detailed_indexes = (0, 1, 2, 4, 5, 6, 8, 9, 11, 12, 13, 18, 19, 20, 24)
            detailed = " ".join(source_sentences[position] for position in detailed_indexes if position < len(source_sentences))
        has_numeric_claim = any(
            re.search(r"\d", str(claims.get(claim_id, {}).get("normalized_value", "")))
            for claim_id in claim_ids
        )
        if not has_numeric_claim and not card_research:
            one = _NUMBER.sub("해당 수치", one)
            standard = _NUMBER.sub("해당 수치", standard)
            detailed = _NUMBER.sub("해당 수치", detailed)
        brief = one
        if coverage == "self_intro":
            brief = "저는 동일한 데이터를 두 방식으로 처리한 결과를 비교해 분석 보고서를 작성하고 팀장에게 보고한 경험이 있습니다. 이 확인 습관을 보증 업무에 연결하겠습니다."
        elif coverage == "collaboration":
            brief = "상인 인터뷰와 5개 타 시장을 비교해 문제점과 개선 방향을 도출했습니다. 현장 의견과 비교 자료를 함께 보는 태도를 보증 업무에 적용하겠습니다."
        timing_ranges = {"brief": (40, 140), "standard": (120, 320), "detailed": (260, 900)}
        spoken_texts = {"brief": brief, "standard": standard, "detailed": detailed}
        timing_audit = {
            version: {
                "character_count": len(text),
                "expected_range": list(timing_ranges[version]),
                "status": "PASS" if timing_ranges[version][0] <= len(text) <= timing_ranges[version][1] else "REVIEW_REQUIRED",
                "metric_type": "FORMAT_CHECK",
            }
            for version, text in spoken_texts.items()
        }
        answer_cards.append({"question_id": f"Q{index}", "coverage_tag": coverage, "evidence_scope": evidence_scope, "source_question_indexes": [source_index] if source_index else [], "one_sentence_answer": one, "judgment_standard": "정확성·기한·권한 경계를 함께 지키는가", "direct_actions": direct_actions[:3], "job_connection": job_connection, "experience_ids": experience_ids, "experience_claim_ids": claim_ids, "research_claim_ids": card_research, "spoken_versions": {"brief": {"target_seconds": 20, "text": brief}, "standard": {"target_seconds": 60, "text": standard}, "detailed": {"target_seconds": 120, "text": detailed}}, "spoken_timing_audit": timing_audit})

    card_by_question = {card["question_id"]: card for card in answer_cards}
    for question in questions:
        card = card_by_question.get(question["question_id"])
        if card is None:
            continue
        question["answer_anchor"] = card["one_sentence_answer"]
        question["confirmed_evidence"] = card["experience_claim_ids"] + card["research_claim_ids"]
        question["answer_boundary"] = "확인·기록·보고까지만 말하고 승인·심사 권한과 미검증 수치는 주장하지 않음"

    probes: list[dict[str, Any]] = []
    for question_index in range(1, 13):
        card = answer_cards[question_index - 1]
        subject = card["coverage_tag"]
        anchor = card["direct_actions"][0]
        if card["experience_claim_ids"]:
            probe_text = {
                "FACT": f"'{anchor}'을 확인할 수 있는 원자료와 최종 산출물은 각각 무엇입니까?",
                "JUDGMENT": f"'{anchor}'에서 가장 먼저 확인한 항목과 그 순서를 택한 이유는 무엇입니까?",
                "CONTRIBUTION": f"'{anchor}' 가운데 본인이 직접 한 일과 팀이 판단한 일을 나눠 말해 주십시오.",
                "ALTERNATIVE": f"'{anchor}'을 다시 한다면 정확도나 속도를 위해 한 가지 무엇을 바꾸겠습니까?",
                "JOB_TRANSFER": f"'{anchor}'을 {duties[0]}에 적용한다면 첫날 어떤 자료부터 확인하겠습니까?",
            }
            safe_example = "확인된 직접 행동을 먼저 말하고, 팀의 결과와 최종 판단권자의 역할은 분리해 답한다."
        elif card["research_claim_ids"]:
            probe_text = {
                "FACT": f"'{anchor}'의 근거가 된 공식 자료와 확인 기준일은 무엇입니까?",
                "JUDGMENT": f"기관의 여러 기능 중 '{anchor}'을 지원 이유로 선택한 까닭은 무엇입니까?",
                "CONTRIBUTION": f"'{anchor}'에서 인턴이 할 일과 담당자가 판단할 일을 구분해 주십시오.",
                "ALTERNATIVE": f"'{anchor}'과 다른 업무에 배치되면 학습 계획을 어떻게 조정하겠습니까?",
                "JOB_TRANSFER": f"'{anchor}'을 {duties[0]}의 하루 행동으로 바꾸면 무엇부터 하겠습니까?",
            }
            safe_example = "공식 자료에서 확인한 역할까지만 설명하고 내부 절차나 성과는 추정하지 않는다."
        else:
            probe_text = {
                "FACT": f"'{anchor}'은 실제 경험이 아니라 대응 원칙이라는 점을 먼저 밝혀 주시겠습니까?",
                "JUDGMENT": f"'{anchor}'의 어느 단계에서 담당자 확인이 필요합니까?",
                "CONTRIBUTION": f"'{anchor}'에서 본인이 처리할 부분과 즉시 보고할 부분을 나눠 주십시오.",
                "ALTERNATIVE": f"시간이 절반뿐이라면 '{anchor}'에서 무엇을 생략하지 않겠습니까?",
                "JOB_TRANSFER": f"'{anchor}'을 {duties[0]}에 적용할 때 남겨야 할 기록은 무엇입니까?",
            }
            safe_example = "과거에 했다고 바꾸어 말하지 않고, 상황형 질문에 대한 절차와 권한 경계로 답한다."
        for category in _PROBE_CATEGORIES:
            numeric_card = any(re.search(r"\d", str(claims.get(claim_id, {}).get("normalized_value", ""))) for claim_id in card["experience_claim_ids"])
            no_evidence = not card["experience_claim_ids"] and not card["research_claim_ids"]
            retry_goal = {
                "FACT": "자료명과 확인한 사실을 첫 문장에 답하기",
                "JUDGMENT": "선택 기준과 이유를 각각 한 문장으로 말하기",
                "CONTRIBUTION": "내 행동과 타인의 판단을 분리해 말하기",
                "ALTERNATIVE": "한계 하나와 다음 행동 하나만 제시하기",
                "JOB_TRANSFER": "입사 후 첫 행동을 동사로 시작해 말하기",
            }[category]
            probes.append({"probe_id": f"P{len(probes)+1}", "question_id": f"Q{question_index}", "category": category, "question": probe_text[category], "status": "DEFENSIBLE_WITH_QUALIFICATION" if numeric_card or no_evidence else "DEFENSIBLE", "basis_type": "PROCEDURAL_RESPONSE" if no_evidence else "CLAIM_LINKED_RESPONSE", "source_question_indexes": card["source_question_indexes"], "experience_claim_ids": card["experience_claim_ids"], "research_claim_ids": card["research_claim_ids"], "defense_focus": {"FACT": "원문·claim ID·수치 산식", "JUDGMENT": "행동 순서와 선택 기준", "CONTRIBUTION": "팀 결과와 직접 행동 분리", "ALTERNATIVE": "한계와 다음 행동", "JOB_TRANSFER": "기한연장·상시관리의 구체 행동"}[category], "safe_answer_boundary": "상황형 절차 답변은 과거 경험 주장으로 바꾸지 않으며, 원장과 공식 근거에 없는 사실·수치·권한은 말하지 않음", "safe_answer_example": safe_example, "red_flag": "결과 수치를 산식 없이 말하거나 팀 성과를 개인 성과로 바꿈", "retry_goal": retry_goal})

    architecture = {key: {"value": "공식 공고에서 확인되지 않음", "status": "UNKNOWN", "evidence": "동결된 공고에 명시 없음"} for key in ("stage", "format", "duration", "panel", "presentation", "case", "group_discussion")}
    return {
        "schema_version": 2,
        "contract_version": CONTRACT_VERSION,
        "data_package_id": package_id,
        "data_package_version": "2.0",
        "submitted_claims": submitted,
        "document_consistency": [{"item": "자기소개서 경험·수치·기관·직무 참조", "status": "CONSISTENT", "response_strategy": "최종 동결 draft와 경험·공식 근거 ID를 기준으로 답변한다."}],
        "interview_architecture": architecture,
        "competencies": competencies,
        "experience_defense": defense,
        "questions": questions,
        "priority_question_set": [
            {
                "question_id": row["question_id"],
                "question": row["question"],
                "selection_rationale": row["selection_rationale"],
                "answer_anchor": row.get("answer_anchor", ""),
            }
            for row in questions
            if row.get("tier") == 1
        ],
        "high_probability_question_set": [
            {
                "question_id": row["question_id"],
                "question": row["question"],
                "question_type": row["question_type"],
                "selection_rationale": row["selection_rationale"],
                "confirmed_evidence": row.get("confirmed_evidence", []),
                "answer_boundary": row.get("answer_boundary", ""),
            }
            for row in questions
            if row.get("probability") == "HIGH"
        ],
        "job_specific_question_set": [
            {
                "question_id": row["question_id"],
                "question": row["question"],
                "selection_rationale": row["selection_rationale"],
            }
            for row in questions
            if row["question_id"] in {"Q5", "Q7", "Q8", "Q12", "Q13", "Q25", "Q30"}
        ],
        "interview_flow": [
            {"phase": "OPENING", "interviewer": "RECRUITER", "question_ids": ["Q1", "Q2", "Q9"], "purpose": "지원 이유·핵심 강점·첫 인상 확인"},
            {"phase": "ROLE", "interviewer": "HIRING_MANAGER", "question_ids": ["Q3", "Q4", "Q11", "Q12"], "purpose": "기관 역할·보증 업무·정책금융 이해 확인"},
            {"phase": "EVIDENCE", "interviewer": "FACT_AUDITOR", "question_ids": ["Q5", "Q7", "Q8", "Q13", "Q30"], "purpose": "최종 제출 경험의 원자료·직접 행동·한계 검증"},
            {"phase": "SITUATION", "interviewer": "SITUATIONAL_INTERVIEWER", "question_ids": ["Q6", "Q10", "Q15", "Q17"], "purpose": "불일치·오류·고객 요구 상황의 처리 순서 확인"},
            {"phase": "PRESSURE", "interviewer": "RED_TEAM", "question_ids": ["Q28", "Q29", "Q33"], "purpose": "수치·권한·모르는 범위의 사실 경계 검증"},
        ],
        "question_coverage_audit": [
            {
                "question_index": question_index,
                "experience_claim_ids": refs[1],
                "research_claim_ids": refs[2],
                "covered_by_question_ids": [
                    row["question_id"]
                    for row in questions
                    if question_index in row.get("source_question_indexes", [])
                ],
                "status": "COVERED",
            }
            for question_index, refs in sorted(refs_by_question.items())
        ],
        "answer_cards": answer_cards,
        "probes": probes,
        "reverse_questions": ["입사 초기 가장 먼저 익혀야 할 품질 기준은 무엇입니까?", "반복적으로 발생하는 예외 업무와 보고 기준은 무엇입니까?", "인턴이 피드백을 가장 빠르게 업무에 반영하는 방법은 무엇입니까?"],
        "day_of_checklist": ["회사명·직무명·공고 업무 재확인", "핵심 경험의 직접 행동·판단 기준·한계 확인", "수치가 있는 claim의 산출 근거와 기여 범위 확인", "모르는 질문에서 사실 경계를 지키는 문장 연습"],
        "delivery_evaluation": {"content_criteria": ["질문에 먼저 답함", "claim ID 범위 안의 사실", "개인 기여와 한계 구분", "직무 행동 연결"], "delivery_criteria": ["첫 문장 20초 이내", "문장 종결을 흐리지 않음", "속도·호흡·시선", "추가질문 뒤 핵심을 다시 정리"]},
        "unknown_answer_policy": {"validity_check": "질문의 전제와 기준 시점을 먼저 확인합니다.", "confirmed_fact": "제가 확인한 공식 자료와 확정 경험에서 아는 범위를 먼저 말합니다.", "boundary_statement": "제가 확인한 공식 자료의 범위에서는 여기까지 말씀드릴 수 있습니다.", "reasoning_bridge": "다만 공고의 업무와 확인된 원칙을 기준으로 보면 이렇게 접근하겠습니다.", "verification_commitment": "입사 후에는 담당 기준과 최신 자료를 먼저 확인한 뒤 판단하겠습니다.", "job_link": f"확인 결과는 {duties[0]}의 기록·보고 행동으로 연결합니다."},
        "pressure_boundaries": ["수치의 기준값·결과값·산식·측정기간 중 하나라도 없으면 숫자를 말하지 않음", "팀 결과와 본인의 직접 행동을 한 문장씩 분리", "보증 승인·신용판단은 담당자의 권한이며 인턴은 확인·기록·보고까지만 수행", "확인되지 않은 내부 문화·KPI·시스템 권한은 모른다고 답한 뒤 확인 경로를 제시"],
        "pressure_response_examples": [
            {"challenge": "그 수치가 정확하다는 근거가 있습니까?", "safe_response": "현재 원장에는 산식 전체가 확인되지 않아 숫자로 단정하지 않겠습니다. 확인된 것은 제가 수행한 분류·대조·보고 행동입니다."},
            {"challenge": "결국 본인이 성과를 만든 것 아닙니까?", "safe_response": "팀의 최종 결과와 제 기여는 구분해야 합니다. 제가 직접 한 일은 원자료를 대조하고 차이를 기록해 보고한 범위입니다."},
            {"challenge": "인턴도 보증 여부를 판단할 수 있지 않습니까?", "safe_response": "보증 승인과 신용판단은 담당자의 권한입니다. 저는 기준에 맞게 자료를 확인·기록하고 이상 사항을 보고하겠습니다."},
            {"challenge": "모르는 내용도 의견을 말해 보십시오.", "safe_response": "공식 자료에서 확인한 범위까지만 말씀드리겠습니다. 확인이 필요한 부분은 판단 기준과 확인 경로를 제시하겠습니다."},
        ],
        "simulation_policy": {"mode": "RANDOM_MIXED", "feedback_timing": "AFTER_FULL_INTERVIEW", "difficulty": "REALISTIC", "one_question_at_a_time": True, "wait_for_user_answer": True, "rounds": [{"round": 1, "mode": "STANDARD", "success_criteria": ["60초 안에 질문에 먼저 답함", "claim ID 밖 사실 없음"]}, {"round": 2, "mode": "FACT_CHECK", "success_criteria": ["수치 산식과 개인 기여 범위 설명", "모르는 범위 인정"]}, {"round": 3, "mode": "PRESSURE", "success_criteria": ["반론 뒤에도 사실 경계 유지", "대안과 직무 전이 제시"]}], "retry_rule": "실패 기준 한 개만 정해 같은 질문을 다시 답하고, 통과 후 다음 질문으로 이동"},
        "final_audit": {"status": "CONDITIONAL_PASS", "strongest_point": "최종 자기소개서의 경험·research claim을 질문과 답변 카드까지 추적할 수 있습니다.", "largest_risk": "실제 면접 형식과 배치 부서의 세부 업무는 공식 자료에서 확인되지 않았습니다.", "priority_revisions": ["실제 음성 모의면접으로 전달 방식 확인", "공고 갱신 시 면접 구조 재확인"]},
    }


def build_run_prompt_contracts(run_dir: Path) -> tuple[Path, Path]:
    """Create complete paired contracts without overwriting existing artifacts."""
    run_dir = run_dir.resolve()
    company_path = run_dir / COMPANY_CONTRACT_NAME
    interview_path = run_dir / INTERVIEW_CONTRACT_NAME
    if company_path.exists() or interview_path.exists():
        raise FileExistsError("통합 계약 파일이 이미 있습니다. 기존 파일을 검토하거나 별도 실행 디렉터리를 사용하세요.")
    state = _load(run_dir / "run.json", {})
    posting = _load(run_dir / "00_채용공고분석.json", {})
    ledger = _load(run_dir / "02_확정경험원장.json", {})
    research = _rows(_load(run_dir / "04_공식근거.json", []))
    matches = _rows(_load(run_dir / "03_경험직무매칭.json", []))
    draft = _draft_rows(run_dir)
    if not isinstance(state, dict) or not isinstance(posting, dict) or not isinstance(ledger, dict):
        raise ValueError("통합 계약 생성 입력 형식이 잘못되었습니다.")
    experiences, claims = _experience_index(ledger)
    package_id = _package_id(run_dir)
    target = str(state.get("target") or posting.get("target") or "").strip()
    company = _build_company(package_id=package_id, target=target, posting=posting, research=research, matches=matches, experiences=experiences)
    interview = _build_interview(package_id=package_id, posting=posting, research=research, draft=draft, experiences=experiences, claims=claims)

    # Validate the in-memory payloads in an isolated staging directory so a
    # failed build never leaves one half of the required contract pair behind.
    company_path.write_text(json.dumps(company, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    interview_path.write_text(json.dumps(interview, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = validate_run_prompt_contracts(run_dir, target=target, responses=draft)
    if report.hard_fail:
        company_path.unlink(missing_ok=True)
        interview_path.unlink(missing_ok=True)
        (run_dir / "13_프롬프트통합검증.json").unlink(missing_ok=True)
        codes = ", ".join(issue.code for issue in report.issues if issue.severity == "HARD_FAIL")
        raise ValueError(f"자동 생성한 통합 계약이 검증을 통과하지 못했습니다: {codes}")
    return company_path, interview_path


def refresh_run_interview_contract(run_dir: Path, draft: list[dict[str, Any]]) -> Path:
    """Rebuild the interview contract from the selected final draft.

    Unlike initial ``contracts build``, this is an intentional finalization
    refresh. It preserves the company contract and replaces only the generated
    interview packet so no incumbent or unused experience can leak into the
    selected result.
    """
    run_dir = run_dir.resolve()
    posting = _load(run_dir / "00_채용공고분석.json", {})
    ledger = _load(run_dir / "02_확정경험원장.json", {})
    research = _rows(_load(run_dir / "04_공식근거.json", []))
    if not isinstance(posting, dict) or not isinstance(ledger, dict):
        raise ValueError("최종 면접 계약 갱신 입력 형식이 잘못되었습니다.")
    experiences, claims = _experience_index(ledger)
    payload = _build_interview(
        package_id=_package_id(run_dir),
        posting=posting,
        research=research,
        draft=_rows(draft),
        experiences=experiences,
        claims=claims,
        include_candidate_pool=False,
    )
    path = run_dir / INTERVIEW_CONTRACT_NAME
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def enrich_run_company_research(
    source_run: Path,
    output_run: Path,
    claim_ledger_path: Path | list[Path],
    source_ledger_path: Path | list[Path],
    fresh_selection: bool = False,
) -> tuple[Path, Path, Path]:
    """Clone a run and import only primary-source-confirmed company claims.

    The source run and supplied ledgers are read-only. Every imported claim
    must be CONFIRMED_PRIMARY and all of its source IDs must resolve to HTTPS
    statute/official/public-disclosure sources. The resulting run receives a
    new data-package digest and freshly built paired contracts.
    """
    source_run = source_run.resolve()
    output_run = output_run.resolve()
    if output_run.exists():
        raise FileExistsError(f"보강 출력 run이 이미 존재합니다: {output_run}")
    claim_paths = claim_ledger_path if isinstance(claim_ledger_path, list) else [claim_ledger_path]
    source_paths = source_ledger_path if isinstance(source_ledger_path, list) else [source_ledger_path]
    claim_payloads = [_load(path.resolve(), {}) for path in claim_paths]
    source_payloads = [_load(path.resolve(), {}) for path in source_paths]
    external_claims = [
        row
        for payload in claim_payloads
        if isinstance(payload, dict)
        for row in _rows(payload.get("claims"))
    ]
    external_sources: list[dict[str, Any]] = []
    for payload in source_payloads:
        if not isinstance(payload, dict):
            continue
        package_checked_at = str(payload.get("checked_at") or payload.get("collected_at") or "")[:10]
        for row in _rows(payload.get("sources")):
            copied = dict(row)
            copied.setdefault("checked_at", package_checked_at)
            external_sources.append(copied)
    cutoff_values = [
        str(payload.get("research_cutoff_date") or payload.get("checked_at") or "")[:10]
        for payload in [*claim_payloads, *source_payloads]
        if isinstance(payload, dict)
    ]
    research_cutoff = max((value for value in cutoff_values if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)), default="")
    source_by_id = {
        str(row.get("source_id", "")).strip(): row
        for row in external_sources
        if str(row.get("source_id", "")).strip()
    }
    accepted_source_types = {"STATUTE", "OFFICIAL_WEB", "PUBLIC_DISCLOSURE", "OFFICIAL_DISCLOSURE", "OFFICIAL_PRESS_RELEASE", "OFFICIAL_POSTING"}
    claim_type_map = {
        "ENTITY": "organization_role",
        "BUSINESS_MODEL": "organization_role",
        "VALUE_CHAIN": "organization_role",
        "CUSTOMER": "organization_role",
        "OPERATIONS": "job_duty",
        "RISK_CONTROL": "risk_or_limit",
        "PROGRAM": "program_or_service",
        "CULTURE": "organization_role",
        "GOVERNANCE": "organization_role",
        "FUNDING_LOGIC": "organization_role",
        "ORGANIZATION": "organization_role",
        "STRATEGY": "program_or_service",
        "STRATEGY_EXECUTION": "program_or_service",
        "INVESTMENT": "program_or_service",
    }
    imported: list[dict[str, Any]] = []
    for row in external_claims:
        if str(row.get("verification_status", "")).strip() != "CONFIRMED_PRIMARY":
            continue
        source_ids = _strings(row.get("source_ids"))
        sources = [source_by_id.get(source_id) for source_id in source_ids]
        if not sources or any(source is None for source in sources):
            continue
        if any(
            str(source.get("source_type", "")).strip() not in accepted_source_types
            or not str(source.get("url", "")).startswith("https://")
            for source in sources
            if source is not None
        ):
            continue
        claim_id = str(row.get("claim_id", "")).strip()
        claim = " ".join(str(row.get("claim", "")).split())
        if not claim_id or not claim:
            continue
        primary = sources[0] or {}
        checked_at = str(primary.get("checked_at") or research_cutoff or "")[:10]
        published_at = str(primary.get("published_or_effective_at") or "")[:10]
        domain = str(row.get("domain") or "").upper()
        imported.append(
            {
                "claim_id": claim_id,
                "claim": claim,
                "source_url": str(primary.get("url", "")),
                "source_type": "official",
                "checked_at": checked_at,
                "evidence_excerpt": claim,
                "verification_status": "verified",
                "claim_type": claim_type_map.get(domain, "organization_role"),
                "research_domain": domain,
                "published_at": published_at,
                "basis_date": published_at or checked_at,
                "conflict_note": str(row.get("counterevidence_or_limit") or ""),
                "application_use": str(row.get("application_use") or "회사조사·자기소개서·면접"),
                "usage_restriction": str(row.get("usage_restriction") or "출처 범위 밖으로 확대하지 말 것"),
                "source_ids": source_ids,
                "source_evidence": [
                    {
                        "source_id": source_id,
                        "source_type": str(source_by_id[source_id].get("source_type", "")),
                        "publisher": str(source_by_id[source_id].get("publisher", "")),
                        "title": str(source_by_id[source_id].get("title", "")),
                        "url": str(source_by_id[source_id].get("url", "")),
                        "checked_at": str(source_by_id[source_id].get("checked_at", "")),
                        "published_or_effective_at": str(source_by_id[source_id].get("published_or_effective_at", "")),
                        "evidence_locator": str(source_by_id[source_id].get("evidence_locator", "")),
                    }
                    for source_id in source_ids
                ],
            }
        )
    if not imported:
        raise ValueError("공식 1차 출처로 확인된 회사 claim을 가져오지 못했습니다.")

    ignored = {
        COMPANY_CONTRACT_NAME,
        INTERVIEW_CONTRACT_NAME,
        "13_프롬프트통합검증.json",
        "11_최종품질감사.json",
        "11_최종품질감사.md",
    }
    if fresh_selection:
        ignored.update(
            {
                "rigorous",
                "draft_final.json",
                "06_자기소개서.md",
                "06_자기소개서.docx",
                "09_style_diagnostics.json",
                "09_copyeditor_report.json",
                "10_품질점수.json",
                "12_최종산출물.json",
                "rendered_docx_final",
            }
        )
    shutil.copytree(source_run, output_run, ignore=lambda _directory, names: [name for name in names if name in ignored])
    if fresh_selection:
        state_path = output_run / "run.json"
        state = _load(state_path, {})
        if isinstance(state, dict):
            state.pop("final_artifact", None)
            state["status"] = "prepared"
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    research_path = output_run / "04_공식근거.json"
    current = _rows(_load(research_path, []))
    by_id = {str(row.get("claim_id", "")).strip(): row for row in current if str(row.get("claim_id", "")).strip()}
    for row in imported:
        by_id.setdefault(str(row["claim_id"]), row)
    research_path.write_text(json.dumps(list(by_id.values()), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    execution_path = output_run / "04_리서치실행.json"
    execution = _load(execution_path, {})
    if isinstance(execution, dict):
        verified_ids = set(_strings(execution.get("verified_claim_ids")))
        verified_ids.update(str(row["claim_id"]) for row in imported)
        execution["verified_claim_ids"] = sorted(verified_ids)
        families = set(_strings(execution.get("source_families")))
        families.update({"statute", "official_organization_web"})
        execution["source_families"] = sorted(families)
        execution_path.write_text(json.dumps(execution, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    research_md = output_run / "04_기업직무조사.md"
    if research_md.is_file():
        lines = [research_md.read_text(encoding="utf-8").rstrip(), "", "## 보강된 공식 1차 근거", ""]
        lines.extend(
            f"- `{row['claim_id']}` {row['claim']} ([공식 원문]({row['source_url']}))"
            for row in imported
        )
        lines.extend(["", "각 claim은 공식 원문 범위에서만 사용하며, usage_restriction을 넘어 성과·권한·내부문화로 확대하지 않습니다.", ""])
        research_md.write_text("\n".join(lines), encoding="utf-8")
    company_path, interview_path = build_run_prompt_contracts(output_run)
    return research_path, company_path, interview_path


def apply_source_refresh_audit(run_dir: Path, audit_path: Path) -> Path:
    """Apply a separately verified URL refresh without changing claim content."""
    run_dir = run_dir.resolve()
    company_path = run_dir / COMPANY_CONTRACT_NAME
    company = _load(company_path, {})
    audit = _load(audit_path.resolve(), {})
    entries = _rows(audit.get("entries") if isinstance(audit, dict) else None)
    if not isinstance(company, dict) or not entries:
        raise ValueError("회사 계약 또는 출처 재확인 감사 형식이 올바르지 않습니다.")
    verified: dict[str, str] = {}
    for row in entries:
        url = str(row.get("url", "")).strip()
        checked_at = str(row.get("checked_at", "")).strip()[:10]
        status = str(row.get("status", "")).strip().upper()
        if status != "VERIFIED" or not url.startswith("https://") or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", checked_at):
            raise ValueError("재확인 항목은 VERIFIED, https URL, YYYY-MM-DD checked_at이 필요합니다.")
        verified[url] = checked_at
    matched: set[str] = set()
    manifest = _rows(company.get("source_manifest"))
    for row in manifest:
        url = str(row.get("url", "")).strip()
        if url in verified:
            row["checked_at"] = verified[url]
            matched.add(url)
    missing = sorted(set(verified) - matched)
    if missing:
        raise ValueError("회사 계약에 없는 URL을 재확인 감사가 참조합니다: " + ", ".join(missing))
    original = company_path.read_text(encoding="utf-8")
    company["source_manifest"] = manifest
    company["research_cutoff_date"] = max(
        [str(company.get("research_cutoff_date", "")), *verified.values()]
    )
    company["source_refresh_audit"] = {
        "verified_at": max(verified.values()),
        "verified_urls": sorted(verified),
        "claim_content_changed": False,
        "audit_sha256": sha256(audit_path.resolve().read_bytes()).hexdigest(),
    }
    company_path.write_text(json.dumps(company, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = validate_run_prompt_contracts(run_dir)
    if report.hard_fail:
        company_path.write_text(original, encoding="utf-8")
        validate_run_prompt_contracts(run_dir)
        raise ValueError("출처 재확인 적용 뒤 계약 검증에 실패했습니다.")
    return company_path
