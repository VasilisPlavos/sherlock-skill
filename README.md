# sherlock-skill

Find a person's accounts across ~450 websites with your AI agent. It turns a short description into username variants, checks them against [Sherlock](https://github.com/sherlock-project/sherlock)'s site list, verifies which profiles are really that person, and writes a self-contained HTML report.

Site and demo: https://vasilisplavos.github.io/sherlock-skill/

## Install as a skill

Tell your agent:

    Read https://vasilisplavos.github.io/sherlock-skill/install.md and install the sherlock skill

It asks whether to install for the current project or globally, or to use the standalone guide instead. Supported: Claude Code, OpenAI Codex, Gemini CLI, GitHub Copilot, Cursor, OpenCode, and any agent that reads `SKILL.md` skills.

## Use without installing

    Read https://vasilisplavos.github.io/sherlock-skill/sherlock.md and follow it to find the accounts of …

## Repository

- `skills/sherlock/` — the skill (`SKILL.md`, `scripts/`, `assets/`, `references/`).
- `standalone/sherlock.md` — single-file guide, **generated** from `standalone/sherlock.src.md` and the skill files.
- `install.md` — install instructions for agents.
- `site/` — GitHub Pages site.

Development (Python 3.9+, standard library only):

    python tools/build_standalone.py          # regenerate standalone/ and site/ copies
    python -m unittest discover -s tests -v   # tests

Manual check per agent: run the install prompt, choose "This project", confirm `SKILL.md` is in the agent's skills folder, then ask "find the online accounts of …" and see that the skill starts with the brief.

## Responsible use

For lawful purposes only: checking your own footprint, due diligence, research with a legitimate reason. Not for stalking or harassment.
