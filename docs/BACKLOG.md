# Backlog

Ideas and features for Mason (the `mason` CLI, TUI and web app), roughly in the order they'd pay off. Pick one, open a PR,
move it to "Done" when it ships.

## Next

- **hubra-cli on the new names.** The old `bitsandbricks` names are gone, so hubra-cli has to `import mason`
  and register its plugin under the `mason.plugins` entry point group before it loads again.
- **hubra-cli on the operator.** hubra-cli still has its own gh plumbing and token file, so in the
  operator its commands don't run with the signed-in user's token. Port it to `mason.core`
  (transport-aware `api`/`graphql`), read the Hubra token with `plugins.secret("hubra_token")`, and expose
  `web_secrets()`, `web_actions()` (sign, release, verify) and `web_commands`. Follow-up PR in hubra-cli.
- **GitLab in the TUI and through the operator.** The CLI reaches GitLab through glab (see the README's GitLab
  section); the TUI still lists GitHub only, and `mason login` users have no GitLab: that needs a GitLab proxy in
  the operator next to the GitHub one (server/api/proxy.py). Also still GitHub only in the CLI: rerun, packages,
  workflows, auto, bump, release, secrets, settings, branches and new.
- **Signed official plugin index.** Make the project key, sign `plugins/index.json` in CI, ship the public
  key in `src/mason/keys/`.
- **Live updates.** GitHub/GitLab webhooks (or a GitHub App) into the operator, pushed to the browser with
  server-sent events, so lists refresh themselves and the cache can be invalidated precisely. Until then the
  web app follows up on its own changes by reading the touched repos again (web/src/load.js, useFollow).
- **Scheduled checks in the web app.** The CLI side is done (`mason doctor --save`, `mason drift --now --notify`,
  from cron or a scheduled workflow). Still to do: the operator running doctor nightly per user or group, keeping
  the results in its database, a drift-over-time chart, and email as a notification channel.
- **Access review in the web app.** `mason access` (people, outside collaborators, teams, deploy keys, webhook
  hosts, `--since` an earlier review, `--stale` keys) is done. Still to do: an Access tab with the same data, a
  "still needed?" sign-off per entry kept in the operator, and a CSV export for audits.
- **Prometheus `/metrics`** for the operator itself (requests, GitHub calls, cache hit rate, rate limit left)
  and an optional exporter for repo stats.

## Handbook and local checks (Mike, 2026-11-24)

