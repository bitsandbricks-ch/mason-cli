# Rules for coding agents

These rules are for AI coding agents (Claude Code, Codex, Copilot, opencode, ...) working on Mason.
Humans: the same rules apply to you in spirit.
`CLAUDE.md` imports this file.

This repo follows the [BitsAndBricks handbook](https://github.com/bitsandbricks-ch/handbook),
profile **multi-tool** (see `.mason.toml`). Read the latest handbook from `main`: its core
chapters and the blocks this profile lists. The rules below are only what is specific to this
repo. Where this repo differs from the handbook, the difference is listed under
[Differences from the handbook](#differences-from-the-handbook) with its reason.

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

- Work from an issue: open one if there is none, comment when you start and when blocked, link it
  from the PR (`Fixes #12`).
- Commits and PR titles follow Conventional Commits, with these scopes: `cli`, `tui`, `web`,
  `server`, `gitlab`, `handbook`, `docs`, `ci`.
- **Pull requests:** fill in `.github/pull_request_template.md`.
- **Changelog:** a user-facing change adds a fragment to `changelog.d/` (see its README).
- **Releases:** the maintainer releases with `mason bump` and `mason release tag`.
- **Tests never talk to the GitHub API:** they run against the stand-ins in `tests/fake_gh`
  (and `tests/fake_glab` for GitLab). Keep it that way.
- **Core and add-on:** the CLI and the TUI are the core; the web app (`src/mason/server/`, `web/`)
  is an add-on on top of it. The core never imports the add-on and works without its libraries;
  a feature lands in the core first. See [docs/architecture.md](docs/architecture.md) (issue #88).
- **Tokens:** the CLI and the TUI reach GitHub through gh and GitLab through glab (`mason login`
  runs `gh auth login` and `glab auth login`). The CLI may read the token they hold, but mason
  never stores one. The web app signs each user in with their own OAuth token; only the server
  holds the client secret. Don't change the server's secret handling without asking.
- Stay inside the repository. Ask before deleting files you didn't create.

## Differences from the handbook

- No `pre-commit`, `ruff format` or PR-title check yet (handbook 0009, 0010): the first
  `ruff format` run touches most files, so it gets its own PR (#84). Until then, run the commands
  under "Before you push".
