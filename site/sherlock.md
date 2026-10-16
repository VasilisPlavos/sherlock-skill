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

PY=""; OLD=""
for c in python3 python "py -3"; do
  if $c -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then PY="$c"; break; fi
  [ -z "$OLD" ] && v=$($c -c 'import platform; print(platform.python_version())' 2>/dev/null) && OLD="$c = Python $v"
done
echo "$PY" > "$WORK/py"
[ -n "$PY" ] && $PY --version || echo "No Python 3.10+ found${OLD:+ (found: $OLD)}"
```

**Shell variables do not survive between tool calls.** Every later snippet therefore starts by restoring them — keep that first line, and run every snippet from the same directory (paths are relative to it). `$PY` stays unquoted so `py -3` works.

No Python → never install on your own. Offer the user:

- **Install it** (their approval): Windows `winget install -e --id Python.Python.3.12` (per-user, no admin; open a new shell afterwards), Debian `apt-get install -y python3`, macOS `brew install python`.
- **Continue without Python**: skip step 3 (no bulk check); find accounts via web search and the browser checks in step 4; build the report by hand as described in step 6. The report states that the bulk check was not run.

Only an older Python (below 3.10) → tell the user which one, and offer: install a current Python (their approval); try the old one anyway; adapt a copy of the script to run on it (the SHA-256 check in step 3 then reports a mismatch, which is expected); or continue without the bulk check. To use the old one, write its command to `"$WORK/py"` (e.g. `echo python3 > "$WORK/py"`).

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

Needs `$PY`; skipped when the user chose to continue without Python.

Each file this guide writes is followed by a check line: it proves the file is exactly the code this guide shipped with (SHA-256). If it prints `error: ... was not written verbatim`, write that file again exactly as shown and rerun the snippet. Without Python, skip the check lines.

Write the checker once:

```bash
OUT="osint/bill-gates"; WORK="$OUT/.work"; PY=$(cat "$WORK/py")
cat > "$WORK/check.py" <<'EOF'
"""Check usernames against Sherlock's site manifest. Python stdlib only."""
import argparse, csv, functools, json, os, queue, re, secrets, signal, string, sys, time
import urllib.error, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, wait

__version__ = "1.1.0"

MANIFEST = "https://data.sherlockproject.xyz"
FALLBACK = "https://raw.githubusercontent.com/sherlock-project/sherlock/master/sherlock_project/resources/data.json"
EXCLUSIONS = "https://raw.githubusercontent.com/sherlock-project/sherlock/refs/heads/exclusions/false_positive_exclusions.txt"
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:129.0) Gecko/20100101 Firefox/129.0"
WAF = [  # bot-challenge fingerprints: a hit means "blocked", not "exists"
    ".loading-spinner{visibility:hidden}body.no-js .challenge-running{display:none}",  # Cloudflare
    '<span id="challenge-error-text">',                                               # Cloudflare
    "AwsWafIntegration.forceRefreshToken",                                            # AWS CloudFront
    '{return l.onPageView}}),Object.defineProperty(r,"perimeterxIdentifiers",{enumerable:',  # PerimeterX
]
HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")  # valid as a subdomain
SEPARATOR = re.compile(r"[\W_]+")  # anything but letters/digits, in any script


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # surface the 3xx as an HTTPError instead of following it


