import csv
import json
from pathlib import Path

from career_pipeline.__main__ import main


def proposed(path: Path) -> None:
    path.write_text(json.dumps({"schema_version": 1, "generated_at": "2026-07-10", "workspace_root": "C:/career", "experiences": [{"experience_id": "exp_1", "title": "경험", "organization_alias": "", "period": None, "role": "역할", "situation": "상황", "actions": ["확인"], "outcomes": ["개선"], "competencies": [], "claims": [{"field": "case_count", "normalized_value": "20건", "status": "proposed", "evidence": [{"source_path": "career.txt", "paragraph_index": 0, "source_sha256": "a" * 64, "excerpt_sha256": "b" * 64}]}], "status": "proposed", "confirmed_at": None}]}, ensure_ascii=False), encoding="utf-8")


def test_profile_confirm_requires_claim_confirmation(tmp_path: Path):
    proposal = tmp_path / "proposed.json"
    proposed(proposal)
    decisions = tmp_path / "decisions.csv"
    decisions.write_text("experience_id,decision,claims_confirmed\nexp_1,confirmed,no\n", encoding="utf-8")
    output = tmp_path / "confirmed.json"

    assert main(["profile", "confirm", "--proposed", str(proposal), "--decisions", str(decisions), "--output", str(output)]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["experiences"][0]["status"] == "proposed"


def test_profile_confirm_promotes_explicitly_confirmed_experience(tmp_path: Path):
    proposal = tmp_path / "proposed.json"
    proposed(proposal)
    decisions = tmp_path / "decisions.csv"
    decisions.write_text("experience_id,decision,claims_confirmed\nexp_1,confirmed,yes\n", encoding="utf-8")
    output = tmp_path / "confirmed.json"

    assert main(["profile", "confirm", "--proposed", str(proposal), "--decisions", str(decisions), "--output", str(output)]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["experiences"][0]["status"] == "confirmed"
    assert payload["experiences"][0]["claims"][0]["status"] == "confirmed"