The list Mike approved, in the order it was built (PRs #76, #78, #79 and the backlog PR):

1. Done: with no repo name, run in the current checkout (`git remote get-url origin`, GitHub or GitLab).
2. Done: `mason check`, offline and local, no token: required files, `.mason.toml`, ruleset JSON, pinned
   workflows and permissions, a changelog fragment on the branch, one migration head, AGENTS.md links the
   handbook; `--install-hook` for a pre-push hook, and a shared CI step.
3. Done: handbook awareness: `[handbook] profile` and `version` in `.mason.toml`, profiles' files, labels and
   skills, `mason handbook` prints the chapters that apply. Nothing is hard-wired: no handbook unless a repo, a
   user or the defaults name one (`handbook = "owner/repo"`).
4. Done: `mason sync` also syncs the profile's skills into `.claude/skills` with a hash lock (skills-lock.json).
5. Done: `mason adopt`: one PR with `.mason.toml` (profile), AGENTS.md from the handbook template, CLAUDE.md
   and the skills.
6. Done: `--json` on every command.
7. Done: `mason lint` for a defaults repo (mason.toml, rulesets) or a handbook (profiles, skills).
8. Done on the CLI: exceptions with an expiry (`skip_until` with a reason, `mason exceptions`), nightly doctor
   with drift notifications (`mason doctor --save`, `mason drift`), access review (`mason access`).

Next for this part:

- The handbook panel for GitLab projects, and `mason adopt` for GitLab.
- `mason check` results in the web app, from the CI step (an uploaded `--json` report per commit).
- `mason check --fix` for what it can fix on its own (a missing CLAUDE.md, `mason sync` for skills).
- Profiles for GitLab labels (doctor checks GitHub labels only).

## Defaults and rules

- Defaults stored in the operator's database as an alternative to a defaults repo, with history and review.
- Policy packs: shareable sets of groups, rulesets and files (e.g. "OpenSSF baseline", "small OSS project").
- Visual ruleset editor next to the JSON one; diff live ruleset vs defaults before applying.
- Org-level settings (default repo permissions, Actions policies, required workflows) in `[org]` tables.
- CODEOWNERS and branch naming rules checked by doctor.
- Environments in mason.toml: required reviewers, wait timers, which branches may deploy.
- Secrets and variables by name only: which repos lack a secret the group needs, and which are unused.
- The new repo keys (topics, labels, required files) for GitLab groups too.
- Terraform / OpenTofu export of the defaults, for teams that manage GitHub as code.
- Exceptions in the web app: list them (`mason exceptions`) and add one with a reason from a doctor finding.
- Template repos as a first-class concept: "new repo from template" wizard with variables.

## Metrics and stats

- DORA-style numbers: deployment frequency, lead time, change failure rate, time to restore.
- PR review latency (time to first review), reviewer load, PR size distribution.
- Flaky workflow detection (same commit, different outcome) and slowest jobs.
- Long-term history kept in the database so charts go back further than the APIs do.
- JSON export and a shareable read-only dashboard link (CSV export of every list is done).
- Actions cost: minutes, cache and artifact storage per repo and workflow, and the biggest savings.
- Supply chain per release: SBOM, signed provenance (`gh attestation`), and which releases lack them.

## Mason

- Teams and shared workspaces: a team's defaults, repo lists and saved views, with roles.
- A daily digest (email or chat): PRs waiting for you, failed runs, new alerts, new drift.
- A command palette (Ctrl+K) in the web UI that searches repos, PRs and commands at once.
- Repo ownership: an owner per repo (from CODEOWNERS or a topic), last activity, and archive candidates.
- Bulk actions with a preview: rerun failed runs, update a file in N repos, archive stale repos.
- Saved views and filters (e.g. "my PRs needing review across both providers").
- Bulk actions with a preview: update a file in N repos, archive stale repos (rerunning failed runs is done).
- OIDC / SAML sign-in for the operator itself in companies, next to GitHub and GitLab.
- GitHub App mode (installation tokens, fine-grained permissions) as an alternative to OAuth apps.
- Passkeys as a second factor for risky actions (deleting the account, new API keys).
- Per-user rate limit budget and a queue for big jobs, with progress in the UI.
- Redis-backed cache and sessions to run several operator processes.
- Helm chart and a k8s manifest next to the docker-compose example.
- arm64 image (native arm runner or QEMU) next to the amd64 one, and an image vulnerability scan in CI.

## Plugins

- Kubernetes (k3s) plugin: deployments per repo, image versions vs latest release.
- Docker/registry plugin: image ages, vulnerable base images, cleanup of old tags.
- Renovate/Dependabot dashboard: open update PRs by repo, auto-merge policy.
- Sentry/uptime plugin: link errors and incidents to repos and releases.
- Plugin sandboxing: run plugins in a subprocess with only the API calls they declare.
- Plugin settings UI generated from a schema the plugin declares.

## AI

- An agent that proposes fixes as PRs: security alerts, failing workflows, merge conflicts, drift that
  `doctor --fix` can't fix (e.g. missing files that need content).
- "Explain this failure": summarize a failed run's logs next to the run.
- Natural-language console (`mason ask "which repos lack branch protection?"`) that turns into mason commands,
  shown before they run.

## TUI and CLI

- `mason watch`: a live status line for a set of repos.
- Shell completion for repo names and groups.
- Your own keys for the TUI: a `[keys]` table in config.toml (Textual keymaps), e.g. to move F-keys a terminal keeps.
- The same F3/F4/F6 search, filter and sort in the web app's lists.

## Done

- Handbook and local checks: see the list above (current checkout, `--json`, check, lint, handbook, adopt,
  skills lock, exceptions, drift, access review).

- Saved views: a page with its filter and group under a name, in the tab bar (settings.views).
- "New since your last visit" marks in the pull request, issue and run lists (per browser).
- GitLab in the CLI, through glab: `gitlab_groups` in your config, `gitlab:` names in every command that reads GitLab.

- TUI keyboard: Tab / Shift+Tab through every panel and dialog, F1-F10 for help, search, filter and sort.

- Workflow hardening: `mason workflows [--fix]`, doctor's `workflows` check and the web app's Workflows tab.
- More repo settings in mason.toml: topics, labels, Actions permissions, required files and `skip`.
- Mason, the web app, with GitHub and GitLab OAuth, terminal UI, API keys, device login (this PR).
- Plugin marketplace with a signed index; `mason stats`; transport layer with caching.