class FollowRedirects(urllib.request.HTTPRedirectHandler):
    """Follows 308 like 307 on every Python (urllib only does so from 3.11): '/user/x' -> '/user/x/'."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, 307 if code == 308 else code, msg, headers, newurl)

    http_error_308 = urllib.request.HTTPRedirectHandler.http_error_302


@functools.lru_cache(maxsize=None)
def opener(proxy, no_redirect=False):
    """Built once per (proxy, redirect mode) and shared by all threads."""
    handlers = [NoRedirect] if no_redirect else [FollowRedirects]
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    return urllib.request.build_opener(*handlers)


def fetch(url, proxy=None, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with opener(proxy).open(req, timeout=timeout) as r:
        return r.read().decode("utf-8-sig", "replace")


def fill(obj, user):
    if isinstance(obj, str):
        return obj.replace("{}", user)
    if isinstance(obj, dict):
        return {k: fill(v, user) for k, v in obj.items()}
    if isinstance(obj, list):
        return [fill(v, user) for v in obj]
    return obj


def load_sites(args):
    if args.data:
        with open(args.data, encoding="utf-8-sig") as f:
            data = json.load(f)
    else:
        data = None
        for url in (MANIFEST, FALLBACK):
            try:
                data = json.loads(fetch(url, args.proxy))
                break
            except Exception as e:
                print(f"warning: site list unavailable at {url}: {e}", file=sys.stderr)
        if data is None:
            sys.exit("error: could not download the site list; pass a saved copy with --data data.json")
    data.pop("$schema", None)
    excluded = set()
    if not args.site and not args.data:  # --site overrides exclusions; --data means offline
        try:
            excluded = {l.strip() for l in fetch(EXCLUSIONS, args.proxy, 10).splitlines() if l.strip()}
        except Exception:
            print("warning: exclusions list unavailable", file=sys.stderr)
    only = {s.lower() for s in args.site}
    sites = {}
    for name, info in data.items():
        if not isinstance(info, dict) or "url" not in info or "errorType" not in info:
            continue
        if only:
            if name.lower() in only:
                sites[name] = info
        elif name not in excluded and (args.nsfw or not info.get("isNSFW")):
            sites[name] = info
    return sites


def allowed(info, user):
    """False if the site cannot have this username: its regexCheck fails, or the name goes into
    the hostname ({}.example.com) and is not a valid subdomain label (e.g. contains '.' or '_')."""
    rx = info.get("regexCheck")
    if rx and not re.search(rx, user):
        return False
    templates = (info["url"], info.get("urlProbe") or info["url"])
    if any("{}" in urllib.parse.urlsplit(t).netloc for t in templates) and not HOST_LABEL.match(user):
        return False
    return True


def probe(site, info, user, args):
    """Never raises: a malformed site entry in the live list must not stop the whole run."""
    row = {"username": user, "site": site, "url": "", "status": "", "http": "", "ms": "", "context": ""}
    try:
        return check(info, user, args, row)
    except Exception as e:
        row.update(status="UNKNOWN", context=f"site entry error: {type(e).__name__}: {e}"[:200])
        return row


def check(info, user, args, row):
    quoted = urllib.parse.quote(user, safe="")  # non-ASCII names (josé, γιώργος) must be percent-encoded
    row["url"] = fill(info["url"], quoted)
    if not allowed(info, user):
        row["status"] = "ILLEGAL"  # site cannot have this username: not requested
        return row
    types = info["errorType"]
    types = [types] if isinstance(types, str) else types
    method = info.get("request_method") or ("HEAD" if types == ["status_code"] else "GET")
    headers = {"User-Agent": UA, **info.get("headers", {})}
    data = None
    if info.get("request_payload") is not None:
        data = json.dumps(fill(info["request_payload"], user)).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(fill(info.get("urlProbe") or info["url"], quoted),
                                 data=data, headers=headers, method=method)
    start = time.monotonic()
    try:
        with opener(args.proxy, "response_url" in types).open(req, timeout=args.timeout) as r:
            code, body = r.status, r.read(2_000_000)
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            body = e.read(2_000_000)
        except Exception:
            body = b""
    except Exception as e:
        row.update(status="UNKNOWN", context=f"{type(e).__name__}: {e}"[:200])
        return row
    row.update(http=code, ms=int((time.monotonic() - start) * 1000))
    text = body.decode("utf-8", "replace")
    codes = info.get("errorCode") or []
    codes = [codes] if isinstance(codes, int) else codes
    # Blocked or broken answers say nothing about the profile (HEAD bodies are empty, so check codes too).
    if code not in codes and (code in (403, 429) or code >= 500):
        row.update(status="WAF", context=f"blocked or failing: HTTP {code}")
        return row
    if any(w in text for w in WAF):
        row.update(status="WAF", context="bot challenge page")
        return row
    if not types or not set(types) <= {"message", "status_code", "response_url"}:
        row.update(status="UNKNOWN", context=f"unknown errorType {types}")
        return row
    status = None
    if "message" in types:  # only a normal page can be a profile; an error text in it means "no such user"
        msgs = info.get("errorMsg") or []
        msgs = [msgs] if isinstance(msgs, str) else msgs
        ok = 200 <= code < 300 and not any(m in text for m in msgs)
        status = "CLAIMED" if ok else "AVAILABLE"
    if "status_code" in types and status != "AVAILABLE":
        status = "AVAILABLE" if code in codes or not 200 <= code < 300 else "CLAIMED"
    if "response_url" in types and status != "AVAILABLE":  # redirects are off: 2xx means a real page
        status = "CLAIMED" if 200 <= code < 300 else "AVAILABLE"
    row["status"] = status
    return row


def shape(user):
    """Some sites answer differently for names with '.', '_' or '-', so calibrate per separator set."""
    return "".join(sorted(set("".join(SEPARATOR.findall(user)))))


def random_like(user, info, keep_first=False):
    """A random username with the same separators as `user` that the site allows (None if impossible).
    keep_first keeps the first word: 'bill.gates' -> 'bill.qzwxvkpl'."""
    parts = re.split(f"({SEPARATOR.pattern})", user)
    first = next((i for i, p in enumerate(parts) if p and not SEPARATOR.fullmatch(p)), None)
    for grow in (True, False):  # longer random parts are safer from real accounts; fall back to same length
        u = "".join(p if not p or SEPARATOR.fullmatch(p) or (keep_first and i == first) else
                    "".join(secrets.choice(string.ascii_lowercase) for _ in range(max(len(p), 8) if grow else len(p)))
                    for i, p in enumerate(parts))
        try:
            if allowed(info, u):
                return u
        except Exception:  # malformed site entry (bad regexCheck, ...): no control request
            return None
    return None


def plan_calibration(users, sites):
    """(site, shape) -> random username to probe. Per pair, the first username of that shape the site can
    mimic: one it cannot (e.g. too long for its regexCheck) must not leave the shape uncalibrated."""
    plan = {}
    for s, info in sites.items():
        for u in users:
            key = (s, shape(u))
            if key not in plan and (ru := random_like(u, info)):
                plan[key] = ru
    return plan


def track(jobs, rows, calibration=(), on_claimed=None):
    """Collect results as they finish: potential hits live, progress + ETA every 5 s (stderr).
    Progress counts calibration requests too. Waits in 1 s slices so Ctrl-C / SIGTERM interrupts promptly.
    Finished futures arrive through a queue: re-waiting on thousands of pending futures each time is O(n^2)."""
    job_set = set(jobs)
    everything = job_set | set(calibration)
    total, finished, hits, start, last = len(everything), 0, 0, time.monotonic(), 0.0
    finished_q = queue.Queue()
    for f in everything:
        f.add_done_callback(finished_q.put)
    while finished < total:
        try:
            done = [finished_q.get(timeout=1)]
        except queue.Empty:
            done = []
        finished += len(done)
        for job in done:
            if job not in job_set or job.cancelled():
                continue
            row = job.result()
            rows.append(row)
            if row["status"] == "CLAIMED":
                hits += 1
                print(f"[?] {row['username']:<20} {row['site']:<22} {row['url']}", flush=True)
                if on_claimed:
                    on_claimed(row)
        now = time.monotonic()
        if now - last >= 5 or finished == total:
            last, n = now, finished
            rate = n / max(now - start, 0.001)
            eta = int((total - n) / rate) if n else None
            print(f"progress {n}/{total} ({n * 100 // total}%)  {rate:.0f} req/s  "
                  f"ETA {'?' if eta is None else f'{eta // 60}m{eta % 60:02d}s'}  potential findings {hits}",
                  file=sys.stderr, flush=True)


def collect_finished(jobs, rows):
    """After an interrupt: add the jobs that finished but were not collected yet. Returns how many."""
    have = {id(r) for r in rows}
    new = [j.result() for j in jobs if j.done() and not j.cancelled() and id(j.result()) not in have]
    rows.extend(new)
    return len(new)


def calibration_claimed(calib, site, sh):
    f = calib.get((site, sh))
    return bool(f and f.done() and not f.cancelled() and f.result()["status"] == "CLAIMED")


def settle(rows, rechecks, calib, handled, interrupted):
    """Final statuses after the run. A hit stays CLAIMED only if its calibration and (for names with
    separators) its prefix recheck both completed and passed. Returns how many hits moved to UNKNOWN."""
    unverified = 0

    def unconfirm(r, why):
        nonlocal unverified
        if r["status"] == "CLAIMED":  # each hit counts once
            r.update(status="UNKNOWN", context=why)
            unverified += 1

    for r, ru, f in rechecks:
        if not f.done() or f.cancelled():
            unconfirm(r, "interrupted before the prefix recheck")
        elif (status := f.result()["status"]) == "CLAIMED":
            if r["status"] == "CLAIMED":
                r.update(status="UNRELIABLE", context=f"site also 'finds' {ru}")
        elif status != "AVAILABLE":
            unconfirm(r, f"prefix recheck inconclusive ({status})")
    for r in rows:
        if r["status"] in ("CLAIMED", "AVAILABLE") and calibration_claimed(calib, r["site"], shape(r["username"])):
            r.update(status="UNRELIABLE", context="random username of the same shape also reported as existing")
    if interrupted:
        for r in rows:
            f = calib.get((r["site"], shape(r["username"])))
            if f and (not f.done() or f.cancelled()):
                unconfirm(r, "interrupted before calibration")
            elif shape(r["username"]) and id(r) not in handled:
                unconfirm(r, "interrupted before the prefix recheck")
    return unverified


def findings_note(interrupted, checked, total, unverified):
    moved = f"{unverified} unconfirmed hits moved to UNKNOWN" if unverified else ""
    if interrupted:
        return f" PARTIAL: {checked}/{total} checked" + (f", {moved}" if moved else "")
    return f" {moved}" if moved else ""


def interrupt(*_):
    raise KeyboardInterrupt


def read_usernames(path):
    """One username per line; UTF-8 (with or without BOM) or UTF-16 with BOM (PowerShell 5.1 '>')."""
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16").splitlines()
    return raw.decode("utf-8-sig").splitlines()


def init_workdir(out_dir):
    """Create <out_dir>/.work and record the run's start time once (used for the report's duration)."""
    work = os.path.join(out_dir, ".work")
    os.makedirs(work, exist_ok=True)
    started = os.path.join(work, "started")
    if not os.path.exists(started):
        with open(started, "w", encoding="utf-8") as f:
            f.write(str(int(time.time())))
    return started


def main():
    started = time.monotonic()
    for stream in (sys.stdout, sys.stderr):  # Windows defaults to cp1252: non-ASCII names would crash print()
        stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("usernames", nargs="*", help="usernames to check")
    p.add_argument("-f", "--file", help="file with one username per line")
    p.add_argument("--out", default="results.csv")
    p.add_argument("--data", help="local data.json instead of the live manifest")
    p.add_argument("--site", action="append", default=[], help="only this site (repeatable)")
    p.add_argument("--nsfw", action="store_true")
    p.add_argument("--proxy", help="http(s) proxy URL, e.g. http://127.0.0.1:8080")
    p.add_argument("--timeout", type=float, default=20)
    p.add_argument("--workers", type=int, default=20)
    p.add_argument("--append", action="store_true", help="add rows to an existing --out file")
    p.add_argument("--log", help="write progress and findings to this file (UTF-8) instead of the console")
    p.add_argument("--init", metavar="OUT", help="create OUT/.work, record the start time, and exit")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = p.parse_args()
    if args.init:
        print(init_workdir(args.init))
        return
    users = list(args.usernames)
    if args.file:
        try:
            users += read_usernames(args.file)
        except UnicodeDecodeError:
            p.error(f"{args.file} is not UTF-8; save it as UTF-8 (e.g. with your file tool, not Set-Content)")
    users = list(dict.fromkeys(u.strip().lstrip("@") for u in users if u.strip().lstrip("@")))
    if not users:
        p.error("no usernames given")
    if args.log:  # PowerShell's '>' would write UTF-16 and wrap stderr lines; write the log ourselves
        log = open(args.log, "w", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
    out_dir = os.path.dirname(os.path.abspath(args.out))
    if os.path.isdir(os.path.join(out_dir, ".work")):  # skill/standalone layout: keep the start time for the report
        init_workdir(out_dir)
    sites = load_sites(args)

    signal.signal(signal.SIGTERM, interrupt)  # POSIX: a terminated run still writes what it has
    pool = ThreadPoolExecutor(args.workers)
    # Calibration: a site that "finds" a random username of the same shape cannot be trusted.
    calib = {key: pool.submit(probe, key[0], sites[key[0]], ru, args)
             for key, ru in plan_calibration(users, sites).items()}
    jobs = [pool.submit(probe, s, i, u, args) for u in users for s, i in sites.items()]
    print(f"check.py {__version__}: {len(users)} usernames x {len(sites)} sites "
          f"(+{len(calib)} calibration requests)", file=sys.stderr)

    def claimed_by_calibration(site, sh):
        return calibration_claimed(calib, site, sh)

    # Some sites resolve 'bill.<anything>' to the account 'bill'. As each separated hit arrives, re-probe it
    # with the first word kept and the rest random; if that is "found" too, the hit means nothing.
    rechecks = []  # (row, random name, future)

    def queue_recheck(r):
        sh = shape(r["username"])
        if sh and not claimed_by_calibration(r["site"], sh):  # no separator, or site already unreliable
            ru = random_like(r["username"], sites[r["site"]], keep_first=True)
            if ru and ru != r["username"]:
                rechecks.append((r, ru, pool.submit(probe, r["site"], sites[r["site"]], ru, args)))
        handled.add(id(r))  # last: a Ctrl-C before this leaves the hit unconfirmed (see settle)

    handled = set()
    rows, interrupted = [], False
    try:
        track(jobs, rows, calib.values(), on_claimed=queue_recheck)
        pending = {f for *_, f in rechecks}
        while pending:  # 1 s slices keep Ctrl-C responsive
            _, pending = wait(pending, timeout=1)
    except KeyboardInterrupt:
        interrupted = True
        print("\ninterrupted: writing partial results (in-flight requests may take a few seconds)", file=sys.stderr)
        collect_finished(jobs, rows)
    pool.shutdown(wait=not interrupted, cancel_futures=True)

    unverified = settle(rows, rechecks, calib, handled, interrupted)
    rows.sort(key=lambda r: (r["username"], r["site"].lower()))
    fields = ["username", "site", "url", "status", "http", "ms", "context"]
    append = args.append and os.path.exists(args.out)
    with open(args.out, "a" if append else "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not append:
            w.writeheader()
        w.writerows(rows)
    print("\nFindings (after calibration):" + findings_note(interrupted, len(rows), len(jobs), unverified))
    for r in rows:
        if r["status"] == "CLAIMED":
            print(f"[+] {r['username']:<20} {r['site']:<22} {r['url']}")
    sys.stdout.flush()  # keep the findings above the totals when both go to one log
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(" ".join(f"{k}={v}" for k, v in sorted(counts.items())), file=sys.stderr)
    took = int(time.monotonic() - started)
    print(f"took {took // 60}m{took % 60:02d}s", file=sys.stderr)
    sys.exit(130 if interrupted else 0)


if __name__ == "__main__":
    main()
EOF
$PY -c 'import hashlib,sys; d=open(sys.argv[1],"rb").read().replace(b"\r\n",b"\n"); sys.exit(0 if hashlib.sha256(d).hexdigest()==sys.argv[2] else "error: "+sys.argv[1]+" was not written verbatim; write it again exactly as shown in this guide")' "$WORK/check.py" 102b1f93a751b8aac76e90c670c417bbd10099a0d4e4e77be9eb08b87f5f0004
```

Run it. It takes several minutes for ~15 variants — longer than many shell tools' default timeout — so run it **in the background** and read progress from the log. **Never kill it** (no `kill`, `taskkill` or tool-side stop): wait for it to finish. If the user wants to stop early, they press Ctrl-C themselves; the finished rows are still written.

```bash
OUT="osint/bill-gates"; WORK="$OUT/.work"; PY=$(cat "$WORK/py")
$PY "$WORK/check.py" --file "$OUT/usernames.txt" --out "$OUT/results.csv" > "$OUT/check.log" 2>&1
tail -n 3 "$OUT/check.log"
```

The log shows `[?]` potential findings as they arrive and, every 5 s, `progress 2140/7200 (30%)  43 req/s  ETA 1m58s  potential findings 6` — relay the ETA to the user. Potential findings can still turn out `UNRELIABLE`; the final `[+]` list after "Findings (after calibration)" is the one to use. Hits that could not be fully verified (a recheck that was blocked or failed, or a run stopped with Ctrl-C) are moved to `UNKNOWN`, and the header says how many; only a stopped run is marked `PARTIAL`.

- `--site GitHub --site Reddit` — only those sites (also overrides exclusions/NSFW for them).
- `--nsfw` — include adult sites; only when the user asks.
- `--proxy http://host:port` — route everything, site list included, through a proxy.
- `--data data.json` — offline/pinned site list.
- `--append` — add rows to an existing `--out` file instead of replacing it (to finish a partial run with the missing usernames; see Troubleshooting).

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
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Profile report</title>
<style>
:root{--bg:#f3f5f8;--card:#fff;--text:#1c2430;--muted:#5d6977;--line:#e2e6ec;--accent:#0b7a75;--soft:#e2f2f1;--high:#1a7f37;--medium:#9a6700;--low:#8c959f}
@media (prefers-color-scheme:dark){:root{--bg:#0e1319;--card:#161d25;--text:#e6edf3;--muted:#9aa6b2;--line:#283340;--accent:#3cc1b9;--soft:#14302e;--high:#3fb950;--medium:#d29922;--low:#6e7681}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent);overflow-wrap:anywhere}
.wrap{max-width:1140px;margin:0 auto;padding:24px 16px;display:grid;grid-template-columns:330px minmax(0,1fr);gap:20px;align-items:start}
@media (max-width:860px){.wrap{grid-template-columns:minmax(0,1fr)}}
@media (min-width:861px){aside .card{position:sticky;top:16px}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;margin-bottom:20px}
h1{font-size:22px;margin:12px 0 2px}
h2{font-size:16px;margin:0 0 12px}
.muted{color:var(--muted)}
.avatar{width:96px;height:96px;border-radius:50%;object-fit:cover;background:var(--soft);color:var(--accent);display:grid;place-items:center;font-size:34px;font-weight:600}
.stats{display:flex;gap:18px;margin:14px 0;padding:12px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.stats b{display:block;font-size:20px}
.row{display:flex;align-items:center;gap:8px;padding:8px 0;border-bottom:1px solid var(--line)}
.row:last-child{border-bottom:0}
.label{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);width:62px;flex:none}
.val{flex:1;min-width:0;overflow-wrap:anywhere}
.src{font-size:12px;color:var(--muted)}
button{font:inherit;font-size:12px;border:1px solid var(--line);background:transparent;color:var(--text);border-radius:6px;padding:3px 9px;cursor:pointer;flex:none}
button:hover{border-color:var(--accent);color:var(--accent)}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.chip[aria-pressed=true]{background:var(--accent);border-color:var(--accent);color:#fff}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.p{border:1px solid var(--line);border-left:4px solid var(--low);border-radius:10px;padding:12px}
.p.high{border-left-color:var(--high)}.p.medium{border-left-color:var(--medium)}
.p .top{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.badge{font-size:11px;font-weight:600;text-transform:uppercase;padding:2px 6px;border-radius:4px;background:var(--soft)}
.badge.high{color:var(--high)}.badge.medium{color:var(--medium)}.badge.low{color:var(--low)}
.kv{font-size:13px;margin-top:4px}.kv span{color:var(--muted)}
.item{padding:8px 0;border-bottom:1px solid var(--line)}.item:last-child{border-bottom:0}
.tw{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase}
dl{display:grid;grid-template-columns:max-content 1fr;gap:6px 14px;margin:0}dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}
.demo{background:var(--soft);border-bottom:1px solid var(--line);padding:10px 16px;text-align:center;font-size:14px}
.credit{font-size:11px;color:var(--muted);margin-top:4px}
</style>
</head>
<body>
<div class="wrap"><aside id="side"></aside><main id="main"></main></div>
<script id="report-data" type="application/json">__REPORT_DATA__</script>
<script>
const D = JSON.parse(document.getElementById('report-data').textContent);
const arr = x => Array.isArray(x) ? x : [];
const str = v => v == null ? '' : String(v);
const S = D.subject || {}, P = arr(D.profiles), C = arr(D.contacts);
function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null) continue;
    if (k === 'class') e.className = v; else e.setAttribute(k, v);
  }
  for (const k of kids.flat(Infinity)) if (k != null && k !== '') e.append(k instanceof Node ? k : String(k));
  return e;
}
const safe = u => /^https?:\/\//i.test(str(u)) ? str(u) : null;
const link = (u, text) => safe(u) ? el('a', {href: safe(u), target: '_blank', rel: 'noopener noreferrer'}, text || safe(u)) : (text || str(u));
function copyBtn(value) {
  const v = str(value);
  const b = el('button', {type: 'button', title: 'Copy'}, 'Copy');
  b.onclick = async () => {
    try { await navigator.clipboard.writeText(v); }
    catch { const t = el('textarea'); t.value = v; document.body.append(t); t.select(); document.execCommand('copy'); t.remove(); }
    b.textContent = 'Copied'; setTimeout(() => b.textContent = 'Copy', 1200);
  };
  return b;
}
const card = (title, ...kids) => el('section', {class: 'card'}, title ? el('h2', {}, title) : null, ...kids);
const conf = p => ['high', 'medium'].includes(str(p.confidence).toLowerCase()) ? str(p.confidence).toLowerCase() : 'low';
const count = c => P.filter(p => conf(p) === c).length;
const kv = (k, v) => str(v) !== '' ? el('div', {class: 'kv'}, el('span', {}, k + ': '), str(v)) : null;

function contactValue(c) {
  const v = str(c.value);
  if (c.type === 'email') return el('a', {href: 'mailto:' + v}, v);
  if (c.type === 'phone') return el('a', {href: 'tel:' + v.replace(/[^\d+]/g, '')}, v);
  return link(v);
}
function exportBtn() {
  const b = el('button', {type: 'button'}, 'Export JSON');
  b.onclick = () => {
    const a = el('a', {href: URL.createObjectURL(new Blob([JSON.stringify(D, null, 2)], {type: 'application/json'})), download: 'report.json'});
    document.body.append(a); a.click(); a.remove();
  };
  return b;
}

const photo = /^data:image\/(png|jpeg|gif|webp);base64,/i.test(str(S.photo)) ? str(S.photo) : safe(S.photo);
const name = str(S.name), aliases = [].concat(S.aliases || []).map(str).filter(Boolean);
const initials = (name || '?').split(/\s+/).map(w => w[0] || '').join('').slice(0, 2).toUpperCase();
document.title = (name || 'Profile') + ' – report';
if (str(D.demo)) document.body.prepend(el('div', {class: 'demo', role: 'note'}, str(D.demo)));
document.getElementById('side').append(el('div', {class: 'card'},
  photo ? el('img', {class: 'avatar', src: photo, alt: '', referrerpolicy: 'no-referrer'}) : el('div', {class: 'avatar'}, initials),
  S.photo_credit ? el('div', {class: 'credit'}, str(S.photo_credit)) : null,
  el('h1', {}, name || 'Unknown'),
  aliases.length ? el('div', {class: 'muted'}, 'aka ' + aliases.join(', ')) : null,
  S.headline ? el('div', {}, str(S.headline)) : null,
  S.location ? el('div', {class: 'muted'}, str(S.location)) : null,
  el('div', {class: 'stats'},
    el('div', {}, el('b', {}, count('high')), 'High'),
    el('div', {}, el('b', {}, count('medium')), 'Medium'),
    el('div', {}, el('b', {}, P.length), 'Profiles')),
  el('h2', {}, 'Contact'),
  C.length ? C.map(c => el('div', {class: 'row'},
    el('span', {class: 'label'}, str(c.type)),
    el('div', {class: 'val'}, contactValue(c), c.source ? el('div', {class: 'src'}, 'source: ', link(c.source)) : null),
    copyBtn(c.value))) : el('div', {class: 'muted'}, 'No public contact details found.'),
  el('div', {style: 'margin-top:14px'}, exportBtn())));

const main = document.getElementById('main');
if (S.summary) main.append(card('Summary', el('p', {style: 'margin:0'}, str(S.summary))));

const grid = el('div', {class: 'grid'});
let filter = 'all';
function drawProfiles() {
  grid.replaceChildren(...P.filter(p => filter === 'all' || conf(p) === filter).map(p => el('div', {class: 'p ' + conf(p)},
    el('div', {class: 'top'}, el('strong', {}, str(p.site)), el('span', {class: 'badge ' + conf(p)}, conf(p))),
    el('div', {class: 'row'}, el('div', {class: 'val'}, link(p.url)), copyBtn(p.url)),
    kv('Username', p.username), kv('Name', p.name), kv('Bio', p.bio), kv('Location', p.location), kv('Followers', p.followers),
    p.reason ? el('div', {class: 'src', style: 'margin-top:6px'}, str(p.reason)) : null)));
}
const chips = el('div', {class: 'chips'}, ['all', 'high', 'medium', 'low'].map(f => {
  const b = el('button', {type: 'button', class: 'chip', 'aria-pressed': String(f === filter)}, f);
  b.onclick = () => { filter = f; chips.querySelectorAll('.chip').forEach(x => x.setAttribute('aria-pressed', String(x === b))); drawProfiles(); };
  return b;
}));
drawProfiles();
main.append(card('Social profiles', P.length ? [chips, grid] : el('div', {class: 'muted'}, 'No profiles found.')));

const timeline = (items, head, sub) => items.map(i => el('div', {class: 'item'}, el('strong', {}, head(i)), el('div', {class: 'muted'}, sub(i)), i.source ? el('div', {class: 'src'}, link(i.source)) : null));
const join = (...xs) => xs.map(str).filter(Boolean).join(' · ');
if (arr(D.experience).length) main.append(card('Work experience', timeline(arr(D.experience), i => join(i.title, i.org), i => str(i.period))));
if (arr(D.education).length) main.append(card('Education', timeline(arr(D.education), i => str(i.school), i => join(i.degree, i.period))));

const table = (heads, rows) => el('div', {class: 'tw'}, el('table', {}, el('thead', {}, el('tr', {}, heads.map(h => el('th', {}, h)))), el('tbody', {}, rows.map(r => el('tr', {}, r.map(c => el('td', {}, c)))))));
if (arr(D.variants).length) main.append(card('Usernames checked', table(['Username', 'Found on'], arr(D.variants).map(v => [el('span', {}, str(v.username), ' ', copyBtn(v.username)), str(v.found)]))));
if (arr(D.unchecked).length) main.append(card('Not verified (check manually)', table(['Site', 'Username', 'Status', 'URL'], arr(D.unchecked).map(u => [str(u.site), str(u.username), str(u.status), link(u.url)]))));

const M = D.method || {};
main.append(card('Methodology', el('dl', {},
  [['Date', M.date], ['Brief', M.brief], ['Browser', M.browser], ['Bulk check', M.bulk_check], ['Duration', M.duration], ['Sites', M.sites], ['Variants', M.variants]]
    .filter(([, v]) => str(v) !== '').map(([k, v]) => [el('dt', {}, k), el('dd', {}, str(v))]))));
</script>
</body>
</html>
EOF
$PY -c 'import hashlib,sys; d=open(sys.argv[1],"rb").read().replace(b"\r\n",b"\n"); sys.exit(0 if hashlib.sha256(d).hexdigest()==sys.argv[2] else "error: "+sys.argv[1]+" was not written verbatim; write it again exactly as shown in this guide")' "$WORK/template.html" bb11214c600ec3cc9adf18c746d994def10f299d50e4d40435068895fe05bf5b

cat > "$WORK/render_report.py" <<'EOF'
"""Render <OUT>/report.json into <OUT>/report.html using the report template. Python stdlib only."""
import argparse, base64, csv, datetime, json, os, re, sys, time, urllib.request

__version__ = "1.0.0"
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:129.0) Gecko/20100101 Firefox/129.0"
DEFAULT_TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "template.html")
OBJECTS = ("subject", "method")
LISTS = ("contacts", "profiles", "experience", "education", "variants", "unchecked")
CONFIDENCE = ("high", "medium", "low")


class ReportError(Exception):
    pass


def decode(raw):
    """UTF-8 (with or without BOM) or UTF-16 with BOM (PowerShell 5.1 Out-File / '>')."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def load_report(path):
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return json.loads(decode(raw))
    except UnicodeDecodeError:
        raise ReportError(f"{path} is not UTF-8; save it as UTF-8 (e.g. with your file tool, not Set-Content)")
    except json.JSONDecodeError as e:
        raise ReportError(f"invalid JSON in {path}: {e}")


