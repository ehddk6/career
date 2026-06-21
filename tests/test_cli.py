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

    assert prepare.command == "prepare"
    assert prepare.target == "HUG 금융·기금"
    assert finalize.command == "finalize"
