# Application Review and Controlled Execution

Phase 5 이후 상태 흐름은 다음과 같다.

```text
review_required
→ review approved/rejected/deferred
→ domain-scoped execution authorization
→ fill_only
→ awaiting_final_confirmation
→ submit authorization
→ submitted_verified | submission_unverified
```

`application review`는 package ID, 공고 SHA, 최종 manifest SHA, form schema SHA를 승인 기록에 고정한다. CAPTCHA, MFA, 변경된 DOM, 불완전한 dry-run은 승인할 수 없다.

`application authorize`는 승인 기록과 정확히 일치하는 package 및 form schema에 대해서만 발급된다. 권한은 정확한 단일 도메인과 `fill_only` 또는 `submit` 모드에 묶인다. 하위 도메인이나 유사 도메인은 자동 허용하지 않는다.

승인과 권한 artifact는 `CAREER_EXECUTION_SIGNING_KEY`를 사용한 HMAC-SHA-256으로 검증한다. 일반 SHA checksum은 권한 서명으로 취급하지 않는다. 키가 없거나 짧거나 artifact가 수정되면 fail-closed한다.

`fill_only` 실행 계약은 필드 입력과 재검증 후 반드시 `awaiting_final_confirmation`에서 멈추도록 정의한다. 제출은 별도의 `submit` 권한이 있을 때만 실행 계약을 통과한다. CAPTCHA, MFA, 중복 지원, 공고·manifest·폼 schema 변경, 검증 실패가 있으면 실행 드라이버 호출 전에 중단한다.

제출 성공은 접수번호와 완료 URL을 모두 확인한 경우에만 `submitted_verified`로 기록한다. 접수번호 원문은 저장하지 않고 SHA-256 fingerprint만 기록하며 URL query와 fragment는 제거한다. 증거가 부족하면 `submission_unverified`다.

Phase 5에는 운영 사이트용 Playwright mutation adapter와 live 실행 CLI가 포함되지 않는다. 운영 사이트 로그인, MFA, CAPTCHA 우회와 실제 개인정보 전송은 수행하지 않는다. 사이트별 fill-only adapter는 origin·iframe·popup·첨부 TOCTOU 정책과 함께 별도 Phase 6에서 구현한다.

위의 v1 실행 흐름은 역사적 계약 설명이며 현재 artifact를 실행 가능하게
만들지 않는다. v1 review/authorization은 자동 승격되지 않고 실행 진입점에서
`LEGACY_AUTHORIZATION_UNUSABLE`로 fail-closed한다. 현재 생성되는 site contract는
live/mutation capability가 비활성화되어 있어 fill 또는 submit 권한을 발급할 수 없다.

## M5 operational status boundary

`python -m career_pipeline offline-acceptance` and `python -m career_pipeline
status` expose only the deterministic local synthetic boundary. The normal
offline command exits `3` as `external_only_blocked`; this means local checks
completed while external inputs remain blocked, live execution is disabled, and
submission is not attempted. These commands provide no browser, credential,
real-PII, upload, click, or submit option and do not perform any live
application action.