def validate(data):
    """Catch the shapes that would make the page render blank, with a message that names the field."""
    if not isinstance(data, dict):
        raise ReportError("report.json must be a JSON object")
    for key in OBJECTS:
        if key in data and not isinstance(data[key], dict):
            raise ReportError(f"'{key}' must be an object, got {type(data[key]).__name__}")
    for key in LISTS:
        if key not in data:
            continue
        if not isinstance(data[key], list):
            raise ReportError(f"'{key}' must be a list, got {type(data[key]).__name__}")
        for i, item in enumerate(data[key]):
            if not isinstance(item, dict):
                raise ReportError(f"'{key}[{i}]' must be an object, got {type(item).__name__}")
    for i, p in enumerate(data.get("profiles", [])):
        if str(p.get("confidence", "")).lower() not in CONFIDENCE:
            raise ReportError(f"'profiles[{i}].confidence' must be high, medium or low, got {p.get('confidence')!r}")


def fmt_duration(seconds):
    s = max(int(seconds), 0)
    return f"{s // 3600}h{s % 3600 // 60:02d}m{s % 60:02d}s"


def read_log(path):
    """check.log as text; tolerates a UTF-16 file (PowerShell '>' redirection)."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    try:
        return decode(raw)
    except UnicodeDecodeError:
        return raw.decode("utf-8", "replace")


def bulk_check(out_dir, ran):
    text = read_log(os.path.join(out_dir, "check.log")) or ""
    took = re.findall(r"(?m)^took (\S+)\s*$", text)
    if took:
        return f"done in {took[-1]}" + (" (partial: stopped early)" if "PARTIAL:" in text else "")
    return "done" if ran else "not run"


def csv_counts(out_dir):
    try:
        with open(os.path.join(out_dir, "results.csv"), encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    except (OSError, UnicodeDecodeError):
        return None
    return len({r.get("site") for r in rows}), len({r.get("username") for r in rows})


def fill_method(data, out_dir, now=None):
    """Fill only the method fields the agent left empty."""
    now = time.time() if now is None else now
    auto = {"date": datetime.date.fromtimestamp(now).isoformat()}
    try:
        with open(os.path.join(out_dir, ".work", "started"), encoding="utf-8") as f:
            started = int(f.read().strip())
        auto["duration"] = fmt_duration(now - started) + " (including time waiting for the user)"
    except (OSError, ValueError):
        pass
    counts = csv_counts(out_dir)
    auto["bulk_check"] = bulk_check(out_dir, counts is not None)
    if counts:
        auto["sites"], auto["variants"] = counts
    method = data.setdefault("method", {})
    for key, value in auto.items():
        if method.get(key) is None or str(method[key]).strip() == "":
            method[key] = value


def embed_photo(data):
    """Embed the photo: CDN links (LinkedIn, Instagram, ...) expire, and a remote image pings its site on every open."""
    subject = data.get("subject") or {}
    photo = subject.get("photo")
    if not (isinstance(photo, str) and photo.startswith(("http://", "https://"))):
        return
    try:
        req = urllib.request.Request(photo, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            kind, body = r.headers.get_content_type(), r.read(2_000_001)
        if kind in ("image/jpeg", "image/png", "image/gif", "image/webp") and len(body) <= 2_000_000:
            subject.update(photo=f"data:{kind};base64," + base64.b64encode(body).decode(), photo_source=photo)
        else:
            print(f"warning: photo not embedded ({kind}, {len(body)} bytes); keeping the link", file=sys.stderr)
    except Exception as e:
        print(f"warning: photo not embedded ({e}); keeping the link", file=sys.stderr)


def render(data, template):
    if template.count("__REPORT_DATA__") != 1:
        raise ReportError("template must contain __REPORT_DATA__ exactly once")
    blob = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")  # no '<' at all: page text can't break out
    return template.replace("__REPORT_DATA__", blob)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # Windows defaults to cp1252
        stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description="Render <OUT>/report.json into <OUT>/report.html.")
    p.add_argument("out", help="output folder, e.g. osint/bill-gates")
    p.add_argument("--template", default=DEFAULT_TEMPLATE, help="report template (default: the skill's assets)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = p.parse_args(argv)
    try:
        data = load_report(os.path.join(args.out, "report.json"))
        validate(data)
        fill_method(data, args.out)
        embed_photo(data)
        with open(args.template, encoding="utf-8-sig") as f:
            html = render(data, f.read())
        dest = os.path.join(args.out, "report.html")
        with open(dest, "w", encoding="utf-8", newline="\n") as f:
            f.write(html)
    except (ReportError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(os.path.abspath(dest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
EOF
$PY -c 'import hashlib,sys; d=open(sys.argv[1],"rb").read().replace(b"\r\n",b"\n"); sys.exit(0 if hashlib.sha256(d).hexdigest()==sys.argv[2] else "error: "+sys.argv[1]+" was not written verbatim; write it again exactly as shown in this guide")' "$WORK/render_report.py" d07f1d718f56918b03f7d3c05c76aebf4df2bd23168aff5426aa6a21ffe05879
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
| `$PY` is empty | No working Python 3.10+. Offer install (with approval) or continue without it — see step 1 (an older Python has more options there). Stdlib only, no pip packages needed. |
| `$WORK` / `$OUT` empty, files written to `/` | The snippet ran without its first line; shell variables don't persist between tool calls. Re-run it with the restore line. |
| `mkdir`, `<<'EOF'` or `command -v` fail | Not a bash shell (PowerShell/cmd). Use Git Bash/WSL, or translate — see the top of this guide. |
| Windows: "Python was not found ... Microsoft Store" | A Store stub was picked up; re-run the detection loop in step 1, which tests by running. |
| Check stopped early (`PARTIAL` in the log) | `results.csv` holds the finished rows. Usernames are checked one after another, so the missing usernames are those with no rows (or fewer rows than the rest). Put only those in `"$OUT/usernames-rest.txt"` and run `--file "$OUT/usernames-rest.txt" --out "$OUT/results.csv" --append > "$OUT/check-rest.log" 2>&1` in the background. The report reads only `check.log`, so set `method.bulk_check` yourself (both run times). |
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
