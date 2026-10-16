"""Generate standalone/sherlock.md from standalone/sherlock.src.md and copy published files into site/.

Placeholders are whole lines of the form {{file:<path relative to the repo root>}}.
Usage: py -3 tools/build_standalone.py [--check]
"""
import argparse, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLACEHOLDER = re.compile(r"^\{\{file:([^}]+)\}\}$")


class BuildError(Exception):
    pass


def read_text(path):
    """Text with LF line endings, so Windows (autocrlf) and Linux checkouts compare equal."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return f.read().replace("\r\n", "\n")


def expand(src_text, root):
    out = []
    for line in src_text.splitlines(keepends=True):
        m = PLACEHOLDER.match(line.rstrip("\n"))
        if not m:
            out.append(line)
            continue
        rel = m.group(1).strip()
        try:
            body = read_text(os.path.join(root, rel))
        except OSError as e:
            raise BuildError(f"{rel}: {e}")
        if "EOF" in body.split("\n"):
            raise BuildError(f"{rel} contains a line 'EOF', which would end the heredoc early")
        out.append(body if body.endswith("\n") else body + "\n")
    return "".join(out)


def outputs(root):
    try:
        standalone = expand(read_text(os.path.join(root, "standalone", "sherlock.src.md")), root)
        install = read_text(os.path.join(root, "install.md"))
    except OSError as e:
        raise BuildError(str(e))
    return {"standalone/sherlock.md": standalone, "site/sherlock.md": standalone, "site/install.md": install}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--check", action="store_true", help="write nothing; exit 1 if a generated file is stale")
    p.add_argument("--root", default=ROOT)
    args = p.parse_args(argv)
    try:
        files = outputs(args.root)
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    stale = []
    for rel, text in files.items():
        path = os.path.join(args.root, *rel.split("/"))
        try:
            current = read_text(path)
        except OSError:
            current = None
        if current == text:
            continue
        stale.append(rel)
        if not args.check:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
    if args.check and stale:
        print("stale: " + ", ".join(stale) + " (run tools/build_standalone.py)", file=sys.stderr)
        return 1
    print(("wrote: " + ", ".join(stale)) if stale and not args.check else "up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
