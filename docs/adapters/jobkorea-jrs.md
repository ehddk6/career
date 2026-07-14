# JobKorea JRS Fixture Adapter

이 adapter는 실제 JRS 지원서 adapter가 아니라 `jobkorea_jrs_fixture_v1` 비식별 계약을 검증하는 첫 단계다.

- adapter ID: `jobkorea_jrs_fixture`
- contract version: `1`
- 공개 포털 origin: `https://jrs.jobkorea.co.kr`
- 실제 기업별 지원서 origin: 미확인
- `live_enabled=false`
- 외부 사이트 접속, 실제 개인정보 입력, 첨부 선택·업로드, 임시저장 클릭, 제출을 지원하지 않는다.

지원 logical field는 `applicant_name`, `email`, `phone`, `recruitment_track`, `work_region`, `motivation`, `problem_solving`, `teamwork`, `career_plan`, `privacy_consent`다. fixture의 `save_draft`와 `final_submit`은 존재 여부와 schema만 검사하는 금지 control이다. file/password/OTP/CAPTCHA, iframe, script, unknown field와 변경된 form action·required·maxlength·select option·submit control은 mutation 전에 차단한다.

fixture는 [application_form_v1.html](../../tests/fixtures/jobkorea_jrs/application_form_v1.html)이며 실제 기업 HTML, 로고, 약관, 사용자 데이터가 포함되지 않는다. schema 변경은 새 fixture와 새 adapter contract version으로 명시적으로 갱신한다.

실제 JRS 연결 전에는 기업별 지원 시작 URL에서 exact origin, form 구조, iframe·popup·redirect, 로그인·MFA·CAPTCHA, 저장/제출 control, 첨부 제한과 사이트 자동화 허용 여부를 별도로 확인해야 한다.
