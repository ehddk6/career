import json
from pathlib import Path

from career_pipeline.writing_guidance import attach_writing_guidance


def test_target_specific_youtube_strategy_is_attached_without_fact_refs(tmp_path: Path):
    source_dir = tmp_path / "자료조사" / "자소서_유튜브_프레임분석_2026-07-03"
    source_dir.mkdir(parents=True)
    (source_dir / "01_자소서_작성원칙_요약.md").write_text(
        "# 작성 원칙\n\n- 기관별 사례는 구조만 참고합니다.\n", encoding="utf-8"
    )
    (source_dir / "04_프레임_근거색인.csv").write_text(
        "playlist_index,video_id,timestamp,score,title,question_types,company_groups,companies,key_lines,red_lines,highlighted_lines,youtube_url,image_file\n"
        "1,VZBEVdmG23Q,00:12,48,[면쌤특강] 신용보증기금 인턴 자기소개서 특강,지원동기;문제해결,보증/기금/HUG,,경험에서 기관 역할로 연결,,,,https://www.youtube.com/watch?v=VZBEVdmG23Q,\n"
        "3,GENERICBANK,00:12,99,은행 자기소개서 특강,지원동기,보증/기금/HUG,,기관군 공통 사례,,,,https://www.youtube.com/watch?v=GENERICBANK,\n"
        "2,NHVIDEO,00:12,60,농협 자기소개서 특강,지원동기,농협/NH,,농협 사례,,,,https://www.youtube.com/watch?v=NHVIDEO,\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    state: dict = {}

    guidance = attach_writing_guidance(
        tmp_path,
        run_dir,
        state,
        target="신용보증기금 체험형 청년인턴1(보증)",
    )

    assert guidance["target_specific"]["status"] == "matched"
    assert guidance["target_specific"]["video_count"] == 2
    assert guidance["target_specific"]["direct_video_count"] == 1
    assert guidance["target_specific"]["videos"][0]["video_id"] == "VZBEVdmG23Q"
    assert guidance["target_specific"]["use_policy"] == "strategy_only_not_factual_evidence"
    artifact = (run_dir / "05_작성가이드_유튜브프레임.md").read_text(encoding="utf-8")
    assert "지원기관 맞춤 유튜브 전략 (사실 근거 아님)" in artifact
    assert "신용보증기금 인턴 자기소개서 특강" in artifact
    assert "research_refs" in artifact
    assert "experience_refs" in artifact


def test_target_specific_youtube_strategy_is_not_requested_without_target(tmp_path: Path):
    source_dir = tmp_path / "자료조사" / "자소서_유튜브_프레임분석_2026-07-03"
    source_dir.mkdir(parents=True)
    (source_dir / "01_자소서_작성원칙_요약.md").write_text("# 작성 원칙\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    state: dict = {}

    guidance = attach_writing_guidance(tmp_path, run_dir, state)

    assert guidance["target_specific"]["status"] == "not_requested"
    json.dumps(guidance, ensure_ascii=False)
