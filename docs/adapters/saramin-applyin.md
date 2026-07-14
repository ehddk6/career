# Saramin Applyin adapters

`saramin_applyin_fixture` is an offline test adapter for the synthetic file `tests/fixtures/saramin_applyin/application_form_v1.html`.

- `live_enabled=false`
- exact fixture origin: `https://sample-company.applyin.invalid:443`
- permission scope: signed `fill_only` authorization
- supported mutations: fixture mock `fill`, `select_option`, and `check`
- attachments: unsupported
- live navigation, login, browser launch, upload, button click, and submit: unsupported

Before the first mutation it checks the full schema, action, method, fields, selectors, options, limits, controls, package bindings, schema hash, exact origin, fixture-only signature, expiry, revocation, and single-use ledger. Any drift blocks the whole fixture run before mutation. The result stores field identifiers and lengths, not entered values.

The fixture authority is issued only by the local `fixture-authorize` command. It is a separate HMAC contract from external V2 execution authority and rejects non-`.invalid` origins. Set `CAREER_EXECUTION_SIGNING_KEY` outside the repository; the key must be at least 32 bytes. `CAREER_EXECUTION_KEY_ID` is an optional non-secret identifier.

```powershell
python -m career_pipeline application adapter show saramin_applyin_fixture
python -m career_pipeline application adapter schema saramin_applyin_fixture
python -m career_pipeline application adapter validate saramin_applyin_fixture
python -m career_pipeline application fixture-authorize `
  --adapter saramin_applyin_fixture `
  --package ".career_profile/application_packages/package.json" `
  --dry-run-result "career_runs/<run-dir>/form_result.json" `
  --allowed-origin "https://sample-company.applyin.invalid" `
  --at "2026-07-12T12:01:00+09:00" `
  --expires-at "2026-07-12T13:00:00+09:00" `
  --output "career_runs/<run-dir>/fixture_authorization.json"
```

Then pass that fixture authorization to `application fill-fixture`. This command still uses only the synthetic `FixtureMockPage`; it cannot open Saramin, navigate, upload, click, or submit.

This contract must not be used against a real Applyin company site. A live adapter requires a separately reviewed contract and explicit authorization.

## KODIT live adapter

`saramin_applyin_kodit_live` supports the inspected KODIT pre-confirm page at the exact origin
`https://kodit2.saramin.co.kr:443`. It does not grant authority to any other Saramin/Applyin tenant.

The live path is split into two independently signed, short-lived actions:

1. `fill_only`: checks the current origin, exact path, POST action, complete structural schema,
   package hashes, eligibility, expiry, CAPTCHA/MFA markers and duplicate status before entering data.
2. `submit`: requires a new grant and immediate final confirmation. The execution intent is stored
   before the submit control is used. A timeout or missing receipt becomes `submission_unverified`
   and is never retried automatically.

Private values are passed to the browser bridge only in memory. Plans and ledgers contain logical
field IDs, hashes and verification status, not names, phone numbers, email addresses, credentials,
cookies or uploaded file contents. File upload also requires a separate immediate confirmation.

The currently verified first-page schema SHA-256 is
`b851a92cad06e0d81330be3d101b913b692359448244fca44d487a8388dbe6fb` (observed 2026-07-13).
Any field, option, form action, iframe, CAPTCHA or MFA change blocks mutation until a new inspection.

Create a plan from a browser-produced structural snapshot, then issue a grant only after the
applicant has reviewed the destination and action:

```powershell
$env:CAREER_APPLICATION_AUTH_HMAC_KEY = "<32-byte-or-longer-secret-from-secret-store>"
python -m career_pipeline application live-plan `
  --adapter saramin_applyin_kodit_live `
  --snapshot "kodit-preconfirm-snapshot.json" `
  --output "kodit-preconfirm-plan.json" `
  --at "2026-07-13T12:00:00+09:00"

python -m career_pipeline application live-authorize `
  --package ".career_profile/application_packages/package.json" `
  --plan "kodit-preconfirm-plan.json" `
  --mode fill_only `
  --approver-id applicant `
  --at "2026-07-13T12:01:00+09:00" `
  --expires-at "2026-07-13T12:11:00+09:00" `
  --confirm-live-action `
  --output "kodit-fill-grant.json"
```

Login credentials are never accepted by these commands. Login, consent, upload and final submit
remain visible browser actions and require the applicant's action-time approval. CAPTCHA is not
solved or bypassed, and MFA is completed only by the applicant.
