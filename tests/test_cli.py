from career_pipeline.__main__ import build_parser


def test_parser_exposes_prepare_and_finalize_commands():
    parser = build_parser()
    prepare = parser.parse_args(
        [
            "prepare",
            "--root",
            ".",
            "--target",
            "HUG 금융·기금",
            "--draft",
            "draft.docx",
        ]
    )
    finalize = parser.parse_args(["finalize", "--run", "career_runs/sample"])
    audit = parser.parse_args(["audit", "--run", "career_runs/sample"])
    fallback = parser.parse_args(
        [
            "finalize",
            "--run",
            "career_runs/sample",
            "--patina-backend",
            "codex-cli,openai-http",
            "--patina-max-retries",
            "1",
            "--patina-voice-sample",
            "voice.txt",
        ]
    )

    assert prepare.command == "prepare"
    assert prepare.target == "HUG 금융·기금"
    assert prepare.research_domain == []
    assert finalize.command == "finalize"
    assert finalize.no_patina is False
    assert finalize.patina_timeout_ms == 180000
    assert audit.command == "audit"
    assert audit.run == "career_runs/sample"
    assert finalize.no_copyeditor is False
    assert finalize.copyeditor_timeout_ms == 180000
    assert finalize.postprocess == "auto"
    assert finalize.max_postprocess_calls == 1
    assert finalize.legacy_patina is False
    assert fallback.patina_backend == "codex-cli,openai-http"
    assert fallback.patina_max_retries == 1
    assert fallback.patina_voice_sample == "voice.txt"


def test_parser_exposes_phase2_commands():
    parser = build_parser()
    applicant = parser.parse_args(
        [
            "profile",
            "applicant",
            "--ledger",
            "ledger.json",
            "--profile-id",
            "applicant-1",
            "--output",
            "profile.json",
        ]
    )
    record = parser.parse_args(
        [
            "posting",
            "record",
            "--target",
            "기관 직무",
            "--source",
            "posting.pdf",
            "--official-source",
            "--output",
            "posting-record.json",
        ]
    )
    evaluate = parser.parse_args(
        [
            "eligibility",
            "evaluate",
            "--profile",
            "profile.json",
            "--posting",
            "posting-record.json",
            "--output",
            "decision.json",
        ]
    )

    assert applicant.profile_command == "applicant"
    assert applicant.force is False
    assert applicant.run_dir is None
    assert record.posting_command == "record"
    assert record.force is False
    assert record.run_dir is None
    assert evaluate.eligibility_command == "evaluate"
    assert evaluate.evaluation_date is None
    assert evaluate.force is False
    assert evaluate.run_dir is None


def test_parser_exposes_phase3_commands():
    parser = build_parser()
    source_add = parser.parse_args(
        [
            "discovery", "source-add", "--organization", "기관", "--type", "manual_url",
            "--url", "https://jobs.example.or.kr/1", "--allow-domain", "example.or.kr",
        ]
    )
    discovery_run = parser.parse_args(
        [
            "discovery", "run", "--source-id", "source-1",
            "--evaluation-time", "2026-07-11T12:00:00+09:00",
        ]
    )
    registry = parser.parse_args(["registry", "list"])
    queue = parser.parse_args(["queue", "list", "--status", "pending"])

    assert source_add.discovery_command == "source-add"
    assert discovery_run.discovery_command == "run"
    assert registry.registry_command == "list"
    assert queue.queue_command == "list"
