from __future__ import annotations

import json
from pathlib import Path


BASE = Path(
    r"C:\Users\ehddk\OneDrive\문서\취업\jasoseo_all_review_20260705\final_gate_20260705"
)
OUT = BASE / "patina_over_30_documents.tsv"


def main() -> int:
    data = json.loads((BASE / "09_patina_report_all_20260705.json").read_text(encoding="utf-8"))
    over: list[tuple[int, str, int]] = []
    for report in data:
        scores = [
            item["selected_ai_score"]
            for item in report["items"]
            if item.get("score_status") == "scored_document_batch"
            and item.get("selected_ai_score") is not None
        ]
        if scores and max(scores) > 30:
            over.append((max(scores), report["file"], report.get("question_count", 0)))
    over.sort(reverse=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    lines = ["score\tquestion_count\tfile"]
    for score, file, question_count in over:
        lines.append(f"{score}\t{question_count}\t{file}")
    lines.append(f"# total_over_30: {len(over)}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # Strip accidental UTF-8 BOM from previous PowerShell redirects.
    if OUT.exists():
        data_bytes = OUT.read_bytes()
        if data_bytes.startswith(b"\xef\xbb\xbf"):
            OUT.write_bytes(data_bytes[3:])
    print(f"wrote {OUT} ({len(over)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
