# Report

Write `<OUT>/report.json` with this shape (omit what you don't have; arrays may be empty; values are strings unless shown as numbers):

```json
{
  "subject": {"name": "", "aliases": [], "headline": "", "location": "", "photo": "https://...", "photo_credit": "", "summary": ""},
  "contacts": [{"type": "email|phone|website", "value": "", "source": "https://..."}],
  "profiles": [{"site": "", "url": "", "username": "", "confidence": "high|medium|low", "reason": "",
                "name": "", "bio": "", "location": "", "followers": ""}],
  "experience": [{"title": "", "org": "", "period": "", "source": ""}],
  "education": [{"school": "", "degree": "", "period": "", "source": ""}],
  "variants": [{"username": "", "found": 0}],
  "unchecked": [{"site": "", "username": "", "status": "WAF|UNKNOWN|UNRELIABLE|LOGIN", "url": ""}],
  "method": {"brief": "", "browser": ""}
}
```

- `method`: write `brief` and `browser` yourself. `render_report.py` fills `date`, `duration` (from the start time recorded in step 1), `bulk_check` (from `check.log`), `sites` and `variants` (from `results.csv`) unless you set them.
- `subject.photo`: the image URL from the most confident profile that has a real photo (avatar or `og:image`; skip generated placeholders such as GitHub identicons, Gravatar defaults or initials avatars). The render step downloads it once and embeds it, so the report keeps its photo offline and after the link expires (the URL is kept as `photo_source`). `photo_credit` is optional text shown under the photo (author/license).
- `unchecked`: one entry per site, not per row. Blocked sites usually block every variant, so list them together (`"username": "billgates, bill.gates"`, `"url"` = the site's main URL).
- `demo` (top level, optional): text for a banner at the top of the page; only for published examples.

Render:

    <PY> "<SKILL_DIR>/scripts/render_report.py" "<OUT>"

On `error: ...` fix the named field and rerun.

## Without Python

Create `<OUT>/report.html` yourself from `<SKILL_DIR>/assets/template.html`: replace `__REPORT_DATA__` with the `report.json` content, with every `<` written as `<` (backslash, u, 0, 0, 3, c). Embed the photo as a `data:image/...;base64,` URI if you have a base64 tool (`base64 -w0`, PowerShell `[Convert]::ToBase64String`), else keep the link. Fill `method` yourself, with `"bulk_check": "not run (no Python)"`.
