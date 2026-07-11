from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def main() -> None:
    worksheet_path = Path(sys.argv[1])
    revisions_path = Path(sys.argv[2])
    revisions = json.loads(revisions_path.read_text(encoding="utf-8"))
    text = worksheet_path.read_text(encoding="utf-8")

    for seg_id, revision in revisions.items():
        pattern = re.compile(
            rf"(<!-- SEG {re.escape(seg_id)} prose -->\n원문: .*?\n(?:힌트: .*?\n)?)(윤문: ).*?\n(규칙: ).*?(?=\n\n<!--|\Z)",
            re.DOTALL,
        )
        replacement = (
            rf"\g<1>\g<2>{revision['text']}\n\g<3>{revision['rules']}"
        )
        text, count = pattern.subn(replacement, text, count=1)
        if count != 1:
            raise RuntimeError(f"SEG {seg_id}를 정확히 한 번 찾지 못했습니다: {count}")

    worksheet_path.write_text(text, encoding="utf-8")
    print(f"filled={len(revisions)}")


if __name__ == "__main__":
    main()
