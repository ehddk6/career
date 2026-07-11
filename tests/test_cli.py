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
    assert fallback.patina_backend == "codex-cli,openai-http"
    assert fallback.patina_max_retries == 1
    assert fallback.patina_voice_sample == "voice.txt"
