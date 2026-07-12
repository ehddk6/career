# Site Intake Fail-Closed Hardening Implementation Plan

> **Worker note:** Execute task-by-task using independent worker and validator agents.

**Goal:** Correct Phase 6.5 so no unknown or structurally ambiguous site evidence can produce a ready contract or reuse a stale intake identity.

**Architecture:** Keep the existing `SiteIntakeRecord` and CLI shape. Add explicit status-to-validation-code policy before readiness calculation, include that policy evidence in the deterministic identity, and extend the read-only parser with structural ambiguity markers. No live or mutation API is introduced.

**Tech Stack:** Python 3.12 standard library, dataclasses, `HTMLParser`, pytest.

**Work Scope:**
- **In scope:** `site_intake.py` and its dedicated test file. Inline synthetic HTML is used; no new fixture file is required.
- **Out of scope:** authorization, readiness CLI, browser/network code, live sites, PII, push/PR.

**Verification Strategy:**
- **Level:** test-suite
- **Command:** `python -m pytest -q tests/test_site_intake.py tests/test_platform_catalog.py`
- **What it validates:** status semantics, structural risk detection, deterministic identity, registry behavior, and catalog invariants.

## File Structure Mapping

- `career_pipeline/site_intake.py`: status policy, parser markers, identity composition.
- `tests/test_site_intake.py`: status matrix, identity, and adversarial structure tests.

### Task 1: Status Policy and Identity

**Dependencies:** None

**Goal:** Require explicit safe structure metadata for contract readiness and bind the evaluated result into intake identity.

**Acceptance Criteria:**
- Missing/`unknown` login, MFA, CAPTCHA, iframe, popup, redirect, or attachment evidence produces a stable validation code and `manual_review_required`.
- `login_status=required`, any security status `present`, or `attachment_status=required` cannot produce `read_only_contract_ready`.
- Only `login=none`, security/structure statuses `none`, and `attachment=unsupported` may satisfy the metadata portion of readiness.
- Changing known structure metadata or validation codes changes `intake_id`; identical input remains idempotent.

**Files:**
- Modify `career_pipeline/site_intake.py`
- Modify `tests/test_site_intake.py`

**Test Commands:**
- RED: `python -m pytest -q tests/test_site_intake.py::test_every_unverified_structure_status_blocks_ready tests/test_site_intake.py::test_review_evidence_changes_intake_identity`
- GREEN: same command; expected `16 passed` (15 status cases plus one identity test).

- [ ] Add `test_every_unverified_structure_status_blocks_ready` using `@pytest.mark.parametrize(("structure_override", "expected_code"), UNSAFE_STRUCTURE_CASES)` and function signature `def test_every_unverified_structure_status_blocks_ready(tmp_path, structure_override, expected_code):`. This makes the 15 mappings below 15 independently reported pytest cases:

```python
UNSAFE_STRUCTURE_CASES = (
    ({}, "LOGIN_STATUS_UNVERIFIED"),
    ({"login_status": "unknown"}, "LOGIN_STATUS_UNVERIFIED"),
    ({"login_status": "required"}, "LOGIN_REQUIRED"),
    ({"mfa_status": "unknown"}, "MFA_STATUS_UNVERIFIED"),
    ({"mfa_status": "present"}, "MFA_DETECTED"),
    ({"captcha_status": "unknown"}, "CAPTCHA_STATUS_UNVERIFIED"),
    ({"captcha_status": "present"}, "CAPTCHA_DETECTED"),
    ({"iframe_status": "unknown"}, "IFRAME_STATUS_UNVERIFIED"),
    ({"iframe_status": "present"}, "EXTERNAL_IFRAME"),
    ({"popup_status": "unknown"}, "POPUP_STRUCTURE_UNKNOWN"),
    ({"popup_status": "present"}, "POPUP_STRUCTURE_UNKNOWN"),
    ({"redirect_status": "unknown"}, "REDIRECT_STRUCTURE_UNKNOWN"),
    ({"redirect_status": "present"}, "REDIRECT_STRUCTURE_UNKNOWN"),
    ({"attachment_status": "unknown"}, "ATTACHMENT_POLICY_UNKNOWN"),
    ({"attachment_status": "required"}, "ATTACHMENT_REQUIRED"),
)
SAFE_STRUCTURE = {
    "login_status": "none", "mfa_status": "none", "captcha_status": "none",
    "iframe_status": "none", "popup_status": "none", "redirect_status": "none",
    "attachment_status": "unsupported",
}
```

Each unsafe case merges over `SAFE_STRUCTURE`, except `{}` which verifies that omitted metadata is fully unverified. Assert expected code, `manual_review_required is True`, and no contract.

