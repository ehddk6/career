from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path

import pytest

from career_pipeline.application_package import (ApplicationPackageError, application_package_to_dict,
    build_application_package, ensure_application_not_duplicate, materialize_package_values,
    persist_application_package, register_application_package, write_application_package)
from career_pipeline.artifacts import sha256_file
from career_pipeline.__main__ import main
from career_pipeline.eligibility import applicant_profile_to_dict, decision_to_dict, posting_record_to_dict
from career_pipeline.inventory import digest_path
from career_pipeline.models import ApplicantProfile, CertificationRecord, EligibilityDecision, PostingRecord
from career_pipeline.profile_builder import excerpt_sha256
from career_pipeline.state import write_json


def package_inputs(tmp_path: Path, eligibility_status="eligible"):
    run_dir=tmp_path/"career_runs"/"sample"; run_dir.mkdir(parents=True)
    answer=run_dir/"draft_final.json"; md=run_dir/"final.md"; docx=run_dir/"final.docx"
    answer.write_text(json.dumps([{"question_index":1,"answer":"검증된 경험을 바탕으로 작성한 답변입니다."}],ensure_ascii=False),encoding="utf-8")
    md.write_text("# final",encoding="utf-8"); docx.write_bytes(b"PK-docx")
    artifact={"answer_json_path":"draft_final.json","markdown_path":"final.md","docx_path":"final.docx",
        "sha256":{"answer_json":sha256_file(answer),"markdown":sha256_file(md),"docx":sha256_file(docx)},"validation":{"status":"passed","issues":[]}}
    state={"status":"complete","questions":[{"index":1,"prompt":"지원 동기를 작성하세요.","character_limit":500}],"final_artifact":artifact}
    profile=ApplicantProfile(1,"profile-1","2026-07-12T09:00:00+09:00",None,(),(),(),())
    posting=PostingRecord(1,"posting-1","https://jobs.example.or.kr/1","jobs.example.or.kr","2026-07-01","2026-07-31","공고","기관","직무","a"*64,
        "2026-07-12T09:00:00+09:00","verified_domain",("서울",),(),(),canonical_url="https://jobs.example.or.kr/1",timezone="+09:00",status="active")
    decision=EligibilityDecision(1,"decision-1",posting.posting_id,profile.profile_id,eligibility_status,"2026-07-12T09:00:00+09:00",(),(),eligibility_status=="eligible_with_gaps")
    private=tmp_path/".career_profile"/"private.json"; private.parent.mkdir(); private.write_text(json.dumps({"schema_version":1,"fields":{"full_name":"홍길동","email":"user@example.com","phone":"010-0000-0000"}},ensure_ascii=False),encoding="utf-8")
    resume=tmp_path/".career_profile"/"resume.pdf"; resume.write_bytes(b"%PDF-1.7\n")
    return run_dir,state,profile,posting,decision,private,resume


def build_package(tmp_path:Path,eligibility_status="eligible"):
    run,state,profile,posting,decision,private,resume=package_inputs(tmp_path,eligibility_status)
    return build_application_package(root=tmp_path,run_dir=run,run_state=state,profile=profile,posting=posting,decision=decision,
        private_data_path=private,profile_sha256="d"*64,attachments={"resume":resume},created_at="2026-07-12T09:00:00+09:00")


def configure_v2_profile(tmp_path: Path, run_dir: Path, state: dict):
    source = tmp_path / "career.txt"
    text = "자료를 확인해 처리 건수를 20건으로 정리했습니다."
    source.write_text(text, encoding="utf-8")
    payload = {
        "schema_version": 1,
        "generated_at": "2026-07-12T09:00:00+09:00",
        "workspace_root": tmp_path.as_posix(),
        "experiences": [
            {
                "experience_id": "exp_1",
                "title": "자료 검증 경험",
                "organization_alias": "",
                "period": None,
                "role": "",
                "situation": text,
                "actions": ["자료를 확인했습니다."],
                "outcomes": [],
                "competencies": ["정확성"],
                "claims": [
                    {
                        "field": "case_count",
                        "normalized_value": "20건",
                        "status": "confirmed",
                        "evidence": [
                            {
                                "source_path": "career.txt",
                                "paragraph_index": 0,
                                "source_sha256": digest_path(source),
                                "excerpt_sha256": excerpt_sha256(text),
                            }
                        ],
                    }
                ],
                "status": "confirmed",
                "confirmed_at": "2026-07-12T09:00:00+09:00",
            }
        ],
    }
    profile_path = tmp_path / ".career_profile" / "experience_ledger.json"
    profile_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    write_json(run_dir / "02_확정경험원장.json", payload)
    state["quality_mode"] = "v2"
    state["profile"] = str(profile_path)
    return source, profile_path, payload


