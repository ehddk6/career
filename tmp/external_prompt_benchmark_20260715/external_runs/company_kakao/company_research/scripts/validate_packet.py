#!/usr/bin/env python3
"""Validate the offline company-research packet and frozen-input integrity."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "company_research"
PACKAGE_ID = "CR-DATA-001"
PACKAGE_VERSION = "1.0"
RESEARCH_QUESTIONS_SHA256 = "793187b88f75c86aa8bc12490b678acc5c32a2c2babdff0be2ec230707d0ad42"
INPUT_SET_SHA256 = "7ddc582ec568dc654f2bf0701d4fd4b885d4f4bfbc4a3ced4dbe1d3103ca61cf"

REQUIRED = [
    "frozen/research_questions.md",
    "frozen/manifest.json",
    "frozen/company_data_package.yaml",
    "frozen/entity_map.md",
    "frozen/input_inventory.md",
    "evidence/source_register.md",
    "evidence/claim_ledger.md",
    "evidence/contradiction_log.md",
    "evidence/needs_verification.md",
    "evidence/prohibited_claims.md",
    "analysis/business_model_map.md",
    "analysis/revenue_logic.md",
    "analysis/value_chain_map.md",
    "analysis/customer_map.md",
    "analysis/organization_map.md",
    "analysis/event_timeline.md",
    "analysis/strategy_resource_alignment.md",
    "analysis/strategy_execution_status.md",
    "analysis/financial_evidence.md",
    "validation/financial_calculations.json",
    "validation/financial_calculations.csv",
    "validation/calculation_audit.md",
    "analysis/competitor_selection.md",
    "analysis/peer_comparison.md",
    "analysis/substitute_map.md",
    "hypotheses/operating_reality.md",
    "hypotheses/strategy_and_market.md",
    "hypotheses/risk_and_governance.md",
    "hypotheses/talent_and_job.md",
    "analysis/culture_evidence.md",
    "analysis/employment_signal_map.md",
    "analysis/culture_unknowns.md",
    "analysis/role_value_map.md",
    "analysis/first_90_days.md",
    "analysis/job_reality_packet.md",
    "analysis/applicant_company_bridge.md",
    "analysis/fit_gap_table.md",
    "analysis/motivation_evidence.md",
    "validation/red_team_report.md",
    "validation/contradiction_matrix.md",
    "validation/hard_fail_report.json",
    "validation/revision_required.md",
    "judges/business_analyst.md",
    "judges/fact_and_source_auditor.md",
    "judges/recruiter_and_job_auditor.md",
    "judges/scorecard.md",
    "synthesis/company_analysis_S.md",
    "synthesis/change_log.md",
    "synthesis/synthesis_validation.json",
    "final/one_page_company_brief.md",
    "final/full_company_report.md",
    "final/application_bridge.md",
    "final/interview_packet.md",
    "final/reverse_questions.md",
    "final/source_appendix.md",
    "final/final_audit.md",
    "final/research_decision.json",
    "final/claim_ledger.md",
    "final/prohibited_claims.md",
    "final/validation_report.md",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def input_set_hash() -> str:
    pairs = []
    for path in sorted(p for p in (ROOT / "input").rglob("*") if p.is_file()):
        pairs.append(f"{path.relative_to(ROOT).as_posix()}\t{sha256(path)}")
    return hashlib.sha256("\n".join(pairs).encode("utf-8")).hexdigest()


def check(condition: bool, code: str, errors: list[str]) -> None:
    if not condition:
        errors.append(code)


def main() -> None:
    errors: list[str] = []
    for rel in REQUIRED:
        path = OUT / rel
        check(path.is_file(), f"MISSING:{rel}", errors)
        if path.is_file():
            check(path.stat().st_size > 0, f"EMPTY:{rel}", errors)

    check(sha256(OUT / "frozen/research_questions.md") == RESEARCH_QUESTIONS_SHA256,
          "STEP0_HASH_MISMATCH", errors)
    check(input_set_hash() == INPUT_SET_SHA256, "INPUT_SET_HASH_MISMATCH", errors)

    manifest = json.loads((OUT / "frozen/manifest.json").read_text(encoding="utf-8"))
    check(len(manifest["inputs"]) == 62, "MANIFEST_INPUT_COUNT", errors)
    check(manifest["counts"]["eligible_target_company_sources"] == 0,
          "TARGET_SOURCE_COUNT", errors)
    for row in manifest["inputs"]:
        path = ROOT / row["path"]
        check(path.is_file(), f"MANIFEST_PATH_MISSING:{row['path']}", errors)
        if path.is_file():
            check(sha256(path) == row["sha256"], f"MANIFEST_HASH:{row['path']}", errors)

    json_paths = sorted(OUT.rglob("*.json"))
    for path in json_paths:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - explicit validation output
            errors.append(f"JSON_PARSE:{path.relative_to(ROOT).as_posix()}:{exc}")
            continue
        if isinstance(value, dict) and "company_data_package_id" in value:
            check(value["company_data_package_id"] == PACKAGE_ID,
                  f"PACKAGE_ID:{path.relative_to(ROOT).as_posix()}", errors)
            check(str(value.get("company_data_package_version")) == PACKAGE_VERSION,
                  f"PACKAGE_VERSION:{path.relative_to(ROOT).as_posix()}", errors)

    decision = json.loads((OUT / "final/research_decision.json").read_text(encoding="utf-8"))
    check(decision["decision"] == "INSUFFICIENT_EVIDENCE", "DECISION", errors)
    check(decision["hard_fail_status"] == "NOT_TRIGGERED", "DECISION_HARD_FAIL", errors)
    hard_fail = json.loads((OUT / "validation/hard_fail_report.json").read_text(encoding="utf-8"))
    check(hard_fail["active_hard_fail_count"] == 0, "ACTIVE_HARD_FAIL", errors)
    financial = json.loads((OUT / "validation/financial_calculations.json").read_text(encoding="utf-8"))
    check(financial["calculation_count"] == 0, "FINANCIAL_COUNT", errors)
    check(financial["eligible_source_count"] == 0, "FINANCIAL_SOURCE_COUNT", errors)

    with (OUT / "validation/financial_calculations.csv").open(encoding="utf-8", newline="") as f:
        csv_rows = list(csv.DictReader(f))
    check(len(csv_rows) == 12, "FINANCIAL_CSV_ROW_COUNT", errors)
    check(all(r["status"] == "NEEDS_VERIFICATION" for r in csv_rows),
          "FINANCIAL_CSV_STATUS", errors)

    check((OUT / "evidence/claim_ledger.md").read_bytes() ==
          (OUT / "final/claim_ledger.md").read_bytes(), "CLAIM_LEDGER_SNAPSHOT", errors)
    check((OUT / "evidence/prohibited_claims.md").read_bytes() ==
          (OUT / "final/prohibited_claims.md").read_bytes(), "PROHIBITED_SNAPSHOT", errors)

    output_manifest = json.loads((OUT / "validation/output_manifest.json").read_text(encoding="utf-8"))
    for row in output_manifest["files"]:
        path = ROOT / row["path"]
        check(path.is_file(), f"OUTPUT_PATH_MISSING:{row['path']}", errors)
        if path.is_file():
            check(sha256(path) == row["sha256"], f"OUTPUT_HASH:{row['path']}", errors)

    final_business_text = "\n".join(
        (OUT / rel).read_text(encoding="utf-8")
        for rel in [
            "final/one_page_company_brief.md",
            "final/full_company_report.md",
            "final/application_bridge.md",
            "final/interview_packet.md",
        ]
    )
    banned_assertions = [
        "카카오는 (주)카카오",
        "카카오는 업계를 선도",
        "카카오는 안정적으로 성장",
        "카카오는 혁신적이고 직원 중심",
    ]
    for phrase in banned_assertions:
        check(phrase not in final_business_text, f"BANNED_ASSERTION:{phrase}", errors)

    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    print(json.dumps({
        "status": "PASS",
        "required_files": len(REQUIRED),
        "input_files": 62,
        "json_files_parsed": len(json_paths),
        "financial_calculations": 0,
        "active_hard_fails": 0,
        "decision": "INSUFFICIENT_EVIDENCE",
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
