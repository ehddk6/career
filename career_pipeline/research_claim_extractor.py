"""Normalize externally extracted company claims without inventing facts.

This is an ingestion boundary, not a semantic fact generator. A browser/model
may propose claim rows, but this module derives source authority metadata,
rejects malformed rows, and then lets the coverage/conflict gates decide use.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Mapping

from .research_source_registry import classify_source
from .research_workspace import (
    CLAIM_FILE, PLAN_FILE, SOURCE_FILE, enrich_claim_metadata,
    initialize_research_workspace,
)

_REQUIRED = ("claim_id", "claim", "source_url", "evidence_excerpt", "claim_type")


def normalize_research_claim(
    raw: Mapping[str, Any],
    *,
    registry: Mapping[str, Any],
    checked_at: str | None = None,
) -> dict[str, Any]:
    missing = [key for key in _REQUIRED if not str(raw.get(key, "")).strip()]
    if missing:
        raise ValueError("research claim missing: " + ", ".join(missing))
    source_type = str(raw.get("source_type", "unknown")).strip().lower() or "unknown"
    source = classify_source(
        str(raw["source_url"]),
        source_type=source_type,
        registry=registry,
        publisher=str(raw.get("publisher", "")),
    )
    item = dict(raw)
    item.update(
        {
            "source_type": source_type,
            "source_tier": source["source_tier"],
            "publisher": source["publisher"],
            "checked_at": str(raw.get("checked_at", "")).strip()
            or checked_at
            or datetime.now().astimezone().date().isoformat(),
            "support_strength": str(raw.get("support_strength", "")).strip()
            or "direct",
        }
    )
    requested_status = str(raw.get("verification_status", "confirmed")).strip() or "confirmed"
    if requested_status in {"confirmed", "verified"} and not source["submission_authority"]:
        item["verification_status"] = "contextual"
        item["authority_note"] = (
            "source is useful for context but is not submission factual authority"
        )
    else:
        item["verification_status"] = requested_status
    return item


def ingest_claim_file(run_dir: Path, input_path: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    initialize_research_workspace(run_dir)
    registry = json.loads((run_dir / SOURCE_FILE).read_text(encoding="utf-8"))
    plan = json.loads((run_dir / PLAN_FILE).read_text(encoding="utf-8"))
    incoming = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(incoming, list):
        raise ValueError("input claims must be an array")
    normalized = [
        normalize_research_claim(item, registry=registry)
        for item in incoming
        if isinstance(item, Mapping)
    ]
    existing = json.loads((run_dir / CLAIM_FILE).read_text(encoding="utf-8"))
    if not isinstance(existing, list):
        raise ValueError(f"{CLAIM_FILE} must be an array")
    by_id = {
        str(item.get("claim_id", "")): dict(item)
        for item in existing
        if isinstance(item, Mapping) and str(item.get("claim_id", ""))
    }
    for item in normalized:
        claim_id = str(item["claim_id"])
        if claim_id in by_id and by_id[claim_id].get("claim") != item.get("claim"):
            raise ValueError(f"claim_id already exists with different text: {claim_id}")
        by_id[claim_id] = item
    merged = enrich_claim_metadata(list(by_id.values()), plan)
    (run_dir / CLAIM_FILE).write_text(
        json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return initialize_research_workspace(run_dir)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest extracted company-research claims")
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = ingest_claim_file(args.run, args.input)
    print(args.run.resolve() / CLAIM_FILE)
    print(args.run.resolve() / "04_근거커버리지.json")
    return 0 if report["coverage"].get("stop_research") else 3


if __name__ == "__main__":
    raise SystemExit(main())