def _build_from_inputs(tmp_path: Path, inputs):
    run, state, profile, posting, decision, private, resume = inputs
    return build_application_package(
        root=tmp_path,
        run_dir=run,
        run_state=state,
        profile=profile,
        posting=posting,
        decision=decision,
        private_data_path=private,
        profile_sha256="d" * 64,
        attachments={"resume": resume},
        created_at="2026-07-12T09:00:00+09:00",
    )


def test_v2_package_blocks_when_evidence_source_changes_after_run(tmp_path):
    inputs = package_inputs(tmp_path)
    run, state, *_ = inputs
    source, _profile_path, _payload = configure_v2_profile(tmp_path, run, state)
    assert _build_from_inputs(tmp_path, inputs).validation_status == "ready_for_review"
    source.write_text(
        "자료를 확인해 처리 건수를 21건으로 정리했습니다.", encoding="utf-8"
    )
    package = _build_from_inputs(tmp_path, inputs)
    assert package.validation_status == "blocked"
    assert "profile_source_evidence_stale" in package.validation_reasons


def test_v2_package_blocks_when_confirmed_ledger_changes_after_run(tmp_path):
    inputs = package_inputs(tmp_path)
    run, state, *_ = inputs
    _source, profile_path, payload = configure_v2_profile(tmp_path, run, state)
    payload["experiences"][0]["claims"][0]["normalized_value"] = "21건"
    profile_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    package = _build_from_inputs(tmp_path, inputs)
    assert package.validation_status == "blocked"
    assert "profile_ledger_stale" in package.validation_reasons


def test_package_preserves_spaces_excluded_character_count_mode(tmp_path):
    inputs = package_inputs(tmp_path)
    run, state, *_ = inputs
    answer_path = run / "draft_final.json"
    answer = "가 나 다"
    answer_path.write_text(
        json.dumps([{"question_index": 1, "answer": answer}], ensure_ascii=False),
        encoding="utf-8",
    )
    state["questions"][0]["character_limit"] = 3
    state["questions"][0]["count_mode"] = "spaces_excluded"
    state["final_artifact"]["sha256"]["answer_json"] = sha256_file(answer_path)
    package = _build_from_inputs(tmp_path, inputs)
    assert len(answer) == 5
    assert package.validation_status == "ready_for_review"
    assert package.answers[0].character_limit == 3
    assert package.answers[0].count_mode == "spaces_excluded"


def test_package_is_private_and_materializes_only_with_runtime_bindings(tmp_path):
    package=build_package(tmp_path); serialized=json.dumps(application_package_to_dict(package),ensure_ascii=False)
    assert package.validation_status=="ready_for_review" and package.mode=="review_required"
    assert "홍길동" not in serialized and "user@example.com" not in serialized and ".career_profile" not in serialized and "OneDrive" not in serialized
    private=tmp_path/".career_profile"/"private.json"; resume=tmp_path/".career_profile"/"resume.pdf"
    assert materialize_package_values(tmp_path,package,private_data_path=private,attachments={"resume":resume})["answer_1"].startswith("검증된")


def test_changed_private_data_blocks_materialization(tmp_path):
    package=build_package(tmp_path); private=tmp_path/".career_profile"/"private.json"
    private.write_text(json.dumps({"schema_version":1,"fields":{"full_name":"변경"}}),encoding="utf-8")
    with pytest.raises(ApplicationPackageError,match="SHA-256 changed"):
        materialize_package_values(tmp_path,package,private_data_path=private,attachments={"resume":tmp_path/".career_profile"/"resume.pdf"})


def test_attachment_change_blocks_materialization(tmp_path):
    package=build_package(tmp_path); resume=tmp_path/".career_profile"/"resume.pdf"; resume.write_bytes(b"%PDF-changed")
    with pytest.raises(ApplicationPackageError,match="attachment changed"):
        materialize_package_values(tmp_path,package,private_data_path=tmp_path/".career_profile"/"private.json",attachments={"resume":resume})


