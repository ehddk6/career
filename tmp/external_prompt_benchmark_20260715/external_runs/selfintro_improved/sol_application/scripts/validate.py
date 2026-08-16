from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


RUN_ID = "SOL-20260715-1537"
DATA_PACKAGE_ID = "SOL-DATA-EXT-001"
DATA_PACKAGE_VERSION = "1.0"
QUESTION_LIMITS = {
    1: (400, 600),
    2: (400, 600),
    3: (400, 600),
    4: (None, 1500),
}
PII_PATTERNS = {
    "name": re.compile(r"(?:제\s*이름은|성명\s*[:：])"),
    "age": re.compile(r"(?:만\s*\d{1,2}\s*세|\d{2}\s*살)"),
    "gender": re.compile(r"(?:성별\s*[:：]|남성입니다|여성입니다)"),
    "origin": re.compile(r"(?:출신지|고향은)"),
    "family": re.compile(r"(?:가족관계|아버지|어머니|형제자매)"),
    "school": re.compile(r"(?:대학교|대학원|고등학교|학력)"),
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def count_text(text: str) -> dict[str, int]:
    without_linebreaks = text.replace("\r", "").replace("\n", "")
    return {
        "with_spaces_without_linebreaks": len(without_linebreaks),
        "without_spaces": len(re.sub(r"\s", "", text)),
        "with_linebreaks": len(text.replace("\r\n", "\n")),
        "utf8_bytes_without_linebreaks": len(without_linebreaks.encode("utf-8")),
    }


def parse_document(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    meta = {}
    for key in ("run_id", "data_package_id", "data_package_version", "strategy"):
        match = re.search(rf"^- {key}:\s*`?([^`\n]+)`?\s*$", text, flags=re.MULTILINE)
        if match:
            meta[key] = match.group(1).strip()

    sections = re.split(r"^## Q([1-4])\s*$", text, flags=re.MULTILINE)
    answers: dict[int, dict[str, Any]] = {}
    for index in range(1, len(sections), 2):
        q = int(sections[index])
        body = sections[index + 1]
        answer_match = re.search(
            r"### 답변\s*\n(.*?)(?=\n### 근거\s*$)", body, flags=re.DOTALL | re.MULTILINE
        )
        fact_match = re.search(r"^- FACT:\s*(.*)$", body, flags=re.MULTILINE)
        research_match = re.search(r"^- RESEARCH:\s*(.*)$", body, flags=re.MULTILINE)
        if not answer_match:
            answers[q] = {"answer": "", "fact_ids": [], "research_ids": []}
            continue
        answer = answer_match.group(1).strip()
        facts = re.findall(r"F\d{2}", fact_match.group(1) if fact_match else "")
        research = re.findall(r"R\d{2}", research_match.group(1) if research_match else "")
        answers[q] = {"answer": answer, "fact_ids": facts, "research_ids": research}
    return {"meta": meta, "answers": answers, "raw": text}


def validate_one(path: Path, facts: dict[str, Any], research: dict[str, Any]) -> dict[str, Any]:
    doc = parse_document(path)
    errors: list[str] = []
    warnings: list[str] = []
    meta = doc["meta"]
    if meta.get("run_id") != RUN_ID:
        errors.append("run_id mismatch")
    if meta.get("data_package_id") != DATA_PACKAGE_ID:
        errors.append("data_package_id mismatch")
    if meta.get("data_package_version") != DATA_PACKAGE_VERSION:
        errors.append("data_package_version mismatch")
    if set(doc["answers"]) != {1, 2, 3, 4}:
        errors.append("questions must appear exactly once: Q1-Q4")

    question_results = {}
    used_fact_ids: list[str] = []
    for q in range(1, 5):
        item = doc["answers"].get(q, {"answer": "", "fact_ids": [], "research_ids": []})
        answer = item["answer"]
        counts = count_text(answer)
        q_errors: list[str] = []
        q_warnings: list[str] = []
        minimum, maximum = QUESTION_LIMITS[q]
        primary = counts["with_spaces_without_linebreaks"]
        if minimum is not None and primary < minimum:
            q_errors.append(f"under minimum proxy: {primary}/{minimum}")
        if primary > maximum:
            q_errors.append(f"over maximum proxy: {primary}/{maximum}")
        if minimum is not None and counts["without_spaces"] < minimum:
            q_errors.append(
                f"WITHOUT_SPACES would be under minimum: {counts['without_spaces']}/{minimum}"
            )
        for label, pattern in PII_PATTERNS.items():
            if pattern.search(answer):
                q_errors.append(f"blind-recruitment risk: {label}")
        if q <= 3 and not item["fact_ids"]:
            q_errors.append("personal claim without FACT ID")
        if q in (1, 3, 4) and not item["research_ids"]:
            q_errors.append("organization/job/research claim without RESEARCH ID")
        for fact_id in item["fact_ids"]:
            entry = facts.get(fact_id)
            if not entry:
                q_errors.append(f"unknown FACT ID: {fact_id}")
            elif entry.get("status") != "CONFIRMED":
                q_errors.append(f"non-confirmed FACT ID: {fact_id}")
        for research_id in item["research_ids"]:
            entry = research.get(research_id)
            if not entry:
                q_errors.append(f"unknown RESEARCH ID: {research_id}")
            elif entry.get("status") != "CONFIRMED_WITHIN_FROZEN":
                q_errors.append(f"unusable RESEARCH ID: {research_id}")
        used_fact_ids.extend(item["fact_ids"])
        question_results[f"q{q}"] = {
            "counts": counts,
            "fact_ids": item["fact_ids"],
            "research_ids": item["research_ids"],
            "errors": q_errors,
            "warnings": q_warnings,
        }
        errors.extend(f"Q{q}: {message}" for message in q_errors)
        warnings.extend(f"Q{q}: {message}" for message in q_warnings)

    duplicates = sorted({fact_id for fact_id in used_fact_ids if used_fact_ids.count(fact_id) > 1})
    if duplicates:
        warnings.append("reused FACT IDs: " + ", ".join(duplicates))
    answer_hash = hashlib.sha256(
        "\n".join(doc["answers"].get(q, {}).get("answer", "") for q in range(1, 5)).encode("utf-8")
    ).hexdigest()
    return {
        "candidate_file": path.name,
        "strategy": meta.get("strategy"),
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "answer_sha256": answer_hash,
        "questions": question_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--stage", choices=("candidates", "synthesis", "final"), default="candidates")
    args = parser.parse_args()
    root = args.root.resolve()
    facts = load_json(root / "frozen" / "fact_registry.json")
    research = load_json(root / "frozen" / "research_registry.json")
    fact_map = {entry["id"]: entry for entry in facts["facts"]}
    research_map = {entry["id"]: entry for entry in research["research"]}
    if args.stage in {"synthesis", "final"}:
        if args.stage == "synthesis":
            source = root / "synthesis" / "version_S.md"
            output = root / "synthesis" / "validation.json"
        else:
            source = root / "final" / "submission_traceable.md"
            output = root / "final" / "submission_counts.json"
        result = validate_one(source, fact_map, research_map)
        payload = {
            "run_id": RUN_ID,
            "data_package_id": DATA_PACKAGE_ID,
            "data_package_version": DATA_PACKAGE_VERSION,
            "stage": args.stage,
            "count_mode": "UNVERIFIED",
            "status": result["status"],
            "errors": list(result["errors"]),
            "warnings": list(result["warnings"]),
            "questions": result["questions"],
        }
        if args.stage == "final":
            submission = (root / "final" / "submission.md").read_text(encoding="utf-8")
            parsed = parse_document(source)
            missing = [q for q in range(1, 5) if parsed["answers"][q]["answer"] not in submission]
            if missing:
                payload["errors"].append(
                    "submission.md does not contain exact traceable answers: " + ", ".join(map(str, missing))
                )
                payload["status"] = "FAIL"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": payload["status"], "stage": args.stage}, ensure_ascii=False))
        return 0 if payload["status"] == "PASS" else 1

    files = sorted((root / "candidates").glob("candidate_?.md"))
    results = [validate_one(path, fact_map, research_map) for path in files]
    hashes = [result["answer_sha256"] for result in results]
    duplicate_candidates = sorted(
        result["candidate_file"] for result in results if hashes.count(result["answer_sha256"]) > 1
    )
    overall_errors = []
    if len(files) != 4:
        overall_errors.append(f"expected 4 candidates, found {len(files)}")
    if duplicate_candidates:
        overall_errors.append("duplicate candidates: " + ", ".join(duplicate_candidates))
    payload = {
        "run_id": RUN_ID,
        "data_package_id": DATA_PACKAGE_ID,
        "data_package_version": DATA_PACKAGE_VERSION,
        "count_mode": "UNVERIFIED",
        "count_policy": "Proxy enforcement uses WITH_SPACES_WITHOUT_LINEBREAKS; all modes are reported.",
        "status": "PASS" if not overall_errors and all(r["status"] == "PASS" for r in results) else "FAIL",
        "overall_errors": overall_errors,
        "duplicate_candidates": duplicate_candidates,
        "candidates": results,
    }
    output = root / "validation" / "candidate_validation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# 후보 결정론적 검증",
        "",
        f"- status: `{payload['status']}`",
        f"- data_package_id: `{DATA_PACKAGE_ID}`",
        "- count_mode: `UNVERIFIED`",
        "- 글자 수 판정: 줄바꿈 제외·공백 포함 수를 보수적 대리값으로 사용하고 다른 모드도 병기",
        "",
        "| 후보 | 상태 | 오류 | 경고 |",
        "|---|---|---:|---:|",
    ]
    for result in results:
        lines.append(
            f"| {result['candidate_file']} | {result['status']} | {len(result['errors'])} | {len(result['warnings'])} |"
        )
    lines.extend(["", "상세 결과는 `candidate_validation.json`에 기록했다."])
    (root / "validation" / "candidate_validation.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    anonymization = load_json(root / "validation" / "anonymization_map.json")
    anon_by_file = {
        entry["candidate_file"]: entry["anonymous_id"] for entry in anonymization["mapping"]
    }
    blind_candidates = []
    for path in files:
        parsed = parse_document(path)
        blind_candidates.append(
            {
                "candidate_id": anon_by_file[path.name],
                "answers": [
                    {
                        "question_index": q,
                        "answer": parsed["answers"][q]["answer"],
                        "fact_ids": parsed["answers"][q]["fact_ids"],
                        "research_ids": parsed["answers"][q]["research_ids"],
                    }
                    for q in range(1, 5)
                ],
            }
        )
    blind_payload = {
        "run_id": RUN_ID,
        "data_package_id": DATA_PACKAGE_ID,
        "data_package_version": DATA_PACKAGE_VERSION,
        "candidate_count": len(blind_candidates),
        "candidates": blind_candidates,
    }
    (root / "validation" / "blind_candidates.json").write_text(
        json.dumps(blind_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": payload["status"], "candidates": len(results)}, ensure_ascii=False))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
