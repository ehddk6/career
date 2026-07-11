from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from career_pipeline.application_package import (ApplicationPackageError, application_package_to_dict,
    build_application_package, ensure_application_not_duplicate, materialize_package_values,
    register_application_package, write_application_package)
from career_pipeline.artifacts import sha256_file
from career_pipeline.__main__ import main
from career_pipeline.eligibility import applicant_profile_to_dict, decision_to_dict, posting_record_to_dict
from career_pipeline.models import ApplicantProfile, EligibilityDecision, PostingRecord
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
