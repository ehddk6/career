import json
from pathlib import Path
from types import SimpleNamespace

from career_pipeline.writing_guidance import attach_writing_guidance
from career_pipeline.youtube_patterns import (
    PATTERN_PACKET_VERSION,
    build_pattern_packet,
    phrase_overlap_report,
    source_quality,
)


def _write_source(root: Path) -> Path:
    source = root / "자료조사" / "자소서_유튜브_프레임분석_2026-07-03"
    source.mkdir(parents=True)
    (source / "run_summary.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-07-03 08:12:39",
                "video_count": 199,
                "frame_count": 5977,
                "nonempty_ocr_frame_count": 5654,
                "usable_frame_count": 5374,
                "company_counts": {"A": 10, "B": 4},
            }
        ),
        encoding="utf-8",
    )
    (source / "01_자소서_작성원칙_요약.md").write_text(
        "# 작성 원칙\n\n- 구조와 판단 기준만 사용합니다.\n", encoding="utf-8"
    )
    return source


def test_pattern_packet_is_strategy_only_and_uses_conservative_quality(tmp_path: Path):
    source = _write_source(tmp_path)

    quality = source_quality(source)
    assert quality["video_count"] == 199
    assert quality["distinct_company_labels"] == 2
    assert quality["ocr_confidence"] == "bounded_not_absolute"
    assert quality["manual_review_required"] is True

    packet = build_pattern_packet(source, target="기관 직무")
    assert packet["packet_version"] == PATTERN_PACKET_VERSION
    assert packet["use_policy"] == "strategy_only_not_factual_evidence"
    assert "company_facts" in packet["prohibited_uses"]
    assert any(item["id"] == "ANTI_TEMPLATE_REUSE" for item in packet["patterns"])
    assert packet["manual_review_gate"]["automatic_action"].startswith("hold_")


def test_attach_writes_packet_and_application_log_without_fact_refs(tmp_path: Path):
    _write_source(tmp_path)
    run_dir = tmp_path / "run"
    state: dict = {}

    guidance = attach_writing_guidance(tmp_path, run_dir, state, target="기관 직무")

    packet_path = run_dir / "06_유튜브_디자인패턴_패킷.json"
    log_path = run_dir / "07_유튜브_패턴적용로그.json"
    assert guidance["pattern_packet"]["version"] == PATTERN_PACKET_VERSION
    assert guidance["pattern_packet"]["manual_review_required"] is True
    assert packet_path.exists()
    assert log_path.exists()
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    log = json.loads(log_path.read_text(encoding="utf-8"))
    assert packet["use_policy"] == "strategy_only_not_factual_evidence"
    assert log["status"] == "planned_not_yet_applied"
    assert [entry["stage"] for entry in log["entries"]] == [
        "prepare",
        "question_classification",
        "candidate_generation",
        "candidate_selection",
        "humanization",
        "final_audit",
    ]
    rendered = (run_dir / "05_작성가이드_유튜브프레임.md").read_text(encoding="utf-8")
    assert "유튜브 디자인 패턴 패킷" in rendered
    assert "회사 사실·개인 경험·문장을 추가하지 않습니다" in rendered


def test_phrase_overlap_is_a_manual_review_warning_not_a_fact_ref(tmp_path: Path):
    source = _write_source(tmp_path)
    (source / "05_문장_근거색인.csv").write_text(
        "score,count,line,source_types,question_types,company_groups,examples\n"
        "10,4,기준을 먼저 확인하고 예외를 분류했습니다,text,직무역량,공기업,\n",
        encoding="utf-8",
    )
    report = phrase_overlap_report(
        [
            SimpleNamespace(
                question_index=1,
                answer="자료를 받으면 기준을 먼저 확인하고 예외를 분류했습니다.",
            )
        ],
        source,
    )
    assert report["status"] == "available"
    assert report["manual_review_required"] is True
    assert report["matches"][0]["action"] == "manual_review_warning"
    assert report["use_policy"] == "strategy_only_not_factual_evidence"
