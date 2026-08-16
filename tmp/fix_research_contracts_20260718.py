from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

hf_run = ROOT / "career_runs/hf-2026-h2-intern-official-20260717-20260717-121306-540610"
hf_path = hf_run / "04_공식근거.json"
hf = json.loads(hf_path.read_text(encoding="utf-8"))
for claim in hf:
    if claim["claim_id"] == "hf-ax-20260717":
        claim["claim_type"] = "program_or_service"
        claim["application_use"] = "문항 2의 현장 학습 목표와 문항 4의 정확하고 쉬운 고객 안내에 보조적으로 사용"
    if claim["claim_id"] == "hf-intern-duty-20260717":
        claim["application_use"] = "문항 1의 직무능력과 문항 2의 인턴 목표, 면접 직무 방어에 사용"
hf_path.write_text(json.dumps(hf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
hf_md = hf_run / "04_기업직무조사.md"
text = hf_md.read_text(encoding="utf-8")
text = text.replace(
    "문항 2: `hf-purpose-20260717`과 공적 지원 증빙 대조 사건",
    "문항 2: `hf-purpose-20260717`, `hf-intern-duty-20260717`과 공적 지원 증빙 대조 사건",
)
hf_md.write_text(text, encoding="utf-8")

y_run = ROOT / "career_runs/yongsan-2026-3-office8-official-20260717-20260717-121709-623609"
y_path = y_run / "04_공식근거.json"
y = json.loads(y_path.read_text(encoding="utf-8"))
for claim in y:
    if claim["claim_id"] == "yongsan-ethics-20260717":
        claim["claim_type"] = "organization_role"
    if claim["claim_id"] != "yongsan-selection-criteria-20260717":
        claim["application_use"] = "문항 1의 자유서술형 자기소개서와 면접에서 지원동기·행정역량·고객서비스·협업·입사 후 기여를 연결하는 데 사용"
y_path.write_text(json.dumps(y, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
y_md = y_run / "04_기업직무조사.md"
text = y_md.read_text(encoding="utf-8")
text = text.replace(
    "문항 1 지원동기: `yongsan-role-20260717`",
    "문항 1 지원동기: `yongsan-role-20260717`, `yongsan-ethics-20260717`",
)
y_md.write_text(text, encoding="utf-8")

print("research contracts fixed")
