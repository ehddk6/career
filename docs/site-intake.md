# Phase 6.5 site intake

Site intake converts a user-supplied, de-identified local HTML fixture into a read-only contract candidate. It does not fetch the URL, launch a browser, log in, fill fields, upload files, or submit an application.

## Why origins are not hardcoded

`https://jrs.jobkorea.co.kr` is the public JRS service origin, not proof of a company application origin. Applyin's `applyin.co.kr` suffix identifies an application family but is never an authorization wildcard. Saramin posting pages may lead to Applyin, JRS, another ATS, or a company site. Therefore every catalog entry keeps `actual_execution_origin=null` and `requires_manual_intake=true` until a specific application URL and sanitized fixture are reviewed.

## Safe input procedure

1. Save only a de-identified UTF-8 HTML fixture under `tests/fixtures/site_intake`.
2. Remove names, contact details, IDs, addresses, cookies, tokens, hidden values, analytics identifiers, local paths, and attachment paths.
3. Run intake with the fixture resource name. The result stores only an opaque resource ID, byte length, SHA-256, canonical schema SHA-256, and validation codes.
4. Review `manual_review_required` and every validation code. A ready contract still has `mutation_enabled=false` and `live_enabled=false`.

```powershell
python -m career_pipeline application site-intake platform-status
python -m career_pipeline application site-intake create --platform-family auto --posting-url "https://www.saramin.co.kr/jobs" --resolved-application-url "https://company.applyin.co.kr/apply" --fixture-resource-id "safe_single_page.html" --login-status none --mfa-status none --captcha-status none --iframe-status none --popup-status none --redirect-status none --attachment-status unsupported --at "2026-07-12T12:00:00+09:00"
python -m career_pipeline application site-intake schema --resolved-application-url "https://company.applyin.co.kr/apply" --fixture-resource-id "safe_single_page.html"
python -m career_pipeline application site-intake list
```

Blocked fixtures and URLs return a nonzero exit status. CLI output never includes the HTML body, source fixture path, URL credentials, sensitive query values, or detected sensitive values.

## Contract states

- `read_only_contract_ready`: exact HTTPS origin, safe fixture, stable schema, and no blocking risk marker.
- `manual_review_required`: unknown family, multistep/redirect ambiguity, uncertain controls, or another structural risk.
- `blocked_sensitive_fixture`: possible personal data, credential, token, cookie, hidden secret, or local path.
- `blocked_invalid_origin`: exact application origin is unresolved or invalid.

Before any future fill-only adapter is considered, a person must confirm the live origin, application path, form steps, login, MFA, CAPTCHA, iframe, redirect, attachment policy, save/submit controls, and the site's automation terms.
