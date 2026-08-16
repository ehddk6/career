#!/usr/bin/env python3
"""Deterministic structural validator for the interview preparation package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "frozen/manifest.json",
    "frozen/interview_data_package.yaml",
    "evidence/submitted_claim_ledger.md",
    "evidence/document_consistency_table.md",
    "evidence/needs_verification.md",
    "evidence/prohibited_claims.md",
    "architecture/interview_architecture_packet.md",
    "architecture/competency_map.md",
    "final/one_page_interview_map.md",
    "final/core_question_set.md",
    "final/answer_cards.md",
    "final/probe_defense_notes.md",
    "final/company_fact_sheet.md",
    "final/reverse_questions.md",
    "final/day_of_checklist.md",
    "final/final_audit.md",
    "final/interview_package.json",
]

SOURCE_HASHES = {
    "input/career_run/00_채용공고원문/source.docx": "5b6f69118ca1eece39f284fb26c18e42422ba01088f978b9829c0501bc456779",
    "input/career_run/02_확정경험원장.json": "485c2fad17ec5cddf117b884e0baf61d4aa9bcfdc9c5b1cc96ab1435e2d3f2c4",
    "input/career_run/draft_final.json": "de94aed7e0cdaaf22607bd4afbf649d63e91861f18d3dc94c899b655590da50b",
    "input/career_run/04_공식근거.json": "4956a70618e06435f17e122eaa31fd1cb33abe00df425fd468302df46b88bcf0",
    "input/career_run/12_최종산출물.json": "32adf25c653e09d89ebf95fec255ce5f47922449d96c1659f277fe013cce9beb",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def validate() -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    checks: list[dict] = []

    missing = [p for p in REQUIRED_FILES if not (ROOT / p).is_file()]
    checks.append({"name": "required_files", "passed": not missing, "missing": missing})
    if missing:
        errors.append(f"required files missing: {missing}")

    package = None
    package_path = ROOT / "final/interview_package.json"
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
        checks.append({"name": "package_json", "passed": True})
    except Exception as exc:  # pragma: no cover - diagnostic path
        checks.append({"name": "package_json", "passed": False, "error": str(exc)})
        errors.append(f"invalid package json: {exc}")

    manifest = None
    manifest_path = ROOT / "frozen/manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        checks.append({"name": "manifest_json", "passed": True})
    except Exception as exc:  # pragma: no cover - diagnostic path
        checks.append({"name": "manifest_json", "passed": False, "error": str(exc)})
        errors.append(f"invalid manifest json: {exc}")

    if package:
        counts = package.get("question_counts", {})
        count_ok = counts == {"tier_1": 12, "tier_2": 15, "tier_3": 8, "total": 35}
        checks.append({"name": "question_counts", "passed": count_ok, "actual": counts})
        if not count_ok:
            errors.append(f"question count contract mismatch: {counts}")

        card_ids = package.get("answer_card_ids", [])
        expected_cards = [f"Q{i:03d}" for i in range(1, 13)]
        cards_ok = card_ids == expected_cards
        checks.append({"name": "answer_card_ids", "passed": cards_ok, "actual": card_ids})
        if not cards_ok:
            errors.append("answer card IDs must be Q001..Q012 in order")

        if package.get("target", {}).get("organization") != "신용보증기금":
            errors.append("target organization mismatch")
        if package.get("target", {}).get("job") != "체험형 청년인턴1(보증)":
            errors.append("target job mismatch")
        if package.get("status") != "REVIEW_REQUIRED":
            warnings.append("package status is not REVIEW_REQUIRED despite open verification items")

    if not missing:
        questions = read_text("final/core_question_set.md")
        seen_questions = sorted(set(re.findall(r"\bQ\d{3}\b", questions)))
        expected_questions = [f"Q{i:03d}" for i in range(1, 36)]
        q_ok = seen_questions == expected_questions
        checks.append({"name": "question_ids_in_markdown", "passed": q_ok, "count": len(seen_questions)})
        if not q_ok:
            errors.append("core question markdown must contain Q001..Q035")

        answers = read_text("final/answer_cards.md")
        answer_headers = re.findall(r"^## (Q\d{3})\.", answers, flags=re.MULTILINE)
        a_ok = answer_headers == [f"Q{i:03d}" for i in range(1, 13)]
        checks.append({"name": "answer_headers", "passed": a_ok, "actual": answer_headers})
        if not a_ok:
            errors.append("answer card headers must contain Q001..Q012 exactly once and in order")

        for token in ["### 20초", "### 60초", "### 120초 확장"]:
            actual = answers.count(token)
            ok = actual == 12
            checks.append({"name": f"answer_section_{token}", "passed": ok, "count": actual})
            if not ok:
                errors.append(f"{token} must appear 12 times, found {actual}")

        duration_specs = {
            "20초": (60, 230, r"^### 20초\s*(.*?)(?=^### 60초)"),
            "60초": (180, 550, r"^### 60초\s*(.*?)(?=^### 120초 확장)"),
            "120초": (350, 1100, r"^### 120초 확장\s*(.*?)(?=^## Q\d{3}\.|^## 공통|\Z)"),
        }
        duration_results = []
        for question_id in [f"Q{i:03d}" for i in range(1, 13)]:
            block_match = re.search(
                rf"^## {question_id}\..*?(?=^## Q\d{{3}}\.|^## 공통|\Z)",
                answers,
                flags=re.MULTILINE | re.DOTALL,
            )
            if not block_match:
                continue
            block = block_match.group(0)
            for label, (lower, upper, pattern) in duration_specs.items():
                match = re.search(pattern, block, flags=re.MULTILINE | re.DOTALL)
                clean = re.sub(r"[\s“”]", "", match.group(1)) if match else ""
                count = len(clean)
                duration_results.append(
                    {
                        "question_id": question_id,
                        "section": label,
                        "character_count_no_whitespace": count,
                        "expected_range": [lower, upper],
                        "passed": lower <= count <= upper,
                    }
                )
        duration_ok = len(duration_results) == 36 and all(item["passed"] for item in duration_results)
        checks.append({"name": "estimated_duration_ranges", "passed": duration_ok, "sections": duration_results})
        if not duration_ok:
            warnings.append("one or more answer sections fall outside the estimated character bands; audio timing remains required")

        banned = {
            "target_confusion": "한국도로공사서비스",
            "authority_overreach": "제가 보증을 결정하겠습니다",
            "unsupported_pass_probability": "합격 확률",
        }
        for name, phrase in banned.items():
            found = phrase in answers
            checks.append({"name": name, "passed": not found})
            if found:
                errors.append(f"banned phrase in answer cards: {phrase}")

        unresolved = re.findall(r"TODO|\[PLACEHOLDER\]|\{\{.+?\}\}", answers)
        checks.append({"name": "unresolved_templates", "passed": not unresolved, "actual": unresolved})
        if unresolved:
            errors.append(f"unresolved templates in answer cards: {unresolved}")

        claim_ledger = read_text("evidence/submitted_claim_ledger.md")
        fact_sheet = read_text("final/company_fact_sheet.md")
        if package:
            missing_claims = [c for c in package.get("submitted_claim_ids", []) if c not in claim_ledger]
            missing_facts = [f for f in package.get("official_fact_ids", []) if f not in fact_sheet]
            checks.append({"name": "claim_references", "passed": not missing_claims, "missing": missing_claims})
            checks.append({"name": "fact_references", "passed": not missing_facts, "missing": missing_facts})
            if missing_claims:
                errors.append(f"claim IDs missing from ledger: {missing_claims}")
            if missing_facts:
                errors.append(f"fact IDs missing from fact sheet: {missing_facts}")

    source_results = []
    for relative, expected in SOURCE_HASHES.items():
        path = ROOT / relative
        actual = sha256(path) if path.is_file() else None
        source_results.append({"path": relative, "expected": expected, "actual": actual, "passed": actual == expected})
        if actual != expected:
            errors.append(f"source hash mismatch: {relative}")
    checks.append({"name": "frozen_source_hashes", "passed": all(r["passed"] for r in source_results), "files": source_results})

    if manifest:
        listed = {item.get("path"): item.get("sha256") for item in manifest.get("frozen_inputs", [])}
        manifest_sources_ok = all(listed.get(path) == expected for path, expected in SOURCE_HASHES.items())
        checks.append({"name": "manifest_source_hashes", "passed": manifest_sources_ok})
        if not manifest_sources_ok:
            errors.append("manifest source hashes do not match the frozen contract")

        generated_results = []
        for item in manifest.get("generated_artifacts", []):
            relative = item.get("path")
            expected = item.get("sha256")
            path = ROOT / relative if relative else None
            actual = sha256(path) if path and path.is_file() else None
            generated_results.append(
                {"path": relative, "expected": expected, "actual": actual, "passed": actual == expected}
            )
            if actual != expected:
                errors.append(f"generated artifact hash mismatch: {relative}")
        generated_ok = bool(generated_results) and all(item["passed"] for item in generated_results)
        checks.append({"name": "generated_artifact_hashes", "passed": generated_ok, "files": generated_results})

    return {
        "validator": "scripts/validate_answers.py",
        "structural_status": "PASS" if not errors else "FAIL",
        "readiness_status": package.get("status") if package else "UNKNOWN",
        "checks_passed": sum(1 for c in checks if c.get("passed")),
        "checks_total": len(checks),
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit canonical JSON")
    args = parser.parse_args()
    result = validate()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"structural_status: {result['structural_status']}")
        print(f"readiness_status: {result['readiness_status']}")
        print(f"checks: {result['checks_passed']}/{result['checks_total']}")
        for error in result["errors"]:
            print(f"ERROR: {error}")
        for warning in result["warnings"]:
            print(f"WARNING: {warning}")
    return 0 if result["structural_status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
