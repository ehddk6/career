from __future__ import annotations

import json
from pathlib import Path


path = Path(__file__).resolve().parents[1] / "career_runs/hf-2026-h2-intern-official-20260717-20260717-121306-540610/draft.json"
rows = json.loads(path.read_text(encoding="utf-8"))
if "고객 안내 문구도 함께 점검하겠습니다." not in rows[1]["answer"]:
    rows[1]["answer"] += " 고객 안내 문구도 함께 점검하겠습니다."
if "공유 후 이해 여부도 다시 확인하겠습니다." not in rows[2]["answer"]:
    rows[2]["answer"] += " 공유 후 이해 여부도 다시 확인하겠습니다."
path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("adjusted")
