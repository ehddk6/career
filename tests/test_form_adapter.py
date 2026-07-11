from hashlib import sha256
import json
from pathlib import Path

from career_pipeline.artifacts import sha256_file
from career_pipeline.form_adapter import FixtureFormDriver, PlaywrightFormDriver, ReviewRequiredFormAdapter, form_automation_result_to_dict
from career_pipeline.models import ApplicationAnswer, ApplicationAttachment, ApplicationPackage, FormFieldDescriptor


def review_package(tmp_path:Path):
    private=tmp_path/".career_profile"/"private.json"; private.parent.mkdir(exist_ok=True); private.write_text(json.dumps({"schema_version":1,"fields":{"full_name":"홍길동","email":"user@example.com"}},ensure_ascii=False),encoding="utf-8")
    resume=tmp_path/".career_profile"/"resume.pdf"; resume.write_bytes(b"%PDF-1.7\n"); answer="지원 동기 답변입니다."
    package=ApplicationPackage(1,"application-1","2026-07-12T09:00:00+09:00","review_required","posting-1","a"*64,"https://jobs.example.or.kr/1","기관","직무",("서울",),"profile-1","decision-1","eligible","b"*64,"c"*64,"d"*64,"e"*64,"phase4-review-required-v1",
        "private-"+sha256(f"private|{sha256_file(private)}".encode()).hexdigest()[:24],sha256_file(private),("email","full_name"),"f"*64,
        (ApplicationAnswer("answer_1",1,"지원 동기",answer,sha256(answer.encode()).hexdigest(),500),),
        (ApplicationAttachment("resume","attachment-"+sha256(f"attachment|{sha256_file(resume)}".encode()).hexdigest()[:24],sha256_file(resume),resume.stat().st_size,"application/pdf",".pdf"),),"ready_for_review",())
    return package,private,resume


def normal_html(extra=""):
    return f'''<form><label for="full-name">성명</label><input id="full-name" name="full_name" required>
    <label for="email">이메일</label><input id="email" name="email" type="email" required>
    <label for="answer">지원 동기</label><textarea id="answer" name="answer_1" maxlength="500" required></textarea>
    <label for="resume">이력서</label><input id="resume" name="resume" type="file" accept=".pdf" required>{extra}<input id="submit" type="submit"></form>'''


def run(tmp_path,html):
    package,private,resume=review_package(tmp_path); driver=FixtureFormDriver(html,url="https://jobs.example.or.kr/apply?sid=secret")
    result=ReviewRequiredFormAdapter().run(driver,root=tmp_path,package=package,private_data_path=private,attachments={"resume":resume},evaluation_time="2026-07-12T09:00:00+09:00")
    return result,driver


def test_read_only_dry_run_plans_without_mutation(tmp_path):
    result,driver=run(tmp_path,normal_html())
    assert result.status=="review_required" and result.stop_reason is None and result.dom_unchanged
    assert len(result.actions)==4 and all(a.status=="validated" for a in result.actions)
    assert not hasattr(driver,"fill") and not hasattr(driver,"upload") and result.page_url=="https://jobs.example.or.kr/apply"
    serialized=json.dumps(form_automation_result_to_dict(result),ensure_ascii=False)
    assert "홍길동" not in serialized and "user@example.com" not in serialized


def test_unknown_captcha_mfa_disabled_and_length_fail_before_actions(tmp_path):
    cases=[(normal_html('<textarea id="new" required></textarea>'),"unknown_or_ambiguous_field"),
        (normal_html('<div class="g-recaptcha">CAPTCHA</div>'),"captcha_detected"),
        (normal_html('<input id="pw" type="password">'),"mfa_or_authentication_detected"),
        (normal_html().replace('name="email"','name="email" readonly'),"form_value_incompatible"),
        (normal_html().replace('maxlength="500"','maxlength="5"'),"form_value_incompatible")]
    for html,reason in cases:
        result,_=run(tmp_path,html); assert result.stop_reason==reason and result.actions==()


def test_duplicate_field_identifier_is_ambiguous(tmp_path):
    result,_=run(tmp_path,normal_html('<input id="email" name="email">'))
    assert result.stop_reason=="unknown_or_ambiguous_field" and result.actions==()


def test_dom_change_fails_closed(tmp_path):
    package,private,resume=review_package(tmp_path)
    class Changing:
        def __init__(self): self.calls=0
        def discover_fields(self):
            self.calls+=1
            base=(FormFieldDescriptor("full_name","성명","full_name",None,"text",True),)
            return base if self.calls==1 else base+(FormFieldDescriptor("new","새 질문","new",None,"text",True),)
        def page_text(self): return ""
        def current_url(self): return "https://example.invalid/apply"
    result=ReviewRequiredFormAdapter().run(Changing(),root=tmp_path,package=package,private_data_path=private,attachments={"resume":resume},evaluation_time="2026-07-12T09:00:00+09:00")
    assert result.status=="blocked" and result.stop_reason=="form_schema_changed" and result.actions==() and not result.dom_unchanged


def test_playwright_driver_exposes_no_mutation_api():
    driver=PlaywrightFormDriver(object())
    for name in ("fill","type","press","click","select","select_option","check","upload","set_input_files","submit"):
        assert not hasattr(driver,name)
