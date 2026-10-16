"""Render <OUT>/report.json into <OUT>/report.html using the report template. Python stdlib only."""
import argparse, base64, csv, datetime, json, os, re, sys, time, urllib.request

__version__ = "1.1.0"
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


def embed_photo(data, proxy=None):
    """Embed the photo: CDN links (LinkedIn, Instagram, ...) expire, and a remote image pings its site on every open.
    With `proxy`, the download goes through it, like check.py's requests."""
    subject = data.get("subject") or {}
    photo = subject.get("photo")
    if not (isinstance(photo, str) and photo.startswith(("http://", "https://"))):
        return
    try:
        req = urllib.request.Request(photo, headers={"User-Agent": UA})
        handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
        with urllib.request.build_opener(*handlers).open(req, timeout=15) as r:
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
    p.add_argument("--proxy", help="http(s) proxy for the photo download; use the same one as check.py")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = p.parse_args(argv)
    try:
        data = load_report(os.path.join(args.out, "report.json"))
        validate(data)
        fill_method(data, args.out)
        embed_photo(data, args.proxy)
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
