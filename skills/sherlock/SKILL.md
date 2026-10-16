---
name: sherlock
description: Find a person's accounts across ~450 websites from a free-form description (name, known usernames, context), verify which ones really belong to them, and produce a self-contained HTML profile report. Uses Sherlock's site list with a Python-stdlib checker. Use when the user asks to find someone's social media or online accounts, search a username across sites, do OSINT on a person, check their own digital footprint, or mentions Sherlock.
license: MIT
---

# Sherlock: find a person's accounts

Finds a person's accounts across ~450 sites from a free-form brief ("Bill Gates, the Microsoft co-founder; I know he uses `thisisbillgates`, maybe `billgates` elsewhere"), checks which ones are really them, and writes an HTML report. Reuses [Sherlock](https://github.com/sherlock-project/sherlock)'s site manifest as data, not its code. Python standard library only — nothing to install.

Phases: **brief → variants → bulk check → browser checks → identity verification → report**. Steps 1, 2 and 4 are gates: present, then **stop and wait for the user's answer**.

## Conventions

- `<SKILL_DIR>` — the folder that contains this `SKILL.md`. Scripts are in `<SKILL_DIR>/scripts`, details in `<SKILL_DIR>/references`.
- `<OUT>` — `osint/<slug>` under the current directory; `<slug>` is a short ASCII name for the subject (`osint/bill-gates`).
- `<PY>` — the Python command found in step 1 (`python3`, `python` or `py -3`).
- Write these out in full in every command — nothing carries over between tool calls — and quote paths. Commands are the same in bash and PowerShell unless two versions are shown. Write files (lists, JSON) with your file tool.

Outputs in `<OUT>`: `results.csv` (every request: variant, site, URL, status), `check.log`, `report.json` (the findings), `report.html` (self-contained profile page; every field copyable, JSON export).

## 1. Brief (gate)

1. Sort the user's description into: **names** (native script and any spellings given), **known usernames**, **platforms where already seen**, **other context** (city, job, age, school, photo).
2. If the brief is thin, do a quick draft search first: web-search the name and each known username, open the profiles the user mentioned, collect extra handles, links and facts.
3. Write back a short understanding: what the user said vs. what you assume or discovered (with sources). Ask the questions that matter, **one at a time** (e.g. "Is the Bill Gates in Seattle, the Microsoft co-founder, the right one?"), and stop. Continue only once the user confirms the brief.

Find a working Python 3.9+. Run each candidate instead of only locating it: on Windows `python`/`python3` are often Microsoft Store stubs that exist on PATH but just ask to install.

```bash
for c in python3 python "py -3"; do $c -c 'import sys; sys.exit(sys.version_info < (3, 9))' >/dev/null 2>&1 && { echo "$c"; break; }; done
```

```powershell
foreach ($c in 'python3', 'python', 'py -3') {
  $p = $c.Split(' ')
  try { & $p[0] $p[1..9] -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>$null } catch { continue }
  if ($LASTEXITCODE -eq 0) { $c; break }
}
```