def test_eligible_with_gaps_requires_manual_review(tmp_path): assert build_package(tmp_path,"eligible_with_gaps").validation_status=="manual_review"


def test_expired_profile_credential_prevents_ready_for_review_package(tmp_path):
    run, state, profile, posting, decision, private, resume = package_inputs(tmp_path)
    profile = replace(
        profile,
        certifications=(
            CertificationRecord(
                "TOEIC", expires_at="2026-07-30", status="valid", verified=True
            ),
        ),
    )

    package = build_application_package(
        root=tmp_path,
        run_dir=run,
        run_state=state,
        profile=profile,
        posting=posting,
        decision=decision,
        private_data_path=private,
        profile_sha256="d" * 64,
        attachments={"resume": resume},
        created_at="2026-07-12T09:00:00+09:00",
    )

    assert package.validation_status == "manual_review"
    assert "credential_selection_unconfirmed" in package.validation_reasons


def test_missing_required_attachment_blocks_application_package(tmp_path):
    run, state, profile, posting, decision, private, resume = package_inputs(tmp_path)

    package = build_application_package(
        root=tmp_path,
        run_dir=run,
        run_state=state,
        profile=profile,
        posting=posting,
        decision=decision,
        private_data_path=private,
        profile_sha256="d" * 64,
        attachments={"resume": resume},
        required_attachment_keys=("resume", "transcript"),
        created_at="2026-07-12T09:00:00+09:00",
    )

    assert package.validation_status == "blocked"
    assert "required_attachment_missing:transcript" in package.validation_reasons


def test_expired_credential_can_be_explicitly_omitted_from_package(tmp_path):
    run, state, profile, posting, decision, private, resume = package_inputs(tmp_path)
    profile = replace(
        profile,
        certifications=(
            CertificationRecord(
                "TOEIC", expires_at="2026-07-30", status="valid", verified=True
            ),
        ),
    )

    package = build_application_package(
        root=tmp_path,
        run_dir=run,
        run_state=state,
        profile=profile,
        posting=posting,
        decision=decision,
        private_data_path=private,
        profile_sha256="d" * 64,
        attachments={"resume": resume},
        included_credential_names=(),
        created_at="2026-07-12T09:00:00+09:00",
    )

    assert package.validation_status == "ready_for_review"
    assert not package.validation_reasons


def test_selected_credential_is_bound_to_exact_attachment_digest(tmp_path):
    run, state, profile, posting, decision, private, resume = package_inputs(tmp_path)
    profile = replace(
        profile,
        certifications=(
            CertificationRecord("컴퓨터활용능력", status="valid", verified=True),
        ),
    )
    certificate = tmp_path / ".career_profile" / "certificate.pdf"
    certificate.write_bytes(b"%PDF-1.7\ncertificate")

    package = build_application_package(
        root=tmp_path,
        run_dir=run,
        run_state=state,
        profile=profile,
        posting=posting,
        decision=decision,
        private_data_path=private,
        profile_sha256="d" * 64,
        attachments={"resume": resume, "certificate": certificate},
        credential_attachment_keys={"컴퓨터활용능력": "certificate"},
        created_at="2026-07-12T09:00:00+09:00",
    )

    assert package.validation_status == "ready_for_review"
    assert package.submission_preflight_status == "ready"
    assert package.submission_preflight_sha256
    assert package.credential_bindings[0].attachment_sha256 == next(
        item.sha256 for item in package.attachments if item.field_key == "certificate"
    )

    tampered = replace(
        package,
        credential_bindings=(
            replace(package.credential_bindings[0], attachment_sha256="f" * 64),
        ),
    )
    with pytest.raises(ApplicationPackageError, match="credential attachment binding"):
        application_package_to_dict(tampered)


def test_registry_is_idempotent_and_changed_package_is_versionable(tmp_path):
    package=build_package(tmp_path); output=tmp_path/".career_profile"/"application_packages"/"package.json"
    write_application_package(output,package); register_application_package(tmp_path,output,package); register_application_package(tmp_path,output,package)
    ensure_application_not_duplicate(tmp_path,replace(package,package_id="application-different",final_manifest_sha256="e"*64))


