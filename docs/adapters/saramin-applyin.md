# Saramin Applyin fixture adapter

`saramin_applyin_fixture` is an offline test adapter for the synthetic file `tests/fixtures/saramin_applyin/application_form_v1.html`.

- `live_enabled=false`
- exact fixture origin: `https://sample-company.applyin.invalid:443`
- permission scope: signed `fill_only` authorization
- supported mutations: fixture mock `fill`, `select_option`, and `check`
- attachments: unsupported
- live navigation, login, browser launch, upload, button click, and submit: unsupported

Before the first mutation it checks the full schema, action, method, fields, selectors, options, limits, controls, package bindings, schema hash, exact origin, signature, expiry, revocation, and single-use ledger. Any drift blocks the whole fixture run before mutation. The result stores field identifiers and lengths, not entered values.

```powershell
python -m career_pipeline application adapter show saramin_applyin_fixture
python -m career_pipeline application adapter schema saramin_applyin_fixture
python -m career_pipeline application adapter validate saramin_applyin_fixture
```

This contract must not be used against a real Applyin company site. A live adapter requires a separately reviewed contract and explicit authorization.
