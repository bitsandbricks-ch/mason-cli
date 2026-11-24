# Rules for coding agents

These rules are for AI coding agents (Claude Code, Codex, Copilot, opencode, ...) working on Mason.
Humans: the same rules apply to you in spirit.
`CLAUDE.md` imports this file.

This repo follows the [BitsAndBricks handbook](https://github.com/bitsandbricks-ch/handbook),
profile **cli-tool** (see `.mason.toml`). Read its core chapters and the blocks this profile
lists. The rules below are only what is specific to this repo; where they differ from the
handbook, this file wins.

## What this is

Mason (the `mason` command): a terminal tool, TUI and web app for looking after many GitHub and
GitLab repositories at once, with drift checks against shared defaults. The [README](README.md)
says where things are and how to run it.

## Before you push

Run what CI runs and make it pass locally:

- `pip install -e ".[dev,docs]"`
- `ruff check .`
- `pytest -q`
- `mkdocs build --strict`
- `cd web && npm ci && npm run build && npm test`

## Repo-specific rules

- **Pull requests:** fill in `.github/pull_request_template.md`.
- **Changelog:** a user-facing change adds a fragment to `changelog.d/` (see its README).
- **Releases:** the maintainer releases with `mason bump` and `mason release tag`.
- **Tests never talk to the GitHub API:** they run against the stand-ins in `tests/fake_gh`
  (and `tests/fake_glab` for GitLab). Keep it that way.
- **Tokens:** on its own, mason talks to GitHub through the gh CLI and never sees a token.
  Don't change that without asking.
- Stay inside the repository. Ask before deleting files you didn't create.
