from career_pipeline.__main__ import build_parser
import pytest
from pathlib import Path
from hashlib import sha256
import json


def test_m3_cli_parser_shape_is_unchanged():
    parser=build_parser(); value=parser.parse_args(["application","authorize","--package","p.json","--dry-run-result","d.json","--review","r.json","--allowed-origin","https://jobs.example.or.kr","--mode","fill_only","--output","a.json","--at","2026-07-12T12:00:00+09:00","--expires-at","2026-07-12T13:00:00+09:00","--approver-id","user"])
    assert value.application_command == "authorize" and value.mode == "fill_only"

def test_m3_cli_legacy_authorize_fails_closed(tmp_path,monkeypatch,capsys):
    import career_pipeline.__main__ as cli
    from career_pipeline.application_execution import approve_application, authorize_execution
    from tests.test_application_execution import KEY, NOW, EXP, dry_run
    from tests.test_application_package import build_package
    package=build_package(tmp_path); result=dry_run(package.package_id); review=approve_application(package,result,decision="approved",decided_at=NOW,approver_id="user",signing_key=KEY)
    monkeypatch.setattr(cli,"run_application_command",lambda _args: authorize_execution(package,result,review,allowed_origin="https://jobs.example.or.kr",mode="fill_only",authorized_at=NOW,expires_at=EXP,approver_id="user",signing_key=KEY))
    assert cli.main(["application","authorize","--package","p.json","--dry-run-result","d.json","--review","r.json","--allowed-origin","https://jobs.example.or.kr","--mode","fill_only","--output","a.json","--at",NOW,"--expires-at",EXP,"--approver-id","user"]) == 4
    assert "LEGACY_AUTHORIZATION_UNUSABLE" in capsys.readouterr().out

def test_m3_cli_legacy_fill_fixture_fails_closed(tmp_path,monkeypatch,capsys):
    import career_pipeline.__main__ as cli
    from career_pipeline.adapters.jobkorea_jrs import FixtureMockPage, collect_fixture_schema, run_fixture_fill
    schema=collect_fixture_schema(Path("tests/fixtures/jobkorea_jrs/application_form_v1.html").read_text(encoding="utf-8"))
    monkeypatch.setattr(cli,"run_application_command",lambda _args: run_fixture_fill(FixtureMockPage(schema),{},None,None,object(),executed_at="2026-07-12T12:00:00+09:00",ledger_path=tmp_path/"ledger.json",signing_key=b"x"*32))
    assert cli.main(["application","fill-fixture","--adapter","jobkorea_jrs_fixture","--package","p.json","--dry-run-result","d.json","--authorization","a.json","--values","v.json","--ledger","l.json","--output","o.json","--at", "2026-07-12T12:00:00+09:00"]) == 4
    assert "LEGACY_AUTHORIZATION_UNUSABLE" in capsys.readouterr().out


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

def test_parser_exposes_read_only_site_intake_commands():
    parser=build_parser()
    create=parser.parse_args(["application","site-intake","create","--resolved-application-url","https://company.applyin.co.kr/apply","--fixture-resource-id","safe_single_page.html","--at","2026-07-12T12:00:00+09:00"])
    schema=parser.parse_args(["application","site-intake","schema","--resolved-application-url","https://company.applyin.co.kr/apply","--fixture-resource-id","safe_single_page.html"])
    status=parser.parse_args(["application","site-intake","platform-status"])
    assert create.intake_command=="create" and schema.intake_command=="schema" and status.intake_command=="platform-status"


M5_KEYS = {"acceptance", "acceptance_sha256", "artifact_sha256", "blocker_codes", "command", "error_code", "external_inputs_status", "kind", "live_execution_status", "local_status", "message", "offline_acceptance_status", "outcome", "package_sha256", "readiness_sha256", "schema_version", "submission_status"}
M5_AT = "2026-07-13T12:00:00+09:00"
M5_UNTIL = "2026-07-13T13:00:00+09:00"


def _m5_run(argv, capsys):
    import career_pipeline.__main__ as cli
    exit_code = cli.main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def _m5_evidence_sha():
    return sha256((Path(__file__).parent / "test_offline_acceptance.py").read_bytes()).hexdigest()


