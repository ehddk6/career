import json
from pathlib import Path

from career_pipeline.strategy_prior import build_strategy_prior, strategy_prior_for_stage


def _base_run(tmp_path: Path) -> tuple[Path, Path]:
    run = tmp_path / "career_runs" / "current"
    run.mkdir(parents=True)
    source = tmp_path / "자료조사" / "자소서_유튜브_프레임분석_2026-08-17"
    source.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({
        "root": str(tmp_path),
        "target": "신용보증기금 체험형 청년인턴",
        "writing_guidance": {"source_dir": source.relative_to(tmp_path).as_posix()},
    }, ensure_ascii=False), encoding="utf-8")
    (run / "02_확정경험원장.json").write_text(json.dumps({"schema_version": 2, "experiences": [{"experience_id": "exp-current"}]}, ensure_ascii=False), encoding="utf-8")
    (run / "03_경험직무매칭.json").write_text('[{"question":{"index":1}}]', encoding="utf-8")
    (run / "04_공식근거.json").write_text('[{"claim_id":"research-1"}]', encoding="utf-8")
    return run, source


def test_strategy_prior_uses_youtube_and_legacy_strategy_without_factual_authority(tmp_path: Path):
    run, source = _base_run(tmp_path)
    (source / "01_자소서_작성원칙_요약.md").write_text("- 성격 선언보다 판단 장면을 먼저 씁니다.\n", encoding="utf-8")
    (source / "04_프레임_근거색인.csv").write_text(
        "video_id,title,score,question_types,company_groups,companies,key_lines\n"
        "K1,신용보증기금 인턴 자기소개서 특강,90,지원동기,보증/기금/HUG,,기관 설명보다 개인 선택 기준을 먼저 둔다\n",
        encoding="utf-8",
    )
    (run / "05_문항전략.md").write_text("# 기존 작성 파이프라인 전략\n- 첫 두 문장 안에 문항에 직접 답합니다.\n", encoding="utf-8")
    packet = build_strategy_prior(run)
    assert packet["current_pipeline"]["confirmed_experience_count"] == 1
    assert packet["youtube"]["target_specific"]["status"] == "matched"
    assert packet["youtube"]["target_specific"]["matches"][0]["video_id"] == "K1"
    assert packet["youtube"]["factual_authority"] is False
    assert packet["legacy_writing_pipeline"]["factual_authority"] is False
    assert packet["authority"]["applicant_facts"] == "02_확정경험원장.json only"


def test_historical_self_intro_is_reused_as_ids_not_raw_prose(tmp_path: Path):
    run, _ = _base_run(tmp_path)
    old = tmp_path / "career_runs" / "old"
    old.mkdir()
    old_answer = "이 문장은 과거 자기소개서 원문이라 새 모델 프롬프트로 전달되면 안 됩니다."
    (old / "draft_final.json").write_text(json.dumps([{
        "question_index": 1,
        "answer": old_answer,
        "experience_refs": [{"experience_id": "exp-old", "claim_ids": ["claim-old"]}],
        "research_refs": [],
    }], ensure_ascii=False), encoding="utf-8")
    packet = build_strategy_prior(run)
    serialized = json.dumps(packet, ensure_ascii=False)
    assert packet["historical_run_usage"]["experience_usage"]["exp-old"] == 1
    assert packet["historical_run_usage"]["claim_usage"]["claim-old"] == 1
    assert packet["historical_run_usage"]["raw_prose_forwarded"] is False
    assert old_answer not in serialized


def test_stage_prior_is_question_scoped(tmp_path: Path):
    run, _ = _base_run(tmp_path)
    (run / "05_문항전략.json").write_text(json.dumps({"questions": [
        {"question_index": 1, "answer_strategy": "개인의 선택 기준을 먼저 제시"},
        {"question_index": 2, "answer_strategy": "갈등 장면을 먼저 제시"},
    ]}, ensure_ascii=False), encoding="utf-8")
    packet = build_strategy_prior(run)
    q1 = strategy_prior_for_stage(packet, "deep_route_plan_q1")
    assert q1["question_index"] == 1
    assert q1["legacy_question_strategy"] == ["개인의 선택 기준을 먼저 제시"]
    assert "갈등 장면" not in json.dumps(q1, ensure_ascii=False)
