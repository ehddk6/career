from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


DATA_PACKAGE_ID = "SOL-DATA-EXT-001"
DATA_PACKAGE_VERSION = "1.0"
CORE_KEYS = ("question_fidelity", "fact_accuracy", "job_relevance")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    validation = load_json(root / "validation" / "candidate_validation.json")
    valid_ids = {entry["candidate_file"] for entry in validation["candidates"] if entry["status"] == "PASS"}
    anon_map = load_json(root / "validation" / "anonymization_map.json")
    file_by_anon = {entry["anonymous_id"]: entry["candidate_file"] for entry in anon_map["mapping"]}

    evaluations: dict[str, list[dict[str, Any]]] = {}
    package_errors = []
    for path in sorted((root / "judges").glob("*.json")):
        payload = load_json(path)
        if payload.get("data_package_id") != DATA_PACKAGE_ID or payload.get("data_package_version") != DATA_PACKAGE_VERSION:
            package_errors.append(f"{path.name}: data package mismatch")
            continue
        for evaluation in payload.get("evaluations", []):
            evaluations.setdefault(evaluation["candidate_id"], []).append(evaluation)

    ranking = []
    for anon_id, items in evaluations.items():
        candidate_file = file_by_anon.get(anon_id)
        deterministic_fail = candidate_file not in valid_ids
        semantic_fail = any(item.get("hard_fail_status") == "HARD_FAIL" for item in items)
        review_required = sorted({reason for item in items for reason in item.get("review_required", [])})
        totals = [item["total"] for item in items]
        core = [sum(item["scores"][key] for key in CORE_KEYS) for item in items]
        ranking.append(
            {
                "candidate_id": anon_id,
                "candidate_file": candidate_file,
                "disqualified": deterministic_fail or semantic_fail,
                "review_required": review_required,
                "median_total": statistics.median(totals) if totals else 0,
                "minimum_total": min(totals) if totals else 0,
                "median_core": statistics.median(core) if core else 0,
                "judge_spread": (max(totals) - min(totals)) if totals else 0,
                "judge_totals": totals,
            }
        )

    ranking.sort(
        key=lambda row: (
            row["disqualified"],
            bool(row["review_required"]),
            -row["median_total"],
            -row["minimum_total"],
            -row["median_core"],
            row["judge_spread"],
            row["candidate_id"],
        )
    )
    eligible = [row for row in ranking if not row["disqualified"]]
    winner = eligible[0] if eligible else None
    runner_up = eligible[1] if len(eligible) > 1 else None

    transferable = []
    for anon_id, items in evaluations.items():
        for item in items:
            for element in item.get("transferable_elements", []):
                key = (
                    anon_id,
                    element.get("question"),
                    element.get("element_type"),
                    element.get("exact_element"),
                )
                transferable.append({"key": key, "judge_mode": item.get("judge_mode"), **element})
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for item in transferable:
        grouped.setdefault(item["key"], []).append(item)
    agreed_transferable = [
        {
            "candidate_id": key[0],
            "question": key[1],
            "element_type": key[2],
            "exact_element": key[3],
            "judge_count": len({item["judge_mode"] for item in items}),
            "reasons": sorted({item.get("reason", "") for item in items if item.get("reason")}),
            "fact_ids": sorted({fact for item in items for fact in item.get("fact_ids", [])}),
        }
        for key, items in grouped.items()
        if len({item["judge_mode"] for item in items}) >= 2
    ]
    agreed_transferable.sort(key=lambda item: (-item["judge_count"], item["candidate_id"], item["question"]))

    payload = {
        "data_package_id": DATA_PACKAGE_ID,
        "data_package_version": DATA_PACKAGE_VERSION,
        "status": "PASS" if winner and not package_errors else "FAIL",
        "package_errors": package_errors,
        "ranking": ranking,
        "winner": winner,
        "runner_up": runner_up,
        "agreed_transferable_elements": agreed_transferable[:8],
    }
    output = root / "synthesis" / "selection.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "winner": winner}, ensure_ascii=False))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

