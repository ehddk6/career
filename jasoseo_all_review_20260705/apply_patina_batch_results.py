from __future__ import annotations

import json
from pathlib import Path

import run_full_final_gate as gate


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "final_gate_20260705"
BATCH_DIR = OUT_DIR / "patina_batch_all"


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: list[dict]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    quality_rows = load(gate.QUALITY_REPORT)
    copy_reports = load(gate.COPYEDITOR_REPORT)
    patina_reports = load(gate.PATINA_REPORT)
    report_by_file = {row["file"]: row for row in patina_reports}
    final_name_to_file = {
        Path(row["final_file"]).name: row["file"]
        for row in quality_rows
        if row.get("final_file")
    }
    applied = 0
    failed = 0
    for result_path in sorted(BATCH_DIR.glob("*.md")):
        source_file = final_name_to_file.get(result_path.name)
        if source_file is None or source_file not in report_by_file:
            continue
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        overall = payload.get("overall")
        try:
            score = int(round(float(overall)))
        except (TypeError, ValueError):
            continue
        passed = score <= 30
        report = report_by_file[source_file]
        for item in report["items"]:
            item["patina_attempted"] = True
            item["patina_applied"] = False
            item["score_status"] = "scored_document_batch"
            item["selected_ai_score"] = score
            item["ai_score_gate"] = "passed" if passed else "blocked"
            item["patina_status"] = "document_score_only"
            item["message"] = (
                "문서 단위 Patina batch 점수 반영"
                if passed
                else "문서 단위 Patina batch 점수 기준 초과; 제한 해제 후 문항별 재점검 필요"
            )
        if passed:
            applied += 1
        else:
            failed += 1
    save(gate.PATINA_REPORT, patina_reports)
    gate.write_summary(copy_reports, patina_reports, quality_rows)
    print(
        json.dumps(
            {
                "batch_results": len(list(BATCH_DIR.glob("*.md"))),
                "applied_passed_documents": applied,
                "blocked_documents": failed,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