- [ ] Add `SAFE_STRUCTURE` at module scope in `tests/test_site_intake.py`. In the existing `test_safe_fixture_produces_stable_read_only_contract`, add `known_structure=SAFE_STRUCTURE` to its `build_site_intake()` call. Do not alter other existing tests.
- [ ] Add `test_review_evidence_changes_intake_identity`: build twice with identical input and `SAFE_STRUCTURE` and assert equal IDs; change only `login_status` to `required` and assert different IDs. Then monkeypatch `career_pipeline.site_intake._risks` to return `("MANUAL_FIELD_MAPPING_REQUIRED",)` with unchanged `SAFE_STRUCTURE` and assert a third distinct ID, proving validation-code-only changes affect identity.
- [ ] Run the RED command before implementation. Expected baseline result is exactly `8 failed, 8 passed`: omitted/login/missing-security/attachment-required assertions and the identity-change assertion expose the new defects, while already-blocked present/unknown popup/redirect cases remain green. Record this result before implementation.
- [ ] Implement exact status-to-code rules above. Default every missing key to `unknown`; safe metadata is exactly `SAFE_STRUCTURE`.
- [ ] Replace the identity payload with canonical JSON containing exactly:

```python
identity_payload = {
    "platform_family": family,
    "exact_origin": exact,
    "fixture_sha256": fixture_sha,
    "schema_sha256": schema_sha,
    "validation_codes": codes,
    "known_structure": {key: known_structure.get(key, "unknown") for key in sorted(allowed_structure)},
    "contract_version": CONTRACT_VERSION,
}
```

Hash `json.dumps(identity_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))` for `intake_id` and contract identity.
- [ ] Run the task test command and require all selected tests to pass.

### Task 2: Structural Ambiguity Detection

**Dependencies:** Task 1

**Goal:** Convert HTML structures the static parser cannot safely interpret into explicit manual-review codes.

**Acceptance Criteria:**
- A `<base>` element produces `BASE_ELEMENT_REVIEW_REQUIRED`.
- Any `formaction` attribute produces `FORMACTION_REVIEW_REQUIRED`.
- Nested, multiple, or unclosed forms produce stable ambiguity/malformed codes and cannot become ready.
- Sensitive URL metadata and existing safe fixtures retain their current fail-closed/non-live behavior.

**Files:**
- Modify `career_pipeline/site_intake.py`
- Modify `tests/test_site_intake.py`

**Test Commands:**
- RED: `python -m pytest -q tests/test_site_intake.py::test_unsupported_html_structures_require_manual_review`
- GREEN: same command; expected `6 passed` through parameterization.

- [ ] Add exact parameterized test `test_unsupported_html_structures_require_manual_review`. Put `SAFE_FORM` and `STRUCTURE_CASES` at module scope so the `@pytest.mark.parametrize(("html", "expected_code"), STRUCTURE_CASES)` decorator can reference them. Keep only `build_inline_intake` inside the test body:

Use the following exact helper inside the test; no fixture file is created:

```python
def build_inline_intake(tmp_path, html):
    (tmp_path / "case.html").write_text(html, encoding="utf-8")
    return build_site_intake(
        posting_url=None,
        resolved_application_url="https://company.applyin.co.kr/apply",
        fixture_root=tmp_path,
        fixture_resource_id="case.html",
        discovery_platform_id=None,
        created_at="2026-07-12T12:00:00+09:00",
        known_structure=SAFE_STRUCTURE,
    )
```

Use these exact module-scope constants for parameterization and base/formaction injection:

```python
SAFE_FORM = """<form id="application" action="https://company.applyin.co.kr/submit" method="post"><button id="save" type="button" data-role="save">Save</button><button id="submit" type="submit">Submit</button></form>"""

STRUCTURE_CASES = (
    ("<base href='https://other.invalid/'>" + SAFE_FORM, "BASE_ELEMENT_REVIEW_REQUIRED"),
    (SAFE_FORM.replace('id="submit"', 'id="submit" formaction="/other"'), "FORMACTION_REVIEW_REQUIRED"),
    ("<form action='https://company.applyin.co.kr/submit'><form></form></form>", "NESTED_FORM_DETECTED"),
    ("<form action='https://company.applyin.co.kr/one'></form><form action='https://company.applyin.co.kr/two'></form>", "MULTIPLE_FORMS_DETECTED"),
    ("<form action='https://company.applyin.co.kr/submit'>", "MALFORMED_FORM_STRUCTURE"),
    ("<form action='https://company.applyin.co.kr/submit'/><button id='save' type='button' data-role='save'>Save</button><button id='submit' type='submit'>Submit</button>", "MALFORMED_FORM_STRUCTURE"),
)
```

