# Mason

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/logo/mason-dark.svg">
  <img src="docs/logo/mason-light.svg" alt="Mason" height="56">
</picture>

[![CI](https://github.com/bitsandbricks-ch/mason-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/bitsandbricks-ch/mason-cli/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE) [![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-bitsandbricks-ffdd00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/bitsandbricks)

Mason (the `mason` command) is a terminal tool, TUI and web app for looking after many GitHub (and, in the web app, GitLab) repositories at once, across orgs and user accounts: status, pull requests, merges, workflow runs and approvals, security alerts, stats, and drift checks against shared defaults. It holds your bricks together.

The defaults live in a repository you choose. Point `mason` at any repo (or local folder) that holds a `mason.toml`, and it checks your repos against it. Nothing is tied to one org: every user can keep their own defaults repo.

## Install

Mason isn't on PyPI yet, so install it from GitHub with pipx. The `tui` extra adds `mason tui`, `server` adds `mason serve` (the web app), and `market` adds signature checks for `mason market`:

```sh
pipx install "mason-cli[tui,server] @ git+https://github.com/bitsandbricks-ch/mason-cli"
gh auth login          # on its own, mason talks to GitHub through the gh CLI and never sees a token
mason init your-org/your-defaults
```

To update: `pipx install --force "mason-cli[tui,server] @ git+https://github.com/bitsandbricks-ch/mason-cli"`. The install builds the web UI into the package, which needs Node.js (`npm`) on your PATH; without it, mason installs fine but `mason serve` has no UI and tells you how to build it. `mason serve --check` shows whether the UI is built. The Docker image always has it (see [Mason (web app)](#mason-web-app)).

The project was called Mortar before, and before that it was `bitsandbricks-ch/bitsandbricks-cli` with a `bnb` command. Only the names `mason`, `MASON_*`, `mason.toml` and `~/.config/mason` work now.

## Commands

Repos are named as `owner/name`, as a bare `name` when only one repo has it, or by their group alias (the group's `prefix` dropped, so `plugin-budgets` is also `budgets`). `name#12` is a pull request. Without names a command runs on every repo of your orgs. `--org` and `--group` narrow it down (`--group` takes a group's name, or an org with a trailing slash: `--group acme/` is every repo of the GitHub org acme, `--group gitlab:grp/` every project under the GitLab group grp, matched by a group or not), and `--dry-run` shows what would change.

| Command | What it does |
|---|---|
| `mason init <owner/repo or folder>` | Use this defaults repo. A local folder without `mason.toml` gets a starter file. |
| `mason config` | Where mason looks: config file, defaults, orgs, groups, plugins. |
| `mason repos` | The repos mason sees, with their group. |
| `mason status` | One line per repo: group, latest release, PRs ready/draft, CI. One GraphQL query per 20 repos. |
| `mason prs` | Open PRs with checks, reviews, merge status (mergeable, blocked, behind, conflicts) and auto-merge. |
| `mason pr web#12 [--diff] [--body]` | One PR in detail: merge state, failing checks with links, files, description (`--body`: all of it). Takes a PR URL too. |
| `mason merge [names] [--now] [--ready] [--method squash\|merge\|rebase]` | Auto-merge open PRs (or merge now; squash by default). When GitHub won't auto-merge a PR (auto-merge off for the repo, or no required checks on the base branch), it is merged right away. Drafts and conflicts stay open; `--ready` marks named drafts ready first. |
| `mason runs [--failed] [--limit 3]` | Latest workflow runs per repo. |
| `mason rerun name [--run ID] [--yes]` | Re-runs the failed jobs of the repo's newest failed run (or of run ID), after listing its jobs and the step that failed. Jobs that passed and approvals already given stay. |
| `mason releases [--problems] [--unreleased]` | Each repo's latest release, its assets, and its release runs. Flags assets the group's `release_assets` wants but the release lacks, and a failed last release run with the job and step that failed. The version column shows the version file against the latest release: `0.4.0 unreleased` when the version changed (a bump was merged) but nothing is released yet, and an open bump PR (`bump #12 → 1.0.1`). `--unreleased` lists only those; the web Releases tab has the same column and filter (u), the TUI's is under F4. |
| `mason packages [--problems]` | Container images on GHCR of your orgs: newest tags, whether the repo's latest release has an image with its tag, and a failed last image build (a run named or filed like image, docker or container) with the job and step that failed. |
| `mason bump name [patch\|minor\|major\|1.4.0] [--auto-merge]` | Opens a PR on `bump/v<new>` that sets (major, minor or patch from the current version; the web and TUI show what each would set) the version in the repo's version file (from its `.mason.toml`, else its group's `version`, else found in the repo root: plugin.yaml, pyproject.toml, package.json, Cargo.toml, VERSION; `__version__` in a Python file works too) and adds the section to each `changelog`: Keep a Changelog `[Unreleased]` entries become `## [1.4.0] - date`, otherwise a `## 1.4.0` section lists the PRs merged since the last release. Default: patch. |
| `mason release new name v1.4.0 [--title T] [--notes TEXT\|-] [--draft] [--prerelease] [--target REF] [--generate-notes] [--yes]` | Creates a release by hand, after asking (GitHub creates the tag on the default branch or `--target` when it is new). `--generate-notes` lets GitHub write the notes from the merged PRs. `mason release tag name [v1.4.0] [--target REF] [--yes]` only pushes the tag, for repos whose workflow creates the release on a tag push, like hubra with immutable releases; it says whether such a workflow is there. It never changes the version file: when the repo's group names one, the tag must be `v<version>` from it (that is also the suggestion), so bump first. Without a version file the next patch is suggested. `mason release view name [tag]` shows one release in full: notes, assets, the runs of its tag, and the repo's other recent releases. |
| `mason release [names] [--yes] [--list]` | Pushes the tag `v<version>` on the default branch of each named repo whose version is newer than its latest release (and whose first changelog has the section), after asking. The repo's own workflow builds and publishes. When the tag is there already it shows its release run. No names (or `--list`): a table of version against latest release. |
| `mason approve [--yes]` | Runs waiting for you: environments you review, and outside contributors' runs. A run that waits for someone else says why you can't approve it, for example "Prevent self-review" when you started it and are its only reviewer. |
| `mason security` | Open Dependabot, secret scanning and code scanning alerts. |
| `mason doctor [names] [--fix] [--no-auto]` | Settings, security, release immutability, rulesets, environments, variables, secrets (by name), Pages and its domain, CodeQL, autolinks, files and default branch protection against the defaults and the repo's own `.mason.toml`. `--fix` applies them; repos with `auto_fix` get them applied without it (`--no-auto`: only check). `--summary`: one line per repo (ok, or how many issues), only checking. |
| `mason secrets [names]` | The Actions secrets the defaults name for each repo (and its environments): set or missing. Names only: GitHub never gives values out. |
| `mason secrets set NAME [names] [--env ENV]` | Reads the value from stdin (or asks without echo), encrypts it with each repo's public key and stores it. One value can go to many repos. |
| `mason auto [names]` | Everything the repos' `auto_*` keys let mason do on its own, in one run: fix drift, push the version tag, update PRs that are behind, close stale PRs and issues, rerun failed runs, delete merged branches, auto-merge Dependabot updates and send drift alerts. Repos with nothing switched on are left alone, so it's safe from cron or a scheduled workflow. |
| `mason sync [names] [--only PATH]` | Opens a PR per repo whose shared files differ (with `auto_push`: pushes them to the default branch). |
| `mason issues [names] [--mine] [--label L] [--assignee X] [--stale DAYS] [--state open\|closed\|all] [--limit 20]` | Issues across repos, newest activity first; PRs are left out. `--assignee none` shows unassigned ones, `*` any assigned; `--label` repeats. |
| `mason issue new name "title" [--body TEXT] [--label L] [--assignee X]` | Opens an issue (`--body -` reads it from stdin). `mason issue view\|close\|reopen name#12` shows, closes (`--not-planned`) or reopens one, `mason issue comment name#12 "text"` comments. An issue URL works too. |
| `mason workflows [names] [--fix]` | Risky GitHub Actions workflows: actions not pinned to a commit, `write-all` or missing `permissions`, `pull_request_target` that checks out the PR, script injection from `${{ github.event... }}`. `--fix` opens a PR per repo that pins the actions to commit SHAs. |
| `mason new owner/name [--group G] [--public] [--description TEXT]` | Creates a repo the way its group wants it: from the reference repo when that is a GitHub template, the group's files committed, then its settings, security and rulesets applied. Private unless `--public`. |
| `mason open web#12 [--actions] [--releases]` | Prints the link, and opens it (or copies it over SSH; `MASON_OPEN=browser\|copy\|print`). `--actions` and `--releases` link those pages of a repo. |
| `mason stats [--days 30]` | Pull requests merged and opened, median time to merge, open and stale PRs, workflow runs with success rate and duration, releases. |
| `mason plugins` | Installed plugins. |
| `mason market [install NAME] [--index URL]` | Plugins in the signed plugin index; `install` adds one (only from a verified index). `keygen`, `sign` and `verify` are for whoever publishes an index. |
| `mason serve [--host 127.0.0.1] [--port 8080]` | Runs Mason, the web app, on Flask's development server (needs the `server` extra). `mason serve --check` shows what its settings allow and what is missing; `mason serve --users` lists its accounts, and `mason operator add github:LOGIN` makes someone an operator (the operator page). See [docs/mason.md](docs/mason.md). |
| `mason login https://mason [--read] [--key KEY]` | Go through [Mason](docs/mason.md), the web app, with an API key: mason shows a code, you approve it in the browser, and every command and the TUI then work without gh or a GitHub token here. `--read` asks for a read-only key, `--key` uses one you made in Settings › API keys. `mason logout` forgets the key, `mason whoami` says how mason reaches GitHub and as whom. |
| `mason tui` | Everything above, full screen. |

Security alerts need the `security_events` scope and packages the `read:packages` scope: `gh auth refresh -s security_events,read:packages`.

## TUI

`mason tui` has tabs for Repos, Pull requests, Runs, Releases, Packages, Security, Checks (doctor plus plugin checks) and Settings (defaults repo, orgs, groups, plugins, theme, config file), plus any tabs that plugins add. Issues and workflow hardening are commands and web app tabs, not TUI tabs yet.

- **Keys per row:** the footer and the top of the right side list only the keys that do something for the selected row (approve only on a run that waits, re-run only on a failed one, ready only on a draft).
- **Pull requests:** **u** updates the branch from its base, **c** comments, **C** closes without merging, besides merge, ready and diff.
- **Runs:** the right side lists the selected run's jobs with the step that failed. **a** approves, **x** re-runs the failed jobs, **l** shows the end of each failed job's log, **C** cancels a running run.
- **Repos** show the version file against the latest release, CI on the default branch, alerts and missing release assets. **Releases** show the version, the release notes and what failed in the last release run.
- **Repos and Releases:** **b** bumps the selected repo's version (pick patch, minor or major; opens the PR), **R** pushes its release tag once the bump is merged, **N** creates a release by hand (tag, title, one line of notes or GitHub's own, published, pre-release or draft), **T** pushes only a tag so the repo's own workflow makes the release.
- **Enter** on a row opens it as a full page: what you can do with it on the left (Enter or the key in brackets runs it), its whole detail on the right, and what the actions printed at the bottom. On Releases the page lists the repo's recent releases with the newest one's whole notes. **Esc** goes back to the list. On Checks and Settings, Enter opens a short menu instead.
- **The footer** starts with the function keys, as htop's does, then the keys that work on the current tab.
- **n** creates a new repo.
- **ctrl+p** (or **F2**) lists every command, **F1** (or **?**) every key.

### Keyboard only

Everything works without a mouse, and **Tab** alone gets you everywhere:

- **Tab / Shift+Tab** move between the panels: the tab bar, the list, its detail, the search line (when it is open) and the log. The panel with the focus has a coloured edge. On a row's page, Tab goes from the actions to the detail to the log.
- **← →** switch tabs from the list or the tab bar (**1**-**9** jump to one). In the detail they scroll sideways, in a search or an answer they move the cursor.
- **↑ ↓ PgUp PgDn Home End** move in the list, or scroll the detail and the log once Tab has put the focus there.
- **Dialogs:** Tab, Shift+Tab and the arrows move between Yes and No, Enter presses the one with the focus. In a list of choices (bump level, filters, sort) Tab and Shift+Tab go through the choices.

### Search, filter and sort (F-keys)

The lists use htop's and Midnight Commander's function keys. Each one also has a letter, because some terminals keep F-keys for themselves (GNOME Terminal opens its help on F1 and its menu on F10; on a Mac the F-keys need fn).

| Key | Letter | What it does |
|---|---|---|
| F1 | `?` | Every key, and the selected row's own keys. |
| F2 | ctrl+p | Every command. |
| F3 | `/` | Search: only the rows with this text stay, as you type. Enter keeps it, Esc clears it. Each tab keeps its own. |
| F4 | `v` | Filter. F4 picks one, `v` goes to the next. Repos: with open PRs, CI failing. Pull requests: auto-merge, recently merged, drafts. Runs: waiting, failed, running. Releases and Packages: with problems. Security: with alerts. |
| F5 | `r` | Refresh the tab you are on. |
| F6 | `>` | Sort by a column. The same column again reverses it, "as loaded" goes back to mason's own order (what needs you first). Ages ("3h ago") and numbers sort by value. |
| F9 | Enter | The selected row as a page. |
| F10 | `q` | Quit. |

The line over the log says what the list shows: `3 of 12 rows · F4 filter: failed · F3 search: 'api' · F6 sort: when ↑`.
- **Loading:** the repo and PR list loads at start, with one GraphQL query per 20 repos. Runs, Releases, Packages and Security load the first time you open their tab. **r** reloads the tab you are on. After a change (ready, auto-merge, merge, a release, a tag, a bump) the view reads just that repo again, and keeps doing so while a PR waits for auto-merge or a release run is going, so the result shows without **r**.
- **Rate limit:** the header shows how many API calls are left. Answers are cached for 60 seconds; **r** reads past the cache. If GitHub's rate limit is reached, the TUI says when it resets instead of failing.

## Version files

Bump, release and New tag need to know which file holds a repo's version. Mason looks in this order:

1. **The repo's `.mason.toml`**, its `[release]` table (the rest of the file is the repo's own settings, see [A repo's own settings](#a-repos-own-settings-masontoml)):

   ```toml
   [release]
   version = "src/app/__init__.py"   # any file: plugin.yaml, pyproject.toml, package.json, Cargo.toml, VERSION, __version__ = "..."
   changelog = ["CHANGELOG.md"]      # optional
   tag = "app-v{version}"            # optional, default "v{version}"
   ```

2. **Its group** in the defaults' `mason.toml`: `version = "plugin.yaml"`, `changelog = ["CHANGELOG.md"]`.
3. **A known file in the repo root** that holds a version: plugin.yaml, pyproject.toml, package.json, Cargo.toml, VERSION (with CHANGELOG.md, CHANGES.md or HISTORY.md as the changelog).

`mason release` (no names) lists every repo with the file it found. `mason doctor` flags a repo that has releases but no
version file, a version file that's missing or holds no version, and a version behind the latest release
(`skip = ["version"]` on a group turns this off).

## Configuration

Your own config is `~/.config/mason/config.toml` (`mason init` writes it):

```toml
defaults = "your-org/your-defaults"   # a GitHub repo, or a local folder
ref = "main"                          # optional branch or tag
orgs = ["another-org"]                # added to the orgs the defaults name
repos = ["someone/their-repo"]        # added to the defaults' repos
exclude = ["another-org/archive-*"]   # added to the defaults' exclude
org_defaults = true                   # read each org's .mason repo (the default; false turns it off)
```

It lives in `$XDG_CONFIG_HOME/mason` when that is set, and `MASON_CONFIG` points mason at another file. `MASON_DEFAULTS`, `MASON_DEFAULTS_REF` and `MASON_ORGS` (comma separated, replacing the orgs) override it for one run.

| Variable | What it does |
|---|---|
| `MASON_CONFIG` | Your config file, instead of `~/.config/mason/config.toml`. |
| `MASON_DEFAULTS`, `MASON_DEFAULTS_REF` | The defaults repo (or folder) and its branch or tag. |
| `MASON_ORGS` | The orgs to look at, comma separated. |
| `MASON_ORG_DEFAULTS` | `0` (or `off`) leaves each org's `.mason` repo out for one run. |
| `MASON_SERVER`, `MASON_KEY` | Go through Mason with this URL and API key (for CI). `MASON_SERVER=` (set but empty) uses gh even after `mason login`. |
| `MASON_OPEN` | How `mason open` opens links: `browser`, `copy` or `print`. |
| `MASON_PLUGINS` | `none`, or a comma separated list of the plugins to load. |
| `MASON_PLUGIN_INDEX`, `MASON_PLUGIN_INDEX_KEYS` | The plugin index for `mason market`, and extra public keys (base64, comma separated) it may be signed with. |

`mason.toml` in the defaults repo is shared by everyone who points mason at it:

```toml
orgs = ["your-org", "your-user"]
repos = ["someone/one-more-repo"]
exclude = ["your-org/old-*"]

[[group]]
name = "plugins"
match = { org = "your-org", prefix = "plugin-" }   # also: suffix, repos, exclude, topics, provider
from = "your-org/plugin-template"                  # a live reference repo
files = [".gitignore", "LICENSE"]                  # files that must match the reference
require = { allow_auto_merge = true }              # what the reference itself must have

[[group]]
name = "default"                                   # no match: takes the rest
settings = { delete_branch_on_merge = true, has_wiki = false }
security = { secret_scanning = "enabled", secret_scanning_push_protection = "enabled",
             dependabot_alerts = "enabled", dependabot_security_updates = "enabled" }
immutable_releases = true
vulnerability_reporting = true
topics = ["your-org"]                              # topics every repo has
labels = { bug = "d73a4a", docs = { color = "0075ca", description = "Documentation" } }
actions = { allowed_actions = "selected", default_workflow_permissions = "read",
            can_approve_pull_request_reviews = false }
required_files = ["README.md", "LICENSE", "CODEOWNERS|.github/CODEOWNERS"]   # A|B: either one
branch = "main"                                    # the default branch's name (--fix renames it)
visibility = "private"                             # public, private or internal
description = true                                 # every repo has a description
workflows = { allow_unpinned = ["actions/*"] }     # doctor checks the workflows too (or: workflows = true)
skip = ["labels"]                                  # checks this group leaves out
release_assets = ["*.zip"]                         # files every release must attach (mason releases)
version = "pyproject.toml"                         # the file with the version (mason bump, mason release)
changelog = ["CHANGELOG.md"]                       # changelogs mason bump adds the section to
rulesets = "rulesets/default"                      # ruleset JSON files (export them from GitHub)
files = "files/default"                            # copied into each repo, path for path
variables = { NODE_VERSION = "22" }                # Actions variables (not secret: the values live here)
secrets = ["NPM_TOKEN"]                            # Actions secrets that must exist: names only
pages = { build = "workflow", https = true }       # GitHub Pages (or true / false); cname = "docs.example.com"
homepage = true                                    # the repo's website: its Pages address, or a URL
code_scanning = true                               # CodeQL default setup
autolinks = { "JIRA-" = "https://jira.example.com/browse/JIRA-<num>" }

[group.environments.production]                    # deployment environments
reviewers = ["mike", "team:your-org/ops"]          # required reviewers (users, or teams)
wait = 5                                           # minutes before a deployment starts
branches = ["main", "tag:v*"]                      # who may deploy: patterns, "protected" or "all"
prevent_self_review = true
secrets = ["DEPLOY_TOKEN"]                         # the environment's secrets (names)
variables = { REGION = "eu" }
```

`actions` also takes `retention_days = 30` (how long logs and artifacts are kept) and `fork_pr_approval`
(`first_time_contributors_new_to_github`, `first_time_contributors` or `all_external_contributors`).

#### Groups stack

Every group that matches a repo applies, not only the first one. So one group can hold what every repo
gets, another what all `plugin-*` repos get on top, and another what one repo gets:

```toml
[[group]]
name = "all"                                       # no match: every repo
settings = { delete_branch_on_merge = true }
immutable_releases = true

[[group]]
name = "plugins"
match = { prefix = "plugin-" }                     # every plugin
secrets = ["SIGN_KEY"]

[[group]]
name = "site"
match = { repos = ["your-org/website"] }           # one repo, by its full name
pages = { cname = "www.example.com", https = true }
```

The more specific group wins key by key: a group naming full repos beats one with a `prefix` or `suffix`,
which beats one with only an `org`, `topics` or `provider`, which beats one without `match`; on a tie the
group written first wins. Tables (`settings`, `security`, `labels`, `actions`, `variables`, `autolinks`,
each environment, `pages`) merge key by key; lists (`topics`, `secrets`, `required_files`, `release_assets`,
`skip`) add up; rulesets and files folders merge by name and path; other values are replaced. A repo's group
name (in lists and for its alias) is the most specific one's, and `--group all` takes every repo the "all"
group matches. `inherit = false` on a group stops the less specific groups from stacking under it.

With `from`, the group takes everything from the reference repo as it is live on GitHub (settings, security, release immutability, rulesets), so changing the reference changes what every repo of the group should have. Explicit `settings`, `security` and `rulesets` go on top. With `from`, the group takes everything from the reference repo as it is live on GitHub (settings, security, release immutability, rulesets), so changing the reference changes what every repo of the group should have. Explicit `settings`, `security` and `rulesets` go on top.

A ruleset from the defaults folder only has to be covered: a repo may set more than the file says (GitHub fills in its own defaults). A reference repo's rulesets must match exactly. Each repo's own `.github/rulesets/*.json` and `.mason/rulesets/*.json` must also match what's live, and `doctor --fix` imports them (`.mason/rulesets` wins when both have a ruleset of the same name).

In the web app each repo shows its doctor result without a run: the Repos list has a doctor column (ok, or how many issues), and a repo's page lists its issues and fixes, checked when the page opens and kept for a day (in memory only; `check again` asks GitHub/GitLab again). Checks › doctor fills the column for every repo at once and puts a per-repo table above the full output.

`doctor --fix` sets settings, security (Dependabot alerts and security updates too), topics (it adds the missing ones and keeps the rest), labels (it creates missing ones and fixes colors, and leaves other labels alone), the Actions permissions, retention and fork PR approval, environments (reviewers, wait timer, branch patterns, variables), variables, Pages (on, off, build, branch, domain, HTTPS), the homepage, CodeQL default setup and autolinks, and renames the default branch to `branch` (GitHub moves open PRs; clones need `git branch -m`). `visibility`, `description` and `required_files` are only checked, because changing them can break things: a missing required file is a job for `mason sync` or a PR. Secrets are only checked by name: mason never knows a value, so `mason secrets set` (or a repo's page in the web app) stores one. Pages HTTPS can only be turned on once GitHub has issued the domain's certificate: `--fix` says so and a later run sets it. DNS for a custom domain stays with you.

Every write needs admin rights on that repo (secrets: write access), and mason uses your own login, so `--fix` changes what you administer and reports the rest.

`skip` turns checks off for a group: `settings`, `security`, `vulnerability_reporting`, `immutable_releases`, `rulesets`, `own_rulesets` (the repo's `.github/rulesets` and `.mason/rulesets`), `files`, `required_files`, `topics`, `labels`, `actions`, `branch`, `visibility`, `description`, `workflows`, `environments`, `variables`, `secrets`, `pages`, `homepage`, `code_scanning`, `autolinks`, `plugins` (the plugins' doctor checks) and `version` (the version file).

`workflows` makes doctor check the group's workflow files like `mason workflows` does. It takes `true` or a table: `pinned`, `permissions`, `pull_request_target` and `injection` turn single checks off with `false`, and `allow_unpinned = ["actions/*", "your-org/*"]` lets actions of owners you trust stay on a tag. `mason workflows --fix` keeps the tag as a comment (`uses: actions/checkout@<sha> # v4`), so Dependabot and Renovate keep updating the pins.

Three switches say what mason may do on its own, on a group or in a repo's `.mason.toml` (the repo wins,
so `auto_push = false` there turns a group's `auto_push` off):

```toml
auto_fix = true     # plain `mason doctor` fixes what --fix would (on the command line and in the web console)
auto_push = true    # sync, pinned actions and version bumps go straight onto the default branch, no PR
auto_merge = true   # the PRs mason opens on the repo (sync, pins, bumps) get auto-merge
```

`auto_fix` needs the same admin rights as `--fix`; `mason doctor --no-auto` only checks. The web app's
Checks page stays a plain check, and in the web console a read-only API key never fixes. With
`auto_push`, a push the default branch refuses (a ruleset that wants PRs, no `workflow` scope for a
workflow file) becomes a PR after all. Turn it on only where nobody needs to review those changes.

### More repo keys

These work on a group and in a repo's `.mason.toml` like the rest (tables merge key by key, lists add up,
the repo wins):

```toml
owner = "mike"                     # who to ask; shown by doctor and on the repo's page in the web app
team = "web"
notes = "Deploys from main to Cloudflare"

protect = { reviews = 1, checks = ["test"], signed_commits = true }   # a ruleset named "protect"
# also: linear_history, merge_queue = true (or a table of GitHub's merge queue settings), code_owners,
# resolve_threads, dismiss_stale, up_to_date, branches = ["main", "release/*"], name = "protect"
skip_until = { code_scanning = 2027-01-01 }   # skip a check until that day; after it, doctor says so

dependabot = { ecosystems = ["pip", "github-actions"], interval = "weekly", group = true, auto_merge = "minor" }
renovate = true                    # or { extends = ["config:recommended"] }
codeowners = { "*" = ["@mike"], "/docs/" = ["@acme/docs"] }
release_notes = { categories = { Features = ["feature"], Fixes = ["bug"] }, exclude = ["chore"] }
templates = true                   # an issue template and a PR template must exist
release_drafts = true              # `mason release new` and the web app's New release make drafts

discussions = ["Announcements", "Q&A"]   # categories that must exist (GitHub only adds them on the web)
social_preview = true              # a custom social preview image must be set
archive_after = 12                 # months without a push; --fix (or auto_fix) archives the repo
properties = { tier = "1" }        # custom property values (--fix sets them)
webhooks = ["https://ci.example.com/hook"]   # must exist; checked only
deploy_keys = ["deploy"]           # titles that must exist; checked only

# what `mason auto` does on its own
auto_release = true                # push the tag once the version file is ahead of the latest release
auto_update_branch = true          # update open PRs that are behind their base
auto_close_stale = 60              # close PRs and issues untouched for 60 days (labels keep, pinned, security stay)
auto_rerun_failed = 1              # rerun the failed jobs of each workflow's latest run on the default branch, once
auto_delete_branches = 14          # delete branches of PRs merged more than 14 days ago
alerts = "https://hooks.slack.com/services/..."   # Slack, Discord or any https webhook: new drift only
```

`dependabot`, `renovate`, `codeowners` and `release_notes` write their files: `mason sync` brings them in
(a PR, or straight onto the default branch with `auto_push`), and doctor reports them like shared files.
`allow_forking` and `is_template` are settings like the others (`[settings]`); a template reference
doesn't make its repos templates. `skip` takes `protect`, `dependabot`, `renovate`, `codeowners`,
`templates`, `release_notes`, `discussions`, `social_preview`, `archive`, `properties`, `webhooks` and
`deploy_keys` too.

`mason auto` keeps what it last saw in `~/.config/mason/alerts.json`, so an alert only lists what's new.
Alerts are sent only from the command line, never from the web app. Run it on a schedule, for example
from a workflow in your defaults repo:

```yaml
on: { schedule: [{ cron: "0 6 * * *" }] }
jobs:
  auto:
    runs-on: ubuntu-latest
    steps:
      - run: pipx install "mason-cli @ git+https://github.com/bitsandbricks-ch/mason-cli" && mason auto
        env: { GH_TOKEN: "${{ secrets.MASON_TOKEN }}", MASON_DEFAULTS: "your-org/your-defaults" }
```

### Default branch protection

Every repo's default branch must be protected by something, and doctor says so when nothing does:

```
- the default branch main isn't protected (no ruleset or branch protection): set protect = { reviews = 1 } ...
```

Anything counts: a ruleset of the repo, a ruleset of its org (GitHub's rules for the branch), or classic
branch protection. What it should look like comes from `protect`, which stacks like every other key, least
important first:

1. a group in your defaults repo's `mason.toml`,
2. a group in the org's `.mason` repo (`<org>/.mason/mason.toml`, GitLab: the group's `.mason` project),
3. a group of your own that names the repo with `match`,
4. the repo's own `.mason.toml`, or `.mason/mason.toml` in a `.mason/` folder.

The tables merge key by key, so the org can say `protect = { reviews = 1 }` and a repo can add
`protect = { checks = ["test"] }`. `protect = false` (or `skip = ["protect"]`) in a repo turns it off there.
On GitHub `protect` becomes a ruleset named `protect` for the default branch; doctor checks it like the
other rulesets and `mason doctor --fix` (or `auto_fix`) creates or updates it. For anything `protect` can't
say, put the ruleset JSON (as GitHub exports it) in the defaults repo's `rulesets` folder, the org's
`.mason` repo, or the repo's own `.github/rulesets/` or `.mason/rulesets/`. On GitLab `protect` protects the
default branch (nobody pushes, developers merge) unless `[gitlab] protected_branches` names it already.

A GitLab project's own `.mason.toml` counts too: its `[gitlab]` table (settings, protected_branches,
approvals_before_merge) goes on top of the group's, and `auto_push` / `auto_merge` decide how `mason sync`
lands the files there.

Unknown keys on a group stay there for plugins (`group.extra`).

### An org's own defaults: the `.mason` repo

Like the `.github` repo, an org (or a GitLab group) can keep the defaults of its own repos in a repo
named `.mason`, with a `mason.toml` in it. Everyone who works on the org's repos gets them, without
pointing mason anywhere:

```toml
# your-org/.mason/mason.toml
[[group]]
name = "services"
match = { prefix = "svc-" }
rulesets = "rulesets/services"   # folders are read from the .mason repo itself
files = "files/services"

[[group]]
name = "default"                 # the rest of the org's repos
settings = { delete_branch_on_merge = true }
security = { secret_scanning = "enabled" }
```

Only its `[[group]]` tables count, and only for repos of that org: `orgs`, `repos` and `exclude` in it
are ignored, so an org's file can't change which repos you look at. Its groups are named `org:name`
(`your-org:services`, for `--group`). On GitLab the nearest group's `.mason` comes first, then its
parents' (`grp/sub/.mason`, then `grp/.mason`).

Which groups stack for a repo, least important first:

1. a group of your own defaults without `match` (your catch-all), only when no group of the org's `.mason` matches,
2. the groups of the repo's org's `.mason` that match (on GitLab a parent group's before its subgroup's),
3. the groups of your own defaults whose `match` takes the repo,
4. the repo's own `.mason.toml` (below).

So the org's `.mason` replaces your catch-all for its repos, a group you wrote for some of its repos on
purpose goes on top, and the repo itself has the last word.

### A repo's own settings: `.mason.toml`

A repo can set everything a group can for itself in a `.mason.toml` at its root (or in `.mason/mason.toml`,
next to its own rulesets in `.mason/rulesets/`), and it wins over every group, the org's `.mason` included. Plugins, indexes, apps and websites of one org can each carry what
they need:

```toml
# your-org/website/.mason.toml
secrets = ["CLOUDFLARE_TOKEN"]
code_scanning = false

[settings]
has_wiki = false

[pages]
cname = "www.example.com"
https = true

[environments.production]
reviewers = ["mike"]
branches = ["main"]

[release]                          # version files (above)
version = "package.json"
```

Keys that only make sense for a group (`name`, `match`, `from`, `files`, `require`, `rulesets`, `version`,
`changelog`, `inherit`) are ignored here; the repo's own rulesets are its `.github/rulesets/*.json` and `.mason/rulesets/*.json`, and
those now win over a group's ruleset of the same name. Anyone who can push to the repo can change this
file, so it can also turn org rules off for that repo (`skip`, or a looser setting): review it like code.
GitLab projects read it too, for their `[gitlab]` table and the auto switches (see More repo keys).

In the web app a repo's page has a **branch rules** panel: what protects its default branch now, where its
rules come from layer by layer (your defaults, the org's `.mason`, the repo), and what's in effect. From there
you can edit the repo's `protect` with a form (or turn it off for that repo), edit or add `.mason/mason.toml`
and `.mason/rulesets/*.json`, and keep the repo's live rulesets in `.mason/rulesets`. Every change is
validated and written to the repo: a pull request, or straight onto the default branch when the repo has
`auto_push` (refused pushes become a PR), or as you pick. An org's `.mason` repo has the same panel for its
`mason.toml` and `rulesets/` folder, always through a pull request unless you pick "commit directly".

mason reads the `.mason` repo with your own login (gh, your token, or your Mason account), so a private
`.mason` only counts for people who can read it, and each user's answer is cached in their own cache
(5 minutes; a file written through mason drops it). `mason config` shows which `.mason` repos it found.
`org_defaults = false` in your config, `MASON_ORG_DEFAULTS=0`, or the switch in the web app's Settings
turns it off.

## Plugins

A plugin is a Python package with an entry point in the `mason.plugins` group. It can add commands, `status` columns (with extra GraphQL fields), doctor checks and hints, TUI tabs and palette commands. See `src/mason/plugins.py`.

```toml
[project.entry-points."mason.plugins"]
myplugin = "my_package.mason:MyPlugin"
```

Install one next to mason with `pipx inject mason-cli <package>`. `MASON_PLUGINS=none` (or a comma separated list of names) limits which plugins load.

hubra-cli is one: it adds Hubra plugin releases, signing checks and a Hubra tab.

## Mason (web app)

`mason serve` runs mason as a web app. People sign in with their own GitHub or GitLab account (OAuth, so every
call uses their own token) and get every command and TUI view in a terminal-style browser UI, plus issues,
workflow hardening, a defaults editor with templates, stats, a console, plugins and a signed plugin
marketplace. It works on a phone too. `mason login https://mason.mortar.ch` points the CLI and TUI at it with an
API key, so a laptop needs neither gh nor a token.

The quickest way to run it is Docker, which builds the UI too:

```sh
cp deploy/mason.env.example deploy/mason.env       # fill in MASON_URL, an OAuth app, who may sign in
docker compose -f deploy/docker-compose.yml up -d    # Mason and Postgres, on 127.0.0.1:8080
```

From a clone, for development:

```sh
docker compose -f deploy/docker-compose.yml up -d   # after filling in deploy/.env (see docs/mason.md)
pip install -e ".[server]" && (cd web && npm ci && npm run build)
mason serve --check && mason serve                       # http://localhost:8080
```

![Mason's pull requests view](docs/screenshots/03-pull-requests.png)

Setup, settings, the security model and more screenshots: [docs/mason.md](docs/mason.md).

## Roadmap

Ideas and planned features live in [docs/BACKLOG.md](docs/BACKLOG.md).

## Development

```sh
pip install -e ".[dev]"
pytest          # runs every command against tests/fake_gh, a stand-in for gh
ruff check .
cd web && npm ci && npm run build   # Mason's UI (npm run dev for a live-reloading one)
```

## License

MIT, see [LICENSE](LICENSE).
