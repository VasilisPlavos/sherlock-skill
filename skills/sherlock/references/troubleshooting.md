# Troubleshooting

| Symptom | Check / fix |
|---|---|
| No working Python | No Python 3.9+. Offer install (with approval) or continue without it — see step 1. Stdlib only, no pip packages needed. |
| Windows: "Python was not found ... Microsoft Store" | A Store stub was picked up; re-run the detection in step 1, which tests by running. |
| Files land in the wrong folder | Use the full `<OUT>` path in every command and quote paths that contain spaces. |
| `check.log` unreadable or empty in PowerShell | Use `--log "<OUT>/check.log"` instead of `>` redirection (PowerShell writes UTF-16). |
| Check stopped early (`PARTIAL` in the log) | `results.csv` holds the finished rows. Finish only the missing sites with `--site X --site Y --append --log "<OUT>/check-rest.log"` (same `--out`), in the background. |
| Manifest download fails | Both URLs blocked/offline → pass a saved copy with `--data data.json`, or `--proxy`. |
| Many `UNKNOWN` (timeouts) | Slow network: `--timeout 40`; lower `--workers`. |
| Many `WAF` (403/429) | Rate-limited or bot-blocked: lower `--workers` (e.g. 5), wait, or use `--proxy`; recheck the important ones in a browser. |
| Obvious false positive | Site changed its error page. Mark it low/ignore; calibration (`UNRELIABLE`) only catches sites that claim *any* name of that shape. |
| Browser lands on a login wall | Ask the user to sign in themselves, or list the site under `unchecked` with status `LOGIN`. |
| `render_report.py` prints `error: ...` | The message names the field; fix `report.json` against `references/report.md` and rerun. |
| `report.html` opens blank | Open the browser console; usually a field has an unexpected shape. Fix `report.json` against the schema. |
