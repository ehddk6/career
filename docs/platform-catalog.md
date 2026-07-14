# Platform catalog

The catalog separates the discovery platform from the application system that owns a form.

| platform_id | current role | fixture adapter | live enabled |
| --- | --- | --- | --- |
| `jobkorea_jrs` | application family | `jobkorea_jrs_fixture` | false |
| `saramin_applyin` | application family | `saramin_applyin_fixture` | false |
| `saramin_direct` | discovery only | none | false |
| `work24` | discovery only | none | false |
| `wanted` | discovery only | none | false |
| `catch` | discovery only | none | false |
| `jasoseol` | discovery only | none | false |

Applyin subdomains are recognized only for classification. Execution authorization remains bound to the exact HTTPS origin, including the effective port. Unknown, malformed, insecure, ambiguous, or unregistered links require manual review. Classification performs no navigation or network request.

```powershell
python -m career_pipeline application platform list
python -m career_pipeline application platform show saramin_applyin
python -m career_pipeline application platform detect --url "https://sample.applyin.co.kr/apply" --discovery-platform saramin_direct --at "2026-07-12T12:00:00+09:00"
```

`live_enabled=false` is fail-closed. The catalog grants no permission to log in, upload, fill a live page, or submit an application.
