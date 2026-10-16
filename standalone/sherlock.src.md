# Username Search Guide (Sherlock-style, no Sherlock)

Finds a person's accounts across ~450 sites from a free-form brief ("Bill Gates, the Microsoft co-founder; I know he uses `thisisbillgates`, maybe `billgates` elsewhere"). Reuses [Sherlock](https://github.com/sherlock-project/sherlock)'s site manifest as data, not its code. Everything runs on the Python standard library — nothing to install.

Snippets are bash. On Windows use Git Bash or WSL if available; otherwise translate them to PowerShell (heredocs → write the file with your file tool).

Phases: **brief → variants → bulk existence check → browser checks → identity verification → HTML report**. Steps 1, 2 and 4 are gates: present, then **stop and wait for the user's answer**.

Outputs, in `"$OUT"` = `osint/<subject>` under the current directory:

- `results.csv` — every request: variant, site, URL, status
- `report.json` — the findings (schema in step 6)
- `report.html` — self-contained, RocketReach-style profile page; every field visible and copyable, JSON export

## 1. Brief and draft research (gate)

1. Sort the user's description into: **names** (native script and any spellings given), **known usernames**, **platforms where already seen**, **other context** (city, job, age, school, photo).
2. If the brief is thin, do a quick draft search first: web-search the name and each known username, open the profiles the user mentioned, collect extra handles, links and facts.
3. Write back a short understanding: what the user said vs. what you assume or discovered (with sources). Ask the questions that matter, **one at a time** (e.g. "Is the Bill Gates in Seattle, the Microsoft co-founder, the right one?"), and stop. Continue only once the user confirms the brief.

Set the output folder (short ASCII slug of the subject) and find a working Python. Run each candidate instead of only locating it: on Windows `python`/`python3` are often Microsoft Store stubs that exist on PATH but just ask to install.

```bash
OUT="osint/bill-gates"; WORK="$OUT/.work"; mkdir -p "$WORK"
date +%s > "$WORK/started"   # for the total duration in the report

PY=""
for c in python3 python "py -3"; do
  $c -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1 && { PY="$c"; break; }
done
echo "$PY" > "$WORK/py"
[ -n "$PY" ] && $PY --version || echo "No Python 3.9+ found"
```

**Shell variables do not survive between tool calls.** Every later snippet therefore starts by restoring them — keep that first line, and run every snippet from the same directory (paths are relative to it). `$PY` stays unquoted so `py -3` works.

No Python → never install on your own. Offer the user:

- **Install it** (their approval): Windows `winget install -e --id Python.Python.3.12` (per-user, no admin; open a new shell afterwards), Debian `apt-get install -y python3`, macOS `brew install python`.
- **Continue without Python**: skip step 3 (no bulk check); find accounts via web search and the browser checks in step 4; build the report by hand as described in step 6. The report states that the bulk check was not run.

## 2. Username variants (gate)

Generate candidates by reasoning, not blind brute force:

| Source | Rules |
|---|---|
| Known username | as-is; separators `_` `.` `-` or none between word parts; common affixes (`real`, `the`, `official`, `thisis`, `_` prefix/suffix, `1`); a year only if one is known (birth/graduation) |
| Full name | first+last, last+first, initial+last, first+initial; each with `_` `.` `-` or none; diminutives/formal forms (William → bill, will, billy; Γεώργιος/Γιώργος → georgios, giorgos, george) |
| Non-Latin names | every plausible transliteration (Greek: β→v/b, η→i/h/e, ω→o/w, υ→y/i, ου→ou/u, χ→ch/h/x, θ→th, φ→f/ph, ψ→ps, ξ→x/ks, γγ→ng/gg, μπ→b/mp, ντ→d/nt) |

Rank by likelihood (known handles first) and present the top ~15 for approval. Every variant multiplies requests by ~450, so prune hard. Save the approved list, one per line, without a leading `@`:

```bash
OUT="osint/bill-gates"; WORK="$OUT/.work"; PY=$(cat "$WORK/py")
printf '%s\n' thisisbillgates billgates bill.gates bill_gates williamgates bgates > "$OUT/usernames.txt"
```

## 3. Bulk existence check

Needs `$PY`; skipped when the user chose to continue without Python. Write the checker once:

```bash
OUT="osint/bill-gates"; WORK="$OUT/.work"; PY=$(cat "$WORK/py")
cat > "$WORK/check.py" <<'EOF'
{{file:skills/sherlock/scripts/check.py}}
EOF
```

