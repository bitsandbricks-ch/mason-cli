"""Mason's own defaults: what doctor holds a repo to when nothing else says.

A repo that no group of yours, no group of its org's .mason and no .mason.toml of its own describes used to get
almost no checks ("no group: only its own ruleset files"). It now gets this small group instead, safe for any
repo, public or private, run by one person or many:

- the default branch is protected: changes go through pull requests, no force pushes, no deletion
  (no approvals required, so a repo with one maintainer can still merge its own PRs)
- merged branches are deleted, PRs can auto-merge and be brought up to date
- Dependabot alerts and security updates are on
- a pull request template, issue templates and a dependency update config exist; `mason sync` adds a
  starter for each one that's missing, and a repo's own version is never replaced

Any group or the repo's .mason.toml replaces it key by key (`protect = false`, `skip = ["templates"]`).
Two pieces fill in for every repo, grouped or not:
- `protect` isn't a key of this group. A default branch nothing protects gets the PROTECT ruleset from --fix
  when no layer sets `protect` at all; one protected some other way (classic protection, an org ruleset)
  is left as it is.
- `templates = true` (and these required_files entries) get the starters when a repo has none.
Turn it all off with `builtin = false` in mason.toml or your config, or MASON_BUILTIN=0.
"""

from __future__ import annotations

from mason.config import Group

NAME = "built-in"
PROTECT = {"reviews": 0}  # pull requests required (deletion and force pushes too), no approvals
SETTINGS = {"delete_branch_on_merge": True, "allow_auto_merge": True, "allow_update_branch": True}
# secret scanning is left out: on private repos it needs GitHub Advanced Security, and --fix would fail
SECURITY = {"dependabot_alerts": "enabled", "dependabot_security_updates": "enabled"}

PR_TEMPLATE = """\
## What and why

<!-- What does this change, and why? Link the issue it closes: Fixes #123 -->

## How it was tested

<!-- Commands you ran; screenshots for changes people see -->

## Checklist

- [ ] Tests added or updated
- [ ] Docs updated where needed
"""

BUG_REPORT = """\
name: Bug report
description: Something doesn't work as it should
labels: ["bug"]
body:
  - type: textarea
    id: what
    attributes:
      label: What happened
      description: What did you do, what did you expect, and what happened instead?
    validations:
      required: true
  - type: textarea
    id: steps
    attributes:
      label: Steps to reproduce
      placeholder: |
        1. ...
        2. ...
  - type: input
    id: version
    attributes:
      label: Version
      description: Which version, commit or environment?
"""

FEATURE_REQUEST = """\
name: Feature request
description: An idea or something that's missing
labels: ["enhancement"]
body:
  - type: textarea
    id: problem
    attributes:
      label: What's the problem?
      description: What are you trying to do, and what gets in the way?
    validations:
      required: true
  - type: textarea
    id: idea
    attributes:
      label: What would help?
"""

DEPENDABOT = """\
# Written by mason (its built-in defaults): keeps the Actions in the workflows up to date.
# Add the ecosystems this repo uses (pip, npm, ...) or replace it with your own.
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
"""

# required_files entries ("a|b": either will do) -> the starter files `mason sync` adds when none is there
PR_NEED = (".github/pull_request_template.md|.github/PULL_REQUEST_TEMPLATE.md|pull_request_template.md|"
           "docs/pull_request_template.md|.github/PULL_REQUEST_TEMPLATE")
ISSUE_NEED = (".github/ISSUE_TEMPLATE/config.yml|.github/ISSUE_TEMPLATE/config.yaml|"
              ".github/ISSUE_TEMPLATE/bug_report.md|.github/ISSUE_TEMPLATE/bug_report.yml|.github/ISSUE_TEMPLATE/feature_request.md|"
              ".github/ISSUE_TEMPLATE/feature_request.yml|.github/ISSUE_TEMPLATE.md")
DEPS_NEED = (".github/dependabot.yml|.github/dependabot.yaml|renovate.json|renovate.json5|.github/renovate.json|"
             ".github/renovate.json5|.renovaterc|.renovaterc.json")
STARTERS: dict[str, dict[str, str]] = {
    PR_NEED: {".github/pull_request_template.md": PR_TEMPLATE},
    ISSUE_NEED: {".github/ISSUE_TEMPLATE/bug_report.yml": BUG_REPORT,
                 ".github/ISSUE_TEMPLATE/feature_request.yml": FEATURE_REQUEST},
    DEPS_NEED: {".github/dependabot.yml": DEPENDABOT},
}
# how doctor names a missing one (the list of every name it may have is long)
NAMES = {PR_NEED: "a pull request template", ISSUE_NEED: "an issue template",
         DEPS_NEED: "a dependency update config (Dependabot or Renovate)"}


def group() -> Group:
    """The built-in defaults as a group: the bottom layer for repos nothing else describes."""
    return Group(NAME, settings=dict(SETTINGS), security=dict(SECURITY), required_files=[DEPS_NEED],
                 more={"templates": True}, origin=NAME)  # protect: see rules._default_protected


def starters(required: list[str]) -> dict[str, dict[str, str]]:
    """The starters for the `required` entries that have one."""
    return {need: dict(STARTERS[need]) for need in required if need in STARTERS}


def missing(need: str) -> str:
    """doctor's line for a required entry that isn't there."""
    name = NAMES.get(need)
    return f"{name} is missing" if name else f"{need.replace('|', ' or ')} is missing"
