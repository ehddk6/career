import json
from pathlib import Path

from career_pipeline.golden_path import GoldenPathServices, advance_golden_path


def _base_run(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    (run / "run.json").write_text(
        json.dumps({"quality_mode": "v2", "strict_quality": True, "root": str(tmp_path), "questions": []}),
        encoding="utf-8",
    )
    for name in (
        "00_채용공고분석.json",
        "02_확정경험원장.json",
        "03_경험직무매칭.json",
        "04_리서치계획.json",
        "04_리서치출처.json",
        "04_공식근거.json",
        "04_근거충돌.json",
        "04_근거커버리지.json",
        "04_리서치실행.json",
    ):
        (run / name).write_text("{}", encoding="utf-8")
    return run


def _services(*, research_ready=True, pack_issues=None, finalize_changes=False, audit_score=95):
    calls = []

    def research(run):
        calls.append("research")
        return {"ready": research_ready, "reasons": [] if research_ready else ["x"], "next_queries": ["q"]}

    def strategy(run):
        calls.append("strategy")
        return "strategy-fingerprint"

    def write(run, config):
        calls.append("write")
        (run / "draft.json").write_text('[{"question_index":1,"answer":"A"}]', encoding="utf-8")
        return {"deterministic_validation": {"status": "passed"}, "semantic_validation": {"status": "passed"}}

    def gate(run, draft):
        calls.append(("gate", draft.name))
        return list(pack_issues or [])

    def finalize(run, config):
        calls.append("finalize")
        value = (run / "draft.json").read_text(encoding="utf-8")
        if finalize_changes:
            value = '[{"question_index":1,"answer":"B"}]'
        (run / "draft_final.json").write_text(value, encoding="utf-8")
        (run / "12_최종산출물.json").write_text("{}", encoding="utf-8")
        state = json.loads((run / "run.json").read_text(encoding="utf-8"))
        state["status"] = "complete"
        state["final_artifact"] = {"answer_json_path": "draft_final.json"}
        (run / "run.json").write_text(json.dumps(state), encoding="utf-8")
        return {"status": "complete"}

    def resolve(run):
        return run / "draft_final.json"

    def compile_interview(run):
        calls.append("interview")
        (run / "08_면접지능설계.json").write_text("{}", encoding="utf-8")
        (run / "08_면접질문은행.md").write_text("bank", encoding="utf-8")
        return {"architecture": "structured_adaptive_claim_defense_v1"}

    def audit(run):
        calls.append("audit")
        payload = {"quality_gate": "pass", "internal_validation_score": audit_score, "issues": []}
        (run / "11_최종품질감사.json").write_text(json.dumps(payload), encoding="utf-8")
        (run / "11_최종품질감사.md").write_text("audit", encoding="utf-8")
        return payload

    return GoldenPathServices(research, strategy, write, gate, finalize, resolve, compile_interview, audit), calls


def test_waits_for_research_before_writer(tmp_path):
    run = _base_run(tmp_path)
    services, calls = _services(research_ready=False)
    result = advance_golden_path(run, services=services)
    assert result["status"] == "waiting_for_research"
    assert "write" not in calls


def test_waits_for_legacy_pack_before_finalize(tmp_path):
    run = _base_run(tmp_path)
    services, calls = _services()
    result = advance_golden_path(run, services=services)
    assert result["status"] == "waiting_for_interview_pack"
    assert "write" in calls
    assert "finalize" not in calls


def test_strict_legacy_pack_gate_blocks_finalize(tmp_path):
    run = _base_run(tmp_path)
    (run / "08_면접대비팩.md").write_text("pack", encoding="utf-8")
    services, calls = _services(pack_issues=[{"code": "interview_timed_answer_missing"}])
    result = advance_golden_path(run, services=services)
    assert result["status"] == "waiting_for_interview_pack_fix"
    assert "finalize" not in calls


def test_final_draft_change_requires_explicit_pack_refresh(tmp_path):
    run = _base_run(tmp_path)
    (run / "08_면접대비팩.md").write_text("pack", encoding="utf-8")
    services, calls = _services(finalize_changes=True)
    result = advance_golden_path(run, services=services)
    assert result["status"] == "waiting_for_interview_pack_refresh"
    assert "interview" not in calls

    (run / "08_면접대비팩.md").write_text("refreshed pack", encoding="utf-8")
    result = advance_golden_path(run, services=services)
    assert result["status"] == "complete"
    assert calls.count("write") == 1
    assert calls.count("finalize") == 1
    assert "interview" in calls
    assert "audit" in calls


def test_content_addressed_cache_avoids_expensive_reexecution(tmp_path):
    run = _base_run(tmp_path)
    (run / "08_면접대비팩.md").write_text("pack", encoding="utf-8")
    services, calls = _services()
    assert advance_golden_path(run, services=services)["status"] == "complete"
    counts = (calls.count("write"), calls.count("finalize"), calls.count("interview"))
    assert advance_golden_path(run, services=services)["status"] == "complete"
    assert (calls.count("write"), calls.count("finalize"), calls.count("interview")) == counts


def test_authority_change_invalidates_writer_cache(tmp_path):
    run = _base_run(tmp_path)
    (run / "08_면접대비팩.md").write_text("pack", encoding="utf-8")
    services, calls = _services()
    assert advance_golden_path(run, services=services)["status"] == "complete"
    previous = calls.count("write")
    (run / "04_공식근거.json").write_text('{"changed":true}', encoding="utf-8")
    assert advance_golden_path(run, services=services)["status"] == "complete"
    assert calls.count("write") == previous + 1


def test_tampered_interview_plan_is_recompiled(tmp_path):
    run = _base_run(tmp_path)
    (run / "08_면접대비팩.md").write_text("pack", encoding="utf-8")
    services, calls = _services()
    assert advance_golden_path(run, services=services)["status"] == "complete"
    previous = calls.count("interview")
    (run / "08_면접지능설계.json").write_text('{"tampered":true}', encoding="utf-8")
    assert advance_golden_path(run, services=services)["status"] == "complete"
    assert calls.count("interview") == previous + 1


def test_low_audit_score_is_not_complete(tmp_path):
    run = _base_run(tmp_path)
    (run / "08_면접대비팩.md").write_text("pack", encoding="utf-8")
    services, _ = _services(audit_score=89)
    result = advance_golden_path(run, services=services)
    assert result["status"] == "review_required"
