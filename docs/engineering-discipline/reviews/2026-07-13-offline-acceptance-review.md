PASS

# 독립 최종 M4 리뷰

- 유일 사양: `docs/engineering-discipline/plans/2026-07-12-offline-acceptance.md`
- 검토 대상: 현재 working tree, `HEAD=2c542ad` 및 미커밋 M4 변경
- 변경 금지 준수: 코드·테스트는 수정하지 않았고 이 리뷰 파일만 작성

## 결론

M4의 실행 경계와 fail-closed 동작을 재검증했다. 구조화된 synthetic posting/profile/eligibility, verified final-artifact fixture, `ApplicationPackage`, read-only site contract, adapter schema lineage, `ReviewDecisionV2`, disabled `AuthorizationCandidateV2`, readiness report까지 연결되며, 결과 상태도 사양과 일치한다.

이전 두 finding은 수정되어 해소됐다. `EVIDENCE-TEST`가 실제 `tests/test_offline_acceptance.py` SHA와 일치하고, sensitive fixture가 runner 수준에서 차단되며 zero counters와 sentinel 비노출을 직접 확인했다.

## Findings

활성 finding 없음.

| 이전 severity | 상태 | 직접 검증 |
|---|---|---|
| HIGH — TEST evidence SHA 불일치 | RESOLVED | 실제 `tests/test_offline_acceptance.py` SHA와 readiness `EVIDENCE-TEST.sha256`가 `7e13eefd9b6e6bda113be8883ed7b4203e093f8b3bd76666210a76f2cce6450b`로 동일 |
| MEDIUM — sensitive fixture runner-level coverage 부족 | RESOLVED | `run_offline_acceptance()`가 `blocked_sensitive_fixture`를 반환하고, 7개 counters가 모두 0이며 sentinel이 `offline_acceptance_to_dict()` 결과에 없음 |

## 사양 대조

| 항목 | 결과 | 결정적 근거 |
|---|---|---|
| 15개 M4 node | PASS | collect 결과 `15/141 tests collected`; focused run `15 passed, 126 deselected` |
| structured eligible path | PASS | runner가 `PostingRecord`/`EligibilityRule`을 직접 만들고 `validate_posting_record`, `evaluate_eligibility` 호출 |
| final-artifact boundary | PASS | `_write_verified_final_artifact_fixture()`가 `run.json`·answer JSON·manifest binding을 만들며 `finalize_run` 미호출 |
| adapter schema lineage | PASS | page `schema_sha256`와 observed adapter digest를 분리하고, 승인 form binding은 `adapter_schema_sha256` 사용 |
| lineage 누락 fail-closed | PASS | `ADAPTER_SCHEMA_LINEAGE_UNVERIFIED`, manual review, `contract is None` 테스트 통과 |
| disabled authority | PASS | `allowed_capabilities == ()`, `mutation_enabled=False`, `live_enabled=False`, candidate=`capability_disabled/FILL_AUTHORITY_DISABLED` |
| authorization boundary | PASS | `authorize_execution_v2()`는 `FILL_AUTHORITY_DISABLED`만 확인하고 authorization artifact를 결과에 보존하지 않음 |
| truthful status | PASS | `local_status=awaiting_external_live_enablement`, `live_status=disabled`, `submission_status=not_attempted` |
| deterministic public result | PASS | 동일 inputs를 두 output root에서 실행한 `offline_acceptance_to_dict()` 결과가 동일하고, package/readiness digest도 결정적으로 생성됨 |
| external boundary | PASS | runner에 network/browser/credential/PII/upload/click/submit 호출 없음; scan도 no match |

## schema lineage 및 공개 결과 점검

- `schema_sha256`는 canonical page/site schema로 유지되고, `adapter_schema_sha256`는 `ReviewRequiredFormAdapter.probe_contract()`의 observed form digest로 전달된다.
- `approve_application_v2()`의 approved path와 `_v2_bindings()`가 dry-run form digest를 adapter digest에 결합한다.
- 공개 serializer는 signing key, key fingerprint, HTML body, private applicant fields, sensitive URL value를 포함하지 않는다.
- readiness의 `EVIDENCE-TEST`가 실제 source digest와 연결됨을 직접 확인했다.

## zero external calls 및 truthful boundary

정적 확인 결과 `offline_acceptance.py`와 `test_offline_acceptance.py`에는 `requests`, `httpx`, `urllib.request`, `socket`, `selenium`, `playwright`, `page.goto`, `page.click`, `page.press`, `set_input_files`가 없다. `datetime.now`, `time.time`, `os.environ`, `dotenv`, `keyring`도 없다. runner는 `FixtureFormDriver`를 메모리 HTML에만 사용하고, 모든 call counter를 `(0, 0, 0, 0, 0, 0, 0)`으로 반환했다.

이 결과는 local synthetic/offline acceptance만 의미한다. live origin, production DOM, credentials, PII transmission authority, upload, click, submit, receipt collection은 검증하지 않으며, readiness report도 각각 external blocker로 남긴다.

## 실행한 검증

| 명령 | 결과 |
|---|---|
| `python -m pytest --collect-only -q tests/test_offline_acceptance.py tests/test_application_execution.py tests/test_site_intake.py -k "offline_acceptance or m4_approval or m4_site_intake"` | `15 tests collected` |
| `python -m pytest -q tests/test_offline_acceptance.py tests/test_application_execution.py tests/test_site_intake.py -k "offline_acceptance or m4_approval or m4_site_intake"` | `15 passed, 126 deselected` |
| `python -m pytest -q tests/test_application_execution.py tests/test_site_intake.py tests/test_form_adapter.py tests/test_jobkorea_jrs_adapter.py tests/test_saramin_applyin_adapter.py tests/test_application_package.py tests/test_readiness.py tests/test_offline_acceptance.py` | `215 passed, 2 skipped`; skip 2건은 Windows symlink creation unavailable |
| 직접 evidence/runner smoke 검증 | `positive_evidence_sha_equal=True`; sensitive runner=`blocked_sensitive_fixture`, counters 7개 0, sentinel 비노출 |
| `python -m pytest -q -rs` | `528 passed, 5 skipped` |
| `python -m compileall -q career_pipeline` | PASS |
| `git diff --check` | PASS; line-ending warning만 출력 |
| clock/environment scan | no match |
| network/browser/mutation API scan | no match |

## 잔여 위험 및 경계

- Windows에서 symlink 생성이 불가능해 symlink 관련 5개 테스트는 skip되었다. 이는 M4 실패는 아니지만 해당 환경의 미검증 경계다.
- call counter가 runtime instrumentation이 아니라 고정 zero tuple이라는 점은 향후 runner에 외부 호출 코드가 추가될 경우 회귀를 자동 계수하지 못하는 위험이다. 현재 tree의 정적 코드와 실행 경계에서는 외부 호출이 확인되지 않았다.

## 최종 판정

`PASS` — 두 finding을 실제 SHA equality와 runner-level sensitive fixture 검증으로 해소했고, focused/full tests, compileall, diff check 및 zero-external-call 경계 검증을 통과했다.
