PASS

# 독립 최종 M5 재리뷰

- 유일 사양: `docs/engineering-discipline/plans/2026-07-13-cli-operational-gate.md`
- 대상: 현재 working tree의 M5 코드·테스트·docs·skill 및 실제 CLI subprocess 출력
- 코드·테스트 수정: 없음. 리뷰 문서만 갱신함.

## Verdict

`PASS`. 이전 MEDIUM finding인 `exact_origin` canonicalization 문제가 수정되었고, shared `normalize_origin()` exact equality, 비정규 origin의 exit 4, canonical positive envelope의 정상 통과를 독립 검증했다. M5의 exit/output security와 no-live 경계도 유지된다.

## Findings

| Severity | 상태 | 위치 | 결과 |
|---|---|---|---|
| MEDIUM | RESOLVED | `career_pipeline/__main__.py:484-491` | `_m5_origin()`이 `normalize_origin(origin)`을 호출하고 `origin != canonical`이면 `M5InputError`를 발생시킨다. |

현재 OPEN finding은 없다.

## Origin canonicalization 재검증

- 구현이 shared `origin_policy.normalize_origin()`을 직접 사용한다.
- canonical M4 positive envelope의 `authorization_candidate.exact_origin`은 shared normalizer 결과와 exact equality이며 `status`가 정상 처리한다.
- `https://EXAMPLE.com`을 acceptance에 넣고 `acceptance_sha256`을 재계산한 strict envelope는 subprocess exit `4`, JSON `outcome=invalid_input`으로 거부했다.
- `https://company.applyin.co.kr`처럼 port를 생략한 envelope도 subprocess exit `4`, JSON `outcome=invalid_input`으로 거부했다.
- 두 invalid 결과 모두 stderr가 비어 있고 traceback이 없다.

실제 subprocess 결과:

```text
offline positive: exit 3
canonical status: exit 3, outcome external_only_blocked
uppercase origin: exit 4, outcome invalid_input
omitted port: exit 4, outcome invalid_input
```

## Tests and verification

- `python -m pytest -q tests/test_cli.py -k "m5_"` → `12 passed, 11 deselected`
- `python -m pytest -q` → `540 passed, 5 skipped`
- `python -m compileall -q career_pipeline` → PASS
- `git diff --check` → PASS

5개 skip은 Windows runner에서 symlink 생성이 불가능한 기존 path/symlink 테스트다. M5 focused 테스트는 모두 실행·통과했다.

## Exit and output security

- 정상 offline acceptance는 exit `3`, `external_only_blocked`, `local_status=complete`, `live_execution_status=disabled`, `submission_status=not_attempted`를 반환한다.
- canonical positive envelope를 읽는 `status`도 exit `3`으로 처리한다.
- uppercase/omitted-port strict input은 exit `4`와 고정 `invalid_input` JSON을 반환한다.
- JSON 결과의 17개 top-level key, canonical ordering, trailing newline 계약이 유지된다.
- human invalid 결과는 stdout이 비고 고정된 4줄 stderr contract를 사용한다.
- `--workspace`·`--output` 경로, raw fixture HTML, sentinel, private path, absolute workspace path, query/token 값, signing material, PII가 public output에 노출되지 않는다.
- browser, network, credential, real PII, upload, click, submit 동작은 CLI 경계에 없다.

## Docs truth

다음 문서와 skill의 M5 설명은 현재 구현과 일치한다.

- `docs/career-pipeline-usage.md`
- `docs/application-execution.md`
- `docs/site-intake.md`
- `.agents/skills/career-pipeline/SKILL.md`

모두 deterministic local synthetic acceptance, 정상 exit 3, external inputs blocked, live execution disabled, submission not attempted, no-live/no-PII 경계를 명시한다. SHA placeholder는 실행 시 실제 lowercase SHA-256으로 치환해야 한다.

## Risks and disposition

- Windows 환경에서 symlink/reparse-point 관련 전체 경계는 5개 skip으로 완전히 실행되지 않았다. 이는 이번 수정의 실패 증거는 아니지만 환경 잔여 위험이다.
- full suite GREEN은 현재 working tree 기준이며, 이후 코드·테스트 변경 시 재검증이 필요하다.

최종 disposition: `PASS`. M5 최종 리뷰 조건을 충족했다.
