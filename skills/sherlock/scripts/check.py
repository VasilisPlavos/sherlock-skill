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


@functools.lru_cache(maxsize=None)
def opener(proxy, no_redirect=False):
    """Built once per (proxy, redirect mode) and shared by all threads."""
    handlers = [NoRedirect] if no_redirect else []
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
    if not set(types) <= {"message", "status_code", "response_url"}:
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
        f = calib.get((site, sh))
        return bool(f and f.done() and not f.cancelled() and f.result()["status"] == "CLAIMED")

    # Some sites resolve 'bill.<anything>' to the account 'bill'. As each separated hit arrives, re-probe it
    # with the first word kept and the rest random; if that is "found" too, the hit means nothing.
    rechecks = []  # (row, random name, future)

    def queue_recheck(r):
        sh = shape(r["username"])
        if sh and not claimed_by_calibration(r["site"], sh):  # no separator, or site already unreliable
            ru = random_like(r["username"], sites[r["site"]], keep_first=True)
            if ru and ru != r["username"]:
                rechecks.append((r, ru, pool.submit(probe, r["site"], sites[r["site"]], ru, args)))

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

    unverified = 0
    for r, ru, f in rechecks:
        if not f.done() or f.cancelled():
            if r["status"] == "CLAIMED":  # never confirmed: keep it out of the [+] list
                r.update(status="UNKNOWN", context="interrupted before the prefix recheck")
                unverified += 1
        elif f.result()["status"] == "CLAIMED":
            r.update(status="UNRELIABLE", context=f"site also 'finds' {ru}")
    for r in rows:
        if r["status"] in ("CLAIMED", "AVAILABLE") and claimed_by_calibration(r["site"], shape(r["username"])):
            r.update(status="UNRELIABLE", context="random username of the same shape also reported as existing")
    rows.sort(key=lambda r: (r["username"], r["site"].lower()))
    fields = ["username", "site", "url", "status", "http", "ms", "context"]
    append = args.append and os.path.exists(args.out)
    with open(args.out, "a" if append else "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if not append:
            w.writeheader()
        w.writerows(rows)
    note = ""
    if interrupted:
        note = f" PARTIAL: {len(rows)}/{len(jobs)} checked"
        note += f", {unverified} unconfirmed hits moved to UNKNOWN" if unverified else ""
    print("\nFindings (after calibration):" + note)
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
