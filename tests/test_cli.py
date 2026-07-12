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


def test_parser_exposes_phase4_review_required_commands():
    parser = build_parser()
    package = parser.parse_args(
        [
            "application", "package", "--run", "career_runs/sample",
            "--profile", "profile.json", "--posting", "posting.json",
            "--decision", "decision.json", "--private-data", ".career_profile/private.json",
            "--attachment", "resume=.career_profile/resume.pdf", "--output", ".career_profile/package.json",
        ]
    )
    validate = parser.parse_args(
        ["application", "validate", "--package", ".career_profile/package.json", "--private-data", ".career_profile/private.json"]
    )
    dry_run = parser.parse_args(
        [
            "application", "dry-run", "--package", ".career_profile/package.json", "--private-data", ".career_profile/private.json",
            "--html", "tests/fixtures/application_form.html", "--output", ".career_profile/form-result.json",
            "--evaluation-time", "2026-07-12T09:00:00+09:00",
        ]
    )

    assert package.application_command == "package"
    assert package.attachment == ["resume=.career_profile/resume.pdf"]
    assert validate.application_command == "validate"
    assert dry_run.application_command == "dry-run"


def test_parser_exposes_review_and_authorization_commands():
    parser = build_parser()
    review = parser.parse_args(["application", "review", "--package", "package.json", "--dry-run-result", "dry.json",
        "--decision", "approved", "--output", "review.json", "--at", "2026-07-12T12:00:00+09:00", "--approver-id", "user"])
    authorize = parser.parse_args(["application", "authorize", "--package", "package.json", "--dry-run-result", "dry.json",
        "--review", "review.json", "--allowed-origin", "https://jobs.example.or.kr", "--mode", "fill_only",
        "--output", "authorization.json", "--at", "2026-07-12T12:01:00+09:00", "--expires-at", "2026-07-12T13:00:00+09:00", "--approver-id", "user"])
    assert review.application_command == "review"
    assert authorize.application_command == "authorize"


def test_parser_exposes_jobkorea_jrs_fixture_commands():
    parser=build_parser()
    show=parser.parse_args(["application","adapter","show","jobkorea_jrs_fixture"])
    validate=parser.parse_args(["application","adapter","validate","jobkorea_jrs_fixture"])
    fill=parser.parse_args(["application","fill-fixture","--adapter","jobkorea_jrs_fixture","--package","p.json","--dry-run-result","d.json","--authorization","a.json","--values","v.json","--ledger","l.json","--output","o.json","--at","2026-07-12T12:00:00+09:00"])
    result=parser.parse_args(["application","fixture-result","--result","o.json"])
    assert show.adapter_command=="show" and validate.adapter_command=="validate" and fill.application_command=="fill-fixture" and result.application_command=="fixture-result"


def test_parser_exposes_platform_catalog_and_applyin_fixture_commands():
    parser = build_parser()
    listing = parser.parse_args(["application", "platform", "list", "--role", "discovery"])
    detection = parser.parse_args(["application", "platform", "detect", "--url", "https://sample.applyin.co.kr/apply", "--discovery-platform", "saramin_direct", "--at", "2026-07-12T12:00:00+09:00"])
    adapter = parser.parse_args(["application", "adapter", "show", "saramin_applyin_fixture"])
    schema = parser.parse_args(["application", "adapter", "schema", "saramin_applyin_fixture"])
    fill = parser.parse_args(["application", "fill-fixture", "--adapter", "saramin_applyin_fixture", "--package", "p.json", "--dry-run-result", "d.json", "--authorization", "a.json", "--values", "v.json", "--ledger", "l.json", "--output", "o.json", "--at", "2026-07-12T12:00:00+09:00"])
    assert listing.role == "discovery"
    assert detection.discovery_platform == "saramin_direct"
    assert adapter.adapter_id == "saramin_applyin_fixture"
    assert schema.adapter_command == "schema"
    assert fill.adapter == "saramin_applyin_fixture"
