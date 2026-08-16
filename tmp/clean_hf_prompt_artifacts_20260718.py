from __future__ import annotations

from pathlib import Path


run = Path(__file__).resolve().parents[1] / "career_runs/hf-2026-h2-intern-official-20260717-20260717-121306-540610"
for name in ("run.json", "00_채용공고분석.json", "00_채용공고분석.md", "05_문항전략.json", "05_문항전략.md"):
    path = run / name
    if path.exists():
        text = path.read_text(encoding="utf-8")
        text = text.replace(" (, 공백 제외)", "").replace("(, 공백 제외)", "")
        path.write_text(text, encoding="utf-8")
print("cleaned")
