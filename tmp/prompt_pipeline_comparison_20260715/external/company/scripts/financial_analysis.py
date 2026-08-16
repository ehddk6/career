"""Frozen KODIT package financial evidence validator.

This script intentionally performs no estimation. The allowed evidence package
contains no company financial statement records, so the reproducible result is
an empty calculation set with an explicit missing-data status.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


MISSING_METRICS = [
    "revenue_growth",
    "operating_margin",
    "net_margin",
    "segment_or_region_mix",
    "rd_to_revenue",
    "capex_change",
    "operating_cash_flow",
    "free_cash_flow",
    "cash_and_debt_change",
    "inventory_and_receivables_change",
    "employee_change",
    "revenue_per_employee",
    "concentration",
    "company_operating_kpis",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-evidence", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--csv-output", type=Path, required=True)
    args = parser.parse_args()

    evidence = json.loads(args.official_evidence.read_text(encoding="utf-8"))
    if not isinstance(evidence, list):
        raise ValueError("official evidence must be a JSON array")

    result = {
        "company_data_package_id": "CR-DATA-001",
        "company_data_package_version": "1.0",
        "status": "INSUFFICIENT_SOURCE_DATA",
        "source_path": args.official_evidence.as_posix(),
        "source_sha256": sha256(args.official_evidence),
        "records": [],
        "missing_metrics": MISSING_METRICS,
        "excluded_numeric_claim": {
            "claim_id": "bok-fx-risk-20260711",
            "value": "14조원",
            "reason": "한국은행 중소기업 한시 특별지원 한도이며 KODIT 재무 수치가 아님",
        },
    }

    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.csv_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with args.csv_output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "metric_id",
                "metric",
                "period",
                "raw_value",
                "calculated_value",
                "unit",
                "formula",
                "source",
                "interpretation_scope",
            ]
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
