from __future__ import annotations

import argparse
import json
from pathlib import Path

from validate import parse_document


def pack(path: Path, label: str) -> dict:
    parsed = parse_document(path)
    return {
        "label": label,
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    payload = {
        "run_id": "SOL-20260715-1537",
        "data_package_id": "SOL-DATA-EXT-001",
        "data_package_version": "1.0",
        "count_mode": "UNVERIFIED",
        "constraints": {
            "q1": "400-600 characters",
            "q2": "400-600 characters",
            "q3": "400-600 characters",
            "q4": "maximum 1500 characters",
            "blind_recruitment": True,
        },
        "remaining_risks": [
            "F01의 실제 비교 기준·결과 차이는 확인되지 않았다.",
            "F08의 구체 개선안·실행 성과는 확인되지 않았다.",
            "Q3의 체크·인계 절차는 지원자 계획이지 기관 내부 절차가 아니다.",
            "Q4의 세부 지원수단은 지원자 제안이며 현행 제도 최신성은 재확인하지 않았다.",
        ],
        "versions": [
            pack(root / "candidates" / "candidate_B.md", "X"),
            pack(root / "synthesis" / "version_S.md", "Y"),
        ],
    }
    output = root / "comparison" / "blind_comparison.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