Assert the expected code, manual review, and no contract for each tuple.

- [ ] Run the RED command and require all six parameterized cases to fail before implementation.
- [ ] Extend `_SchemaParser` with integer `base_count`, integer `formaction_count`, integer `form_depth`, boolean `nested_form`, and boolean `malformed_form`. In `handle_starttag`: increment `base_count` when `tag == "base"`; increment `formaction_count` whenever `"formaction" in a`; when `tag == "form"`, set `nested_form=True` if `form_depth > 0`, then increment `form_depth` before appending the form. In `handle_endtag`: when `tag == "form"`, decrement `form_depth` if it is positive, otherwise set `malformed_form=True`. Override `handle_startendtag`: if `tag.casefold() == "form"`, set `malformed_form=True`; then call `handle_starttag(tag, attrs)` followed by `handle_endtag(tag)` so the form is still represented without leaving depth open. Immediately after `parser.feed(html)` in `parse_read_only_schema`, set `parser.malformed_form = parser.malformed_form or parser.form_depth != 0` so unclosed forms are detected.
- [ ] Add these canonical schema keys: `base_count`, `formaction_count`, `nested_form`, `malformed_form`.
- [ ] Add exact `_risks` mappings: base count -> `BASE_ELEMENT_REVIEW_REQUIRED`; formaction count -> `FORMACTION_REVIEW_REQUIRED`; nested form -> `NESTED_FORM_DETECTED`; form count not equal to one -> `MULTIPLE_FORMS_DETECTED`; malformed form -> `MALFORMED_FORM_STRUCTURE`.
- [ ] Run the task test command and require all selected tests to pass.

### Task 3 (Final): Regression Verification and Checkpoint

**Dependencies:** Tasks 1 and 2

**Goal:** Verify the complete M1 contract and create one corrective checkpoint commit.

**Acceptance Criteria:**
- Every M1 success criterion is covered by a passing test.
- Full pytest, compileall, and diff check pass.
- Production code contains no browser/network/mutation API and generated contracts remain non-live/non-mutating.
- The M1 code commit contains only `career_pipeline/site_intake.py` and `tests/test_site_intake.py`. Long-run planning artifacts are committed separately at a later documentation checkpoint.

**Files:** Read-only verification, then stage exactly `career_pipeline/site_intake.py` and `tests/test_site_intake.py`. Do not stage `docs/engineering-discipline/` in the M1 code commit; harness artifacts remain separate until their own documentation checkpoint.

**Test Commands:**
- `python -m pytest -q tests/test_site_intake.py tests/test_platform_catalog.py`
- `python -m pytest -q`
- `python -m compileall -q career_pipeline`
- `git diff --check`

- [ ] Run all task test commands.
- [ ] Run this exact executable-API scan and require exit code 1 with no output (ripgrep's normal no-match result):

```powershell
rg -n -i "\.(fill|click|press|select_option|set_input_files|requestSubmit|fetch|send|post)\s*\(|\b(playwright|selenium|httpx|requests|urllib\.request|XMLHttpRequest|websocket|socket)\b" career_pipeline/site_intake.py
```

- [ ] Verify every generated contract has false mutation/live flags.
- [ ] Stage exactly `career_pipeline/site_intake.py tests/test_site_intake.py`, inspect staged diff and sensitive-value scan.
- [ ] After staging, run these exact sensitive-literal scans against the staged diff. The first `rg` command must exit 1 with no output. The PowerShell script must exit 0 with no output; it throws and fails if any assignment-like secret literal is found:

```powershell
git diff --cached -- career_pipeline/site_intake.py tests/test_site_intake.py | rg -n -i "C:\\\\Users\\|OneDrive\\|BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|Authorization:\s*(Bearer|Basic)\s+\S+"
$secretPattern = @'
(?i)(api[_-]?key|hmac[_-]?key|secret|access[_-]?token|refresh[_-]?token|password)\s*=\s*["'][^"']{8,}["']
'@
$secretHits = git diff --cached -- career_pipeline/site_intake.py tests/test_site_intake.py | Select-String -Pattern $secretPattern
if ($secretHits) { $secretHits; throw "sensitive literal detected" }
```
- [ ] Commit with `fix: harden site intake readiness semantics`.

## Self-Review

- Spec coverage: all four M1 criteria map to Task 1 or Task 2; Task 3 is the final gate.
- Placeholder scan: no TODO/TBD or unspecified implementation step.
- Type consistency: existing status strings and `SiteIntakeResult` remain the public contract.
- Dependencies: Task 2 follows Task 1 because both modify the same files; Task 3 follows both.
- Verification: dedicated tests plus full-suite regression are mandatory.
