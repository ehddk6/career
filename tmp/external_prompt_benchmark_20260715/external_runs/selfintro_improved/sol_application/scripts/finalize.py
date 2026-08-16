from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def parse_sections(text: str) -> list[dict[str, str]]:
    parts = re.split(r"^## Q([1-4])\s*$", text, flags=re.MULTILINE)
    sections = []
    for index in range(1, len(parts), 2):
        q = int(parts[index])
        body = parts[index + 1]
        prompt = re.search(
            r"### 문항\s*\n(.*?)(?=\n### 답변\s*$)", body, flags=re.DOTALL | re.MULTILINE
        )
        answer = re.search(
            r"### 답변\s*\n(.*?)(?=\n### 근거\s*$)", body, flags=re.DOTALL | re.MULTILINE
        )
        grounds = re.search(r"### 근거\s*\n(.*)$", body, flags=re.DOTALL | re.MULTILINE)
        if not prompt or not answer or not grounds:
            raise ValueError(f"cannot parse Q{q}")
        sections.append(
            {
                "question_index": q,
                "prompt": prompt.group(1).strip(),
                "answer": answer.group(1).strip(),
                "grounds": grounds.group(1).strip(),
            }
        )
    if [section["question_index"] for section in sections] != [1, 2, 3, 4]:
        raise ValueError("Q1-Q4 required")
    return sections


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    source = root / "synthesis" / "version_S.md"
    text = source.read_text(encoding="utf-8")
    sections = parse_sections(text)
    final_dir = root / "final"
    final_dir.mkdir(parents=True, exist_ok=True)

    traceable = text.replace("# VERSION S", "# 최종 제출본 추적본", 1).replace(
        "- strategy: `SYNTHESIS`", "- strategy: `FINAL_SELECTED`", 1
    )
    (final_dir / "submission_traceable.md").write_text(traceable, encoding="utf-8")

    submission = ["# 자기소개서", ""]
    for section in sections:
        submission.extend(
            [
                f"## {section['question_index']}. {section['prompt']}",
                "",
                section["answer"],
                "",
            ]
        )
    (final_dir / "submission.md").write_text("\n".join(submission).rstrip() + "\n", encoding="utf-8")

    selected = {
        "run_id": "SOL-20260715-1537",
        "data_package_id": "SOL-DATA-EXT-001",
        "data_package_version": "1.0",
        "selected_version": "Y",
        "selected_source": "synthesis/version_S.md",
        "baseline_winner": "R8",
        "version_z_created": False,
        "comparison": "comparison/final_comparison.json",
    }
    (final_dir / "selected_source.json").write_text(
        json.dumps(selected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

