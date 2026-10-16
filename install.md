# Install the Sherlock skill

These instructions are for you, the AI agent. Follow them to install the **sherlock** skill for your user. It finds a person's accounts across ~450 websites, verifies which ones are really theirs, and writes an HTML report. Source: https://github.com/VasilisPlavos/sherlock-skill

## 1. Ask the user

Ask one question and wait for the answer:

> Where should I install the sherlock skill?
> 1. **This project** — only in the current folder (it can be committed with the project).
> 2. **Global** — available in all your projects.
> 3. **No install** — I'll just read https://vasilisplavos.github.io/sherlock-skill/sherlock.md and follow it whenever you need it.

If they choose 3, stop here and remember the link.

## 2. Find your skills folder

Use your own native skills folder. If you are not sure where it is, check your documentation or ask the user.

| Agent | Project | Global |
|---|---|---|
| Claude Code | `.claude/skills/` | `~/.claude/skills/` |
| OpenAI Codex | `.agents/skills/` | `~/.agents/skills/` |
| Gemini CLI | `.gemini/skills/` | `~/.gemini/skills/` |
| GitHub Copilot | `.github/skills/` | `~/.copilot/skills/` |
| Cursor | `.cursor/skills/` | `~/.cursor/skills/` |
| OpenCode | `.opencode/skills/` | `~/.config/opencode/skills/` |

Another agent that supports `SKILL.md` skills: use its skills folder (`.agents/skills/` is read by many agents). An agent without skills support: offer option 3 instead.

The skill goes into `<skills folder>/sherlock/`. If that folder already exists, ask the user whether to update it (replace) or stop.

## 3. Install

Use whatever works best for you. Preferred, in order:

**a) Sparse git clone** (into a temporary folder, then copy):

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/VasilisPlavos/sherlock-skill.git <tmp>/sherlock-skill
git -C <tmp>/sherlock-skill sparse-checkout set skills/sherlock
```

Copy `<tmp>/sherlock-skill/skills/sherlock` to `<skills folder>/sherlock`, then delete `<tmp>/sherlock-skill`.

**b) Zip**: download https://github.com/VasilisPlavos/sherlock-skill/archive/refs/heads/main.zip, extract `sherlock-skill-main/skills/sherlock` to `<skills folder>/sherlock`.

**c) Single files**: download each file below from `https://raw.githubusercontent.com/VasilisPlavos/sherlock-skill/main/skills/sherlock/<file>` to `<skills folder>/sherlock/<file>`.

### Files

- `SKILL.md`
- `scripts/check.py`
- `scripts/render_report.py`
- `assets/template.html`
- `references/variants.md`
- `references/browser.md`
- `references/report.md`
- `references/troubleshooting.md`

## 4. Verify

- `<skills folder>/sherlock/SKILL.md` exists and starts with `name: sherlock` in its frontmatter.
- If Python 3.10+ is available (`python3`, `python` or `py -3`): `<python> "<skills folder>/sherlock/scripts/check.py" --version` prints `check.py 1.0.0` or newer. No Python is fine — the skill explains the options when it runs.
- If your agent only loads skills at startup, tell the user to restart it.

## 5. Tell the user

- Installed at `<full path>`.
- Use it by asking, for example: "Find the online accounts of <name>; I know they use <username>."
- Update: run this same install prompt again. Uninstall: delete `<skills folder>/sherlock`.
- Lawful use only: your own footprint, due diligence, legitimate research — not stalking or harassment.