Run it. It takes several minutes for ~15 variants — longer than many shell tools' default timeout — so run it **in the background** and read progress from the log. **Never kill it** (no `kill`, `taskkill` or tool-side stop): wait for it to finish. If the user wants to stop early, they press Ctrl-C themselves; the finished rows are still written.

```bash
OUT="osint/bill-gates"; WORK="$OUT/.work"; PY=$(cat "$WORK/py")
$PY "$WORK/check.py" --file "$OUT/usernames.txt" --out "$OUT/results.csv" > "$OUT/check.log" 2>&1
tail -n 3 "$OUT/check.log"
```

The log shows `[?]` potential findings as they arrive and, every 5 s, `progress 2140/7200 (30%)  43 req/s  ETA 1m58s  potential findings 6` — relay the ETA to the user. Potential findings can still turn out `UNRELIABLE`; the final `[+]` list after "Findings (after calibration)" is the one to use. After a Ctrl-C the output is marked `PARTIAL` and hits that could not be fully verified are moved to `UNKNOWN`.

- `--site GitHub --site Reddit` — only those sites (also overrides exclusions/NSFW for them).
- `--nsfw` — include adult sites; only when the user asks.
- `--proxy http://host:port` — route everything, site list included, through a proxy.
- `--data data.json` — offline/pinned site list.
- `--append` — add rows to an existing `--out` file instead of replacing it (to finish a partial run with `--site`).

Statuses:

| Status | Meaning |
|---|---|
| `CLAIMED` | a profile page answered |
| `AVAILABLE` | no profile |
| `ILLEGAL` | the site cannot have this username (its rules, or not a valid subdomain); not requested |
| `WAF` | blocked: bot challenge or HTTP 403/429/5xx — recheck in a browser |
| `UNKNOWN` | network error or timeout |
| `UNRELIABLE` | the site also "found" a random username of the same shape, or the same first word with a random rest (`bill.qzwxvkpl`) — ignore its answer |

`CLAIMED` means "the site answered differently than for a missing user", not "this is the person". That is step 5's job.

## 4. Browser checks (gate)

Plain HTTP misses login-walled platforms and anything that returned `WAF`. Treat these as browser-only regardless of the CSV: **LinkedIn, Facebook, Instagram, X/Twitter, TikTok, Threads** — and use their **people search by name**, not only username URLs (LinkedIn slugs are often `first-last-1a2b3c`).

First find what is available — do not ask before looking:

```bash
OUT="osint/bill-gates"; WORK="$OUT/.work"; PY=$(cat "$WORK/py")
for b in chromium chromium-browser google-chrome google-chrome-stable firefox msedge; do command -v "$b"; done
for p in "/c/Program Files/Google/Chrome/Application/chrome.exe" "/c/Program Files (x86)/Google/Chrome/Application/chrome.exe" \
         "/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" "/c/Program Files/Mozilla Firefox/firefox.exe" \
         "/Applications/Google Chrome.app" "/Applications/Firefox.app" "/Applications/Microsoft Edge.app"; do
  [ -e "$p" ] && echo "$p"
done
$PY -c "import playwright; print('python playwright')" 2>/dev/null
npx --no-install playwright --version 2>/dev/null
```

Also check your own tool list for browser tools (names containing `chrome`, `browser`, `playwright`, `puppeteer`, `browseros`). An installed desktop browser alone is not automatable; it matters for extension-based tools and for Playwright's `chrome`/`msedge` channels.

Present **only what you found**, with trade-offs, and let the user choose:

| Option | Logged in? | Trade-off |
|---|---|---|
| Browser extension tools in the user's own browser | yes, as the user | best coverage; lookups come from the user's real accounts |
| Dedicated agent browser (e.g. BrowserOS) | whatever the user signed into it | separate profile; same visibility caveat if signed in |
| Playwright / headless browser | no (unless the user logs in once in a persistent profile) | clean; login walls stay closed |
| None / skip | — | report lists these sites as unchecked |