The line printed is `<PY>`. Then create the output folder and record the start time (used for the report's duration):

    <PY> "<SKILL_DIR>/scripts/check.py" --init "<OUT>"

No Python → never install on your own. Offer the user:

- **Install it** (their approval): Windows `winget install -e --id Python.Python.3.12` (per-user, no admin; open a new shell afterwards), Debian `apt-get install -y python3`, macOS `brew install python`.
- **Continue without Python**: skip step 3; find accounts via web search and the browser checks in step 4; build the report by hand (`references/report.md`, "Without Python"). The report states that the bulk check was not run.

## 2. Variants (gate)

Generate username candidates by reasoning — rules in `references/variants.md`. Rank by likelihood (known handles first), present the top ~15 and stop. Every variant costs ~450 requests, so prune hard. Save the approved list to `<OUT>/usernames.txt`, one per line, no leading `@`.

## 3. Bulk check

Skipped when continuing without Python. It takes several minutes for ~15 variants — longer than many tools' default timeout — so run it **in the background**:

    <PY> "<SKILL_DIR>/scripts/check.py" --file "<OUT>/usernames.txt" --out "<OUT>/results.csv" --log "<OUT>/check.log"

Use `--log`, not shell redirection. **Never kill it** (no `kill`, `taskkill`, `Stop-Process` or tool-side stop): wait for it to finish. If the user wants to stop early, they press Ctrl-C themselves; the finished rows are still written.

Read progress with `tail -n 3 "<OUT>/check.log"` (PowerShell: `Get-Content "<OUT>/check.log" -Tail 3`). The log shows `[?]` potential findings as they arrive and, every 5 s, `progress 2140/7200 (30%)  43 req/s  ETA 1m58s  potential findings 6` — relay the ETA to the user. Potential findings can still turn out `UNRELIABLE`; the final `[+]` list after "Findings (after calibration)" is the one to use. Hits that could not be fully verified (a recheck that was blocked or failed, or a run stopped with Ctrl-C) are moved to `UNKNOWN`, and the header says how many; only a stopped run is marked `PARTIAL`.

- `--site GitHub --site Reddit` — only those sites (also overrides exclusions/NSFW for them).
- `--nsfw` — include adult sites; only when the user asks.
- `--proxy http://host:port` — route everything, site list included, through a proxy.
- `--data data.json` — offline/pinned site list.
- `--append` — add rows to an existing `--out` file (to finish a partial run with the missing usernames; give it its own `--log`; see `references/troubleshooting.md`).

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

Plain HTTP misses login-walled platforms and anything that returned `WAF`. Treat **LinkedIn, Facebook, Instagram, X/Twitter, TikTok, Threads** as browser-only regardless of the CSV, and use their **people search by name**, not only username URLs. Follow `references/browser.md`: find what browser tooling is available (look before asking), present only what you found with its trade-offs, warn that **signed-in visits can be visible to the person**, and stop for the user's choice. Never log in, enter credentials or solve CAPTCHAs on the user's behalf. Record each browser finding as an extra `CLAIMED` (site, URL, username).

## 5. Identity verification

Open **only `CLAIMED` profiles** (CSV + browser). For each, read the display name, bio, location, links, follower count, photo and any work/education. Without a browser, the page's `og:title` / `og:description` / `og:image` meta tags often suffice.

Score against the confirmed brief:

- **high** — name and at least one independent detail match (city, employer, links to a known profile, same photo)
- **medium** — name or handle matches, nothing contradicts
- **low** — handle only, or details conflict

Give a one-line reason for every score. Collect public contact details (emails, phones, websites) **with their source URL**; never guess emails from name patterns.

New handles found in profiles (e.g. linked accounts) → propose another round from step 2, with the user's approval.

## 6. Report

Write `<OUT>/report.json` as described in `references/report.md`, then:

    <PY> "<SKILL_DIR>/scripts/render_report.py" "<OUT>"

It checks the JSON, fills in the run details (date, duration, bulk check time, sites, variants), embeds the photo and writes `<OUT>/report.html`. On `error: ...` fix the named field and rerun.

Tell the user the full path to `report.html` and summarize: high-confidence profiles, contacts found, what could not be verified, and how long it took (bulk check and total).

## 7. Clean up

Delete `<OUT>/.work` (`rm -rf "<OUT>/.work"`; PowerShell `Remove-Item -Recurse -Force "<OUT>/.work"`).

Problems: `references/troubleshooting.md`.

## Notes

- Only for lawful purposes: checking your own footprint, due diligence, research with a legitimate reason. Decline requests that look like stalking or harassing a private individual.
- Report only what pages actually show, each fact with its source; never invent contact details or merge people without evidence.
- Keep `--workers` at 20 or lower: each run already sends thousands of requests from the user's IP.
- The site list is fetched live each run, so fixes from the Sherlock project arrive automatically.
