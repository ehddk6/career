# Phase 4 Output Contract

## ApplicationPackage

`ApplicationPackage`는 `mode: review_required`만 허용한다. package ID에는 output contract version과 공고 ID·snapshot SHA, applicant profile SHA, 질문 schema SHA, 최종 manifest SHA, 최종 답변 SHA가 반영된다.

private JSON과 첨부파일은 로컬 경로 없이 불투명한 resource reference, SHA-256, 형식 메타데이터만 기록한다. 이름, 이메일, 전화번호 등 실제 개인정보와 Windows 절대 경로, OneDrive 경로, URL query는 패키지와 일반 로그에 기록하지 않는다.

`validation_status`는 다음 값만 허용한다.

- `ready_for_review`: eligibility가 `eligible`이고 고정 산출물과 입력 해시가 검증됨
- `manual_review`: `eligible_with_gaps` 또는 폼 호환성에 사람의 판단이 필요함
- `blocked`: 공고·profile·decision 불일치, 비활성 공고, `manual_review` 또는 `ineligible`

동일한 입력의 동일 package ID는 멱등 처리한다. 식별 입력이 바뀌면 새 package ID를 만들고 이전 prepared 항목을 `superseded` 상태로 보존한다.

## FormAutomationResult

`dry-run`은 읽기 전용 DOM 탐색, 필드 매핑, 값·첨부 호환성 검사만 수행한다. DOM 입력, 파일 업로드, 클릭, 제출은 수행하지 않는다. private JSON과 첨부파일은 매 실행에서 명시적으로 바인딩하며 해시나 형식이 달라지면 실패한다.

`FormAutomationResult.status`는 `review_required`, `manual_review`, `blocked` 중 하나다. action은 실제 입력 기록이 아니라 사람 검토용 계획이며 원문 값 대신 SHA-256만 기록한다.

CAPTCHA, MFA, 비밀번호, 새 문항, 중복·모호한 매핑, disabled·readonly 필드, 길이·선택지·첨부 형식 불일치, 검사 중 DOM schema 변경이 발견되면 action 없이 중단한다. 제출 완료 상태, 접수번호, 자동 제출 권한은 Phase 4 계약에 존재하지 않는다.

제출 버튼 감지는 기록하되 클릭하지 않는다.
