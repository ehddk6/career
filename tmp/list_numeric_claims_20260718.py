from __future__ import annotations

import json
import re
from pathlib import Path

from docx import Document


ROOT = Path(__file__).resolve().parents[1]
ledger_path = ROOT / "career_runs/kinfa-2026-youth-intern-20260717/experience_ledger.json"
data = json.loads(ledger_path.read_text(encoding="utf-8"))
docs: dict[str, Document] = {}
pattern = re.compile(r"(?<![A-Za-z])(?:\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?:\s*[만천백십]?원|%|건|명|주|일|페이지|년|개월|세)?")
ignore = {str(n) for n in range(19, 30)}

for experience in data.get("experiences", []):
    for claim in experience.get("claims", []):
        if claim.get("status") != "needs_verification":
            continue
        source = (claim.get("evidence") or [{}])[0]
        source_path = source.get("source_path", "")
        paragraph_index = source.get("paragraph_index")
        text = claim.get("normalized_value", "")
        numbers = [item for item in pattern.findall(text) if item not in ignore]
        if not numbers:
            continue
        context = ""
        try:
            document = docs.setdefault(source_path, Document(str(ROOT / source_path)))
            context = " ".join(document.paragraphs[int(paragraph_index)].text.split())
        except Exception:
            context = text
        print("|".join([
            experience.get("experience_id", ""),
            experience.get("title", ""),
            claim.get("claim_id", ""),
            ", ".join(numbers),
            context[:280],
        ]))