def _m5_positive_envelope(tmp_path):
    from career_pipeline.offline_acceptance import AcceptanceInputs, offline_acceptance_to_dict, run_offline_acceptance
    result = run_offline_acceptance(workspace=tmp_path / "synthetic", inputs=AcceptanceInputs(M5_AT, M5_AT, M5_AT, M5_AT, M5_AT, M5_AT, M5_UNTIL, M5_AT, M5_AT, M5_AT, b"m5-public-synthetic-signing-value-01", "m5-public-synthetic", _m5_evidence_sha()))
    acceptance = offline_acceptance_to_dict(result)
    axes = {item.axis.value: item.status.value for item in result.readiness_report.axes}
    return {"acceptance": acceptance, "acceptance_sha256": sha256(json.dumps(acceptance, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(), "artifact_sha256": acceptance["final_manifest_sha256"], "blocker_codes": sorted({item.code.value for item in result.readiness_report.blockers}), "command": "offline-acceptance", "error_code": None, "external_inputs_status": axes["external_inputs"], "kind": "offline_acceptance", "live_execution_status": axes["live_execution"], "local_status": "complete", "message": None, "offline_acceptance_status": axes["offline_acceptance"], "outcome": "external_only_blocked", "package_sha256": acceptance["package_sha256"], "readiness_sha256": acceptance["readiness_sha256"], "schema_version": "career-pipeline-cli-offline-acceptance-v1", "submission_status": axes["submission"]}


def _m5_complete_readiness():
    from career_pipeline.readiness import EvidenceFreshness, EvidenceRecord, EvidenceSourceKind, ExternalInputsStatus, LiveExecutionStatus, LocalFoundationStatus, OfflineAcceptanceStatus, ReadinessAxisName, RequirementClassification, RequirementRecord, SubmissionStatus, build_readiness_report, readiness_report_to_dict
    evidence = (EvidenceRecord("EVIDENCE-CODE", EvidenceSourceKind.CODE, "career_pipeline/readiness.py", "a" * 64, None, M5_AT, EvidenceFreshness.CURRENT), EvidenceRecord("EVIDENCE-TEST", EvidenceSourceKind.TEST, "tests/test_readiness.py", "b" * 64, None, M5_AT, EvidenceFreshness.CURRENT))
    requirements = tuple(RequirementRecord(f"REQ-{axis.value.upper()}", axis, f"{axis.value} complete", RequirementClassification.IMPLEMENTED, ("EVIDENCE-CODE", "EVIDENCE-TEST"), cli_exposure="m5") for axis in ReadinessAxisName)
    return readiness_report_to_dict(build_readiness_report(generated_at=M5_AT, axis_statuses={ReadinessAxisName.LOCAL_FOUNDATION: LocalFoundationStatus.COMPLETE, ReadinessAxisName.OFFLINE_ACCEPTANCE: OfflineAcceptanceStatus.PASSED, ReadinessAxisName.EXTERNAL_INPUTS: ExternalInputsStatus.READY, ReadinessAxisName.LIVE_EXECUTION: LiveExecutionStatus.AUTHORIZED, ReadinessAxisName.SUBMISSION: SubmissionStatus.VERIFIED}, requirements=requirements, blockers=(), evidence=evidence))


def _m5_blocked_envelope():
    acceptance = {"schema_version": "career-pipeline-offline-acceptance-v1", "scenario": "sensitive_fixture", "block_code": "blocked_sensitive_fixture", "counters": {name: 0 for name in ("network", "browser", "credential", "pii", "upload", "click", "submit")}}
    return {"acceptance": acceptance, "acceptance_sha256": sha256(json.dumps(acceptance, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(), "artifact_sha256": None, "blocker_codes": ["blocked_sensitive_fixture"], "command": "offline-acceptance", "error_code": None, "external_inputs_status": "blocked", "kind": "offline_acceptance", "live_execution_status": "disabled", "local_status": "unsafe", "message": None, "offline_acceptance_status": "failed", "outcome": "local_unsafe", "package_sha256": None, "readiness_sha256": None, "schema_version": "career-pipeline-cli-offline-acceptance-v1", "submission_status": "not_attempted"}


def _m5_write(tmp_path, monkeypatch, name, value):
    monkeypatch.chdir(tmp_path)
    (tmp_path / name).write_bytes(value if isinstance(value, bytes) else value.encode("utf-8"))
    return name


def test_m5_parser_exposes_status_and_offline_acceptance_commands():
    parser = build_parser()
    offline = parser.parse_args(["offline-acceptance", "--workspace", "synthetic", "--at", M5_AT, "--site-valid-until", M5_UNTIL, "--test-evidence-sha256", "a" * 64])
    status = parser.parse_args(["status", "--input", "report.json", "--format", "json"])
    assert offline.command == "offline-acceptance" and offline.format == "human"
    assert status.command == "status" and status.input == "report.json"


def test_m5_offline_acceptance_json_envelope_and_external_blocked_exit(tmp_path, capsys):
    from career_pipeline.origin_policy import normalize_origin
    exit_code, stdout, stderr = _m5_run(["offline-acceptance", "--workspace", str(tmp_path / "synthetic"), "--at", M5_AT, "--site-valid-until", M5_UNTIL, "--test-evidence-sha256", _m5_evidence_sha(), "--format", "json"], capsys)
    value = json.loads(stdout)
    assert exit_code == 3 and stderr == "" and set(value) == M5_KEYS
    assert (value["schema_version"], value["outcome"], value["local_status"], value["offline_acceptance_status"], value["external_inputs_status"], value["live_execution_status"], value["submission_status"]) == ("career-pipeline-cli-offline-acceptance-v1", "external_only_blocked", "complete", "passed", "blocked", "disabled", "not_attempted")
    assert value["acceptance"] is not None and value["acceptance_sha256"] and "--fixture-scenario" not in build_parser().format_help()
    assert value["acceptance"]["authorization_candidate"]["exact_origin"] == normalize_origin(value["acceptance"]["authorization_candidate"]["exact_origin"])


def test_m5_offline_acceptance_human_summary_is_machine_safe(tmp_path, capsys):
    expected = _m5_positive_envelope(tmp_path)
    exit_code, stdout, stderr = _m5_run(["offline-acceptance", "--workspace", str(tmp_path / "actual"), "--at", M5_AT, "--site-valid-until", M5_UNTIL, "--test-evidence-sha256", _m5_evidence_sha()], capsys)
    assert exit_code == 3 and stderr == ""
    assert stdout.splitlines() == ["command: offline-acceptance", "local: complete", "offline acceptance: passed", "external inputs: blocked", "live execution: disabled", "submission: not_attempted", "blockers: " + ",".join(expected["blocker_codes"]), "readiness sha256: " + expected["readiness_sha256"], "artifact sha256: " + expected["artifact_sha256"], "outcome: external_only_blocked (exit 3)"]
    assert str(tmp_path) not in stdout and "sensitive_fixture" not in stdout


def test_m5_offline_acceptance_writes_same_json_without_path_echo(tmp_path, capsys):
    output = tmp_path / "result.json"
    exit_code, stdout, stderr = _m5_run(["offline-acceptance", "--workspace", str(tmp_path / "synthetic"), "--at", M5_AT, "--site-valid-until", M5_UNTIL, "--test-evidence-sha256", _m5_evidence_sha(), "--format", "json", "--output", str(output)], capsys)
    assert exit_code == 3 and stderr == "" and output.read_bytes() == stdout.encode("utf-8") and str(output) not in stdout


def test_m5_status_reads_offline_envelope_as_external_only_blocked(tmp_path, monkeypatch, capsys):
    envelope = _m5_positive_envelope(tmp_path)
    input_name = _m5_write(tmp_path, monkeypatch, "offline.json", (json.dumps(dict(reversed(list(envelope.items()))), indent=1) + "\n"))
    exit_code, stdout, stderr = _m5_run(["status", "--input", input_name, "--format", "json"], capsys)
    value = json.loads(stdout)
    assert exit_code == 3 and stderr == "" and set(value) == M5_KEYS
    assert (value["command"], value["kind"], value["outcome"], value["acceptance"], value["readiness_sha256"]) == ("status", "status", "external_only_blocked", None, envelope["readiness_sha256"])


def test_m5_status_returns_zero_for_complete_readiness_fixture(tmp_path, monkeypatch, capsys):
    input_name = _m5_write(tmp_path, monkeypatch, "complete.json", json.dumps(_m5_complete_readiness()))
    exit_code, stdout, stderr = _m5_run(["status", "--input", input_name, "--format", "json"], capsys)
    value = json.loads(stdout)
    assert exit_code == 0 and stderr == "" and (value["outcome"], value["local_status"], value["blocker_codes"], value["acceptance"]) == ("local_complete", "complete", [], None)


def test_m5_status_returns_two_for_strict_blocked_offline_envelope(tmp_path, monkeypatch, capsys):
    input_name = _m5_write(tmp_path, monkeypatch, "blocked.json", json.dumps(_m5_blocked_envelope()))
    exit_code, stdout, stderr = _m5_run(["status", "--input", input_name, "--format", "json"], capsys)
    value = json.loads(stdout)
    assert exit_code == 2 and stderr == "" and value["outcome"] == "local_unsafe"
    assert (value["offline_acceptance_status"], value["external_inputs_status"], value["live_execution_status"], value["submission_status"], value["acceptance"], value["readiness_sha256"]) == ("failed", "blocked", "disabled", "not_attempted", None, None)


def test_m5_status_rejects_strict_input_failures_with_exit_four(tmp_path, monkeypatch, capsys):
    positive = _m5_positive_envelope(tmp_path)
    nested = json.loads(json.dumps(positive)); nested["acceptance"]["unknown"] = True
    mismatch = json.loads(json.dumps(positive)); mismatch["package_sha256"] = "0" * 64
    blocked = _m5_blocked_envelope(); blocked["blocker_codes"] = []
    cases = [("oversized.json", b" " * 1_000_001, "oversized.json"), ("escape.json", json.dumps(positive), "../escape.json"), ("malformed.json", "{", "malformed.json"), ("nested.json", json.dumps(nested), "nested.json"), ("digest.json", json.dumps(mismatch), "digest.json"), ("blocked.json", json.dumps(blocked), "blocked.json")]
    monkeypatch.chdir(tmp_path)
    for name, value, input_name in cases:
        (tmp_path / name).write_bytes(value if isinstance(value, bytes) else value.encode("utf-8"))
        exit_code, stdout, stderr = _m5_run(["status", "--input", input_name, "--format", "json"], capsys)
        parsed = json.loads(stdout)
        assert exit_code == 4 and stderr == "" and set(parsed) == M5_KEYS and parsed["outcome"] == "invalid_input" and parsed["error_code"] == "INVALID_INPUT"
    for index, origin in enumerate(("https://EXAMPLE.com", "https://example.com")):
        noncanonical = json.loads(json.dumps(positive))
        noncanonical["acceptance"]["authorization_candidate"]["exact_origin"] = origin
        noncanonical["acceptance_sha256"] = sha256(json.dumps(noncanonical["acceptance"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        name = f"origin-{index}.json"
        (tmp_path / name).write_text(json.dumps(noncanonical), encoding="utf-8")
        exit_code, stdout, stderr = _m5_run(["status", "--input", name, "--format", "json"], capsys)
        parsed = json.loads(stdout)
        assert exit_code == 4 and stderr == "" and set(parsed) == M5_KEYS and parsed["outcome"] == "invalid_input" and parsed["error_code"] == "INVALID_INPUT"
    exit_code, stdout, stderr = _m5_run(["offline-acceptance", "--workspace", "synthetic", "--at", M5_AT, "--site-valid-until", M5_UNTIL, "--test-evidence-sha256", "a" * 64, "--output", "out.json"], capsys)
    assert exit_code == 4 and stdout == "" and stderr.splitlines() == ["command: offline-acceptance", "outcome: invalid_input (exit 4)", "error: INVALID_INPUT", "message: invalid offline acceptance input"]


def test_m5_status_human_summary_never_claims_submission(tmp_path, monkeypatch, capsys):
    for name, value, expected_exit, outcome in (("complete.json", _m5_complete_readiness(), 0, "local_complete"), ("external.json", _m5_positive_envelope(tmp_path), 3, "external_only_blocked"), ("blocked.json", _m5_blocked_envelope(), 2, "local_unsafe")):
        input_name = _m5_write(tmp_path, monkeypatch, name, json.dumps(value))
        exit_code, stdout, stderr = _m5_run(["status", "--input", input_name], capsys)
        assert exit_code == expected_exit and stderr == "" and len(stdout.splitlines()) == 10
        assert stdout.splitlines()[0] == "command: status" and stdout.splitlines()[-1] == f"outcome: {outcome} (exit {expected_exit})"
        assert "submission: verified" not in stdout or outcome == "local_complete"


def test_m5_adapter_list_is_registry_derived_and_fixture_only(capsys):
    from career_pipeline.platform_catalog import list_fixture_adapters
    exit_code, stdout, stderr = _m5_run(["application", "adapter", "list"], capsys)
    assert list_fixture_adapters() == ("jobkorea_jrs_fixture", "saramin_applyin_fixture")
    assert exit_code == 0 and stderr == "" and json.loads(stdout) == list(list_fixture_adapters())


def test_m5_product_surface_redacts_sensitive_values_and_absolute_paths(tmp_path, capsys):
    exit_code, stdout, stderr = _m5_run(["offline-acceptance", "--workspace", str(tmp_path / "workspace"), "--at", M5_AT, "--site-valid-until", M5_UNTIL, "--test-evidence-sha256", _m5_evidence_sha(), "--format", "json"], capsys)
    source = Path("career_pipeline/__main__.py").read_text(encoding="utf-8")
    assert exit_code == 3 and stderr == "" and str(tmp_path) not in stdout and "sensitive_fixture" not in stdout
    assert "--fixture-html" not in source and "--fixture-scenario" not in source and "page.goto" not in source and "page.click" not in source and "set_input_files" not in source


def test_m5_existing_commands_remain_compatible_when_new_top_level_commands_are_added(capsys):
    parser = build_parser()
    legacy = parser.parse_args(["application", "adapter", "list"])
    exit_code, stdout, stderr = _m5_run(["application", "adapter", "list"], capsys)
    newer = parser.parse_args(["status", "--input", "report.json"])
    assert legacy.application_command == "adapter" and legacy.adapter_command == "list"
    assert exit_code == 0 and stderr == "" and json.loads(stdout) == ["jobkorea_jrs_fixture", "saramin_applyin_fixture"] and newer.command == "status"