Tell the user before choosing: **signed-in visits can be visible to the person** (LinkedIn's "Who viewed your profile" unless private mode is on; story/profile views elsewhere). Never log in, enter credentials or solve CAPTCHAs on the user's behalf — ask them to do it.

Record each browser finding as an extra `CLAIMED` (site, URL, username) for step 5.

## 5. Identity verification (phase 2)

Open **only `CLAIMED` profiles** (CSV + browser). For each, read the display name, bio, location, links, follower count, photo and any work/education. Without a browser, the page's `og:title` / `og:description` / `og:image` meta tags often suffice.

Score against the confirmed brief:

- **high** — name and at least one independent detail match (city, employer, links to a known profile, same photo)
- **medium** — name or handle matches, nothing contradicts
- **low** — handle only, or details conflict

Give a one-line reason for every score. Collect public contact details (emails, phones, websites) **with their source URL**; never guess emails from name patterns.

New handles found in profiles (e.g. linked accounts) → propose another round from step 2, with the user's approval.

## 6. Report

Write `"$OUT/report.json"` with this shape (omit what you don't have; arrays may be empty; values are strings unless shown as numbers):

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

`render_report.py` fills the run details you leave empty in `method`: `date`, `duration` (from `$WORK/started`), `bulk_check` (from the `took` line of `check.log`), `sites` and `variants` (from `results.csv`). Write `brief` and `browser` yourself.

`subject.photo` is the image URL from the most confident profile that has a real photo (avatar or `og:image`; skip generated placeholders such as GitHub identicons, Gravatar defaults or initials avatars); the render step downloads it once and embeds it in `report.html`, so the report keeps its photo offline and after the link expires (the URL is kept as `photo_source`). `photo_credit` is optional text shown under the photo (author/license).

`unchecked` gets one entry per site, not per row: blocked sites usually block every variant, so list them together (`"username": "billgates, bill.gates"`, `"url"` = the site's main URL).

Write the template and the renderer, then render:

```bash
OUT="osint/bill-gates"; WORK="$OUT/.work"; PY=$(cat "$WORK/py")
cat > "$WORK/template.html" <<'EOF'
{{file:skills/sherlock/assets/template.html}}
EOF

cat > "$WORK/render_report.py" <<'EOF'
{{file:skills/sherlock/scripts/render_report.py}}
EOF
$PY "$WORK/render_report.py" "$OUT" --template "$WORK/template.html"
```

Without Python: write `template.html` as above with your file tool, then create `report.html` from it yourself — replace `__REPORT_DATA__` with the `report.json` content, with every `<` written as `\u003c` (backslash, u, 0, 0, 3, c). Embed the photo as a `data:image/...;base64,` URI if you have a base64 tool (`base64 -w0`, PowerShell `[Convert]::ToBase64String`), else keep the link. Set `"method": {"bulk_check": "not run (no Python)", ...}` so the report says so.

Tell the user the full path to `report.html` and summarize: high-confidence profiles, contacts found, what could not be verified, and how long it took (bulk check and total).

## 7. Clean up

```bash
OUT="osint/bill-gates"; rm -rf "$OUT/.work"
```

## Troubleshooting

| Symptom | Check / fix |
|---|---|
| `$PY` is empty | No working Python 3.9+. Offer install (with approval) or continue without it — see step 1. Stdlib only, no pip packages needed. |
| `$WORK` / `$OUT` empty, files written to `/` | The snippet ran without its first line; shell variables don't persist between tool calls. Re-run it with the restore line. |
| `mkdir`, `<<'EOF'` or `command -v` fail | Not a bash shell (PowerShell/cmd). Use Git Bash/WSL, or translate — see the top of this guide. |
| Windows: "Python was not found ... Microsoft Store" | A Store stub was picked up; re-run the detection loop in step 1, which tests by running. |
| Check stopped early (`PARTIAL` in the log) | `results.csv` holds the finished rows. Finish only the missing sites with `--site X --site Y --append` (same `--out`), in the background. |
| Manifest download fails | Both URLs blocked/offline → pass a saved copy with `--data data.json`, or `--proxy`. |
| Many `UNKNOWN` (timeouts) | Slow network: `--timeout 40`; lower `--workers`. |
| Many `WAF` (403/429) | Rate-limited or bot-blocked: lower `--workers` (e.g. 5), wait, or use `--proxy`; recheck the important ones in a browser. |
| Obvious false positive | Site changed its error page. Mark it low/ignore; calibration (`UNRELIABLE`) only catches sites that claim *any* name of that shape. |
| Browser lands on a login wall | Ask the user to sign in themselves, or list the site under "Not verified". |
| Render step prints `error: ...` | The message names the field; fix `report.json` against the schema in step 6 and rerun. |
| `report.html` opens blank | Open the browser console; usually a field has an unexpected shape (e.g. an object where text is expected). Fix `report.json` against the schema. |

## Notes

- Only for lawful purposes: checking your own footprint, due diligence, research with a legitimate reason. Decline requests that look like stalking or harassing a private individual.
- Report only what pages actually show, each fact with its source; never invent contact details or merge people without evidence.
- Keep `--workers` at 20 or lower: each run already sends thousands of requests from the user's IP.
- The site list is fetched live each run, so fixes from the Sherlock project arrive automatically.
