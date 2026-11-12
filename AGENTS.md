# Rules for coding agents

These rules are for AI coding agents (Claude Code, Codex, Copilot, ...) working on Mason.
Humans: the same rules apply to you in spirit.
`CLAUDE.md` imports this file.

## What this is

Mason (the `mason` command): a terminal tool, TUI and web app for looking after many GitHub and GitLab repositories at once, with drift checks against shared defaults. The [README](README.md) says where things are and how to run it.

## Workflow

1. **Branch:** work on your own branch, never push to `main`. One topic per branch and pull request.
2. **Before you push**, run what CI runs and make it pass locally:
   - `pip install -e ".[dev]"`
   - `ruff check .`
   - `pytest -q`
   - `cd web && npm ci && npm run build`
3. **Pull request:** open it as a **draft** and fill in the template
   (`.github/pull_request_template.md`). Link the issue.
4. **CI:** wait for the checks in `.github/workflows/`. Fix failures
   yourself. Never skip, disable or weaken a check or a test to get green.
5. **Done** means the task is complete, the checklist is ticked and the checks are green: then mark
   the pull request ready for review. Leave it a draft only while work is open or you are blocked,
   and say why in the description.
6. **Never merge** your own pull request, never force-push to a branch someone else works on, and
   never push a tag. Merging and releasing are the maintainer's call.
7. Keep the pull request description current when you push more commits.

## Rules

- **Ask, don't guess.** Never make up facts about the project, its users or its author (features,
  history, numbers, names). Leave a `TODO` and ask instead.
- **No secrets** in code, commits, screenshots, logs or docs. Use example values (`example.com`).
- **Names:** the brand is written "BitsAndBricks". Public text names the author as "Mike" only.
- **Releases:** don't change the version or push tags; the maintainer releases with `mason bump` and `mason release tag`.
- **Workflows:** pin every action to a full commit sha with the version as a comment
  (`uses: actions/checkout@<sha> # v7.0.1`), keep `permissions` minimal, and never put
  `${{ github.event.* }}` text straight into a `run:` script (pass it through `env:`).
- **Dependencies:** add one only when it clearly pays for itself, and say why in the pull request.
- Write short comments that explain why, not what.
- Stay inside the repository. Ask before deleting files you didn't create.
- **Tests never talk to the GitHub API:** they run against the stand-ins in `tests/fake_gh`. Keep it that way.
- **Tokens:** on its own, mason talks to GitHub through the gh CLI and never sees a token. Don't change that without asking.