def test_same_identity_with_later_created_at_is_idempotent(tmp_path):
    package=build_package(tmp_path); output=tmp_path/"package.json"; write_application_package(output,package)
    write_application_package(output,replace(package,created_at="2026-07-12T10:00:00+09:00"))
    assert json.loads(output.read_text(encoding="utf-8"))["created_at"]==package.created_at


def test_corrupt_registry_fails_closed(tmp_path):
    package=build_package(tmp_path); output=tmp_path/"package.json"; write_application_package(output,package)
    (tmp_path/".career_profile"/"application_registry.json").write_text("{",encoding="utf-8")
    with pytest.raises(ApplicationPackageError,match="invalid application registry"):
        register_application_package(tmp_path,output,package)


def test_credential_private_field_and_mime_mismatch_rejected(tmp_path):
    run,state,profile,posting,decision,private,resume=package_inputs(tmp_path)
    private.write_text(json.dumps({"schema_version":1,"fields":{"session_token":"secret"}}),encoding="utf-8")
    with pytest.raises(ApplicationPackageError,match="credential-like"):
        build_application_package(root=tmp_path,run_dir=run,run_state=state,profile=profile,posting=posting,decision=decision,private_data_path=private,profile_sha256="d"*64)
    private.write_text(json.dumps({"schema_version":1,"fields":{"full_name":"홍길동"}}),encoding="utf-8"); resume.write_bytes(b"not-pdf")
    with pytest.raises(ApplicationPackageError,match="mismatched"):
        build_application_package(root=tmp_path,run_dir=run,run_state=state,profile=profile,posting=posting,decision=decision,private_data_path=private,profile_sha256="d"*64,attachments={"resume":resume})


def test_identity_contract_fields_are_present(tmp_path):
    p=build_package(tmp_path)
    assert all(len(getattr(p,name))==64 for name in ("posting_sha256","profile_sha256","question_schema_sha256","final_manifest_sha256","final_artifact_sha256"))
    assert p.output_contract_version=="phase4-review-required-v1" and p.private_data_ref.startswith("private-") and p.attachments[0].resource_ref.startswith("attachment-")


def test_application_package_cli(tmp_path):
    run,state,profile,posting,decision,private,resume=package_inputs(tmp_path); write_json(run/"run.json",state)
    write_json(tmp_path/"profile.json",applicant_profile_to_dict(profile)); write_json(tmp_path/"posting.json",posting_record_to_dict(posting)); write_json(tmp_path/"decision.json",decision_to_dict(decision))
    result=main(["application","package","--root",str(tmp_path),"--run",str(run),"--profile","profile.json","--posting","posting.json","--decision","decision.json","--private-data",str(private),"--attachment",f"resume={resume}","--output",".career_profile/application_packages/package.json","--created-at","2026-07-12T09:00:00+09:00"])
    assert result==0 and (tmp_path/".career_profile"/"application_registry.json").exists()


def test_package_paths_reject_windows_drive_relative_and_link_escape(tmp_path):
    run, state, profile, posting, decision, private, resume = package_inputs(tmp_path)
    with pytest.raises(ApplicationPackageError):
        build_application_package(root=tmp_path, run_dir=run, run_state=state, profile=profile, posting=posting, decision=decision, private_data_path=Path("C:private.json"), profile_sha256="d" * 64, attachments={"resume": resume})
    package = build_application_package(root=tmp_path, run_dir=run, run_state=state, profile=profile, posting=posting, decision=decision, private_data_path=private, profile_sha256="d" * 64, attachments={"resume": resume}, created_at="2026-07-12T09:00:00+09:00")
    outside = tmp_path.parent / "outside-package.json"
    outside.write_text("{}", encoding="utf-8")
    link = tmp_path / "linked-package.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ApplicationPackageError):
        persist_application_package(tmp_path, link, package, private_data_path=private, attachments={"resume": resume})


def test_application_registry_concurrent_idempotent_writers_leave_valid_registry(tmp_path):
    package = build_package(tmp_path)
    package_path = tmp_path / "package.json"
    write_application_package(package_path, package)
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: register_application_package(tmp_path, package_path, package), range(16)))
    registry = json.loads((tmp_path / ".career_profile" / "application_registry.json").read_text(encoding="utf-8"))
    assert len(registry["entries"]) == 1 and len(registry["events"]) == 1
    assert not (tmp_path / ".career_profile" / ".application_registry.lock").exists()
