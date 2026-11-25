# Core and add-ons

Mason's **core** is the CLI and the TUI. The **web app is an add-on** on top of the same core: it calls the
core's functions and adds sign-in, accounts and a browser UI. Everything works from the CLI first; the TUI and the
web app call the same functions (the handbook's `multi-tool` profile). All of it is one package with one version;
the extras pick what gets installed:

| Part | Where | Extra | Needs |
| --- | --- | --- | --- |
| Core: CLI | `src/mason/` without `server/` | none | Python, gh (GitHub), glab (GitLab) |
| Core: TUI | `src/mason/tui.py` | `tui` | Textual |
| Web app add-on | `src/mason/server/`, `web/` | `server` | Flask, SQLAlchemy, cryptography, gunicorn; Node.js to build `web/` |

## The rules

- **The core never imports the add-on.** No module outside `src/mason/server/` imports `mason.server`, Flask,
  Werkzeug, SQLAlchemy or gunicorn. The one door is `mason serve` and `mason operator`, which load the add-on in
  `mason.cli.web_addon` and say how to install it when it's missing.
- **The core imports and runs without the add-on's libraries** (`pipx install "mason-cli[tui]"` is a full CLI and TUI).
- **The add-on has no copies of core logic.** A feature lands in the core first, with a CLI command, then the web
  app shows it.
- `tests/test_boundary.py` checks the first two rules and that the list below is complete.

## Sign-in and tokens

- **CLI and TUI:** they reach GitHub through gh and GitLab through glab, which keep the tokens. `mason login` signs
  them in (`gh auth login`, `glab auth login`). The CLI may read the token gh or glab holds (`gh auth token`) where
  that is simpler, but Mason never stores one.
- **Web app:** every user signs in with their own GitHub or GitLab account (OAuth); every call uses that user's
  own token, kept encrypted in the add-on's database. Only the server holds the OAuth client secret.
- **CLI through the web app:** `mason login <URL>` gets an API key from the add-on instead, and the CLI and TUI go
  through its proxy (below), with no gh or token on that machine.

## The API between them

### What the add-on uses from the core (Python)

The add-on imports these core modules. A change to their functions is a change to the add-on's API: run the web
tests too.

| Module | For |
| --- | --- |
| `mason.core` | output, dry run, the per-request context (`SERVING`, `install_context_stdout`) |
| `mason.config` | defaults, groups, per-user config (`OVERRIDE`, `GITLAB` context variables) |
| `mason.transport` | `HttpTransport` with each user's token; `set_default` |
| `mason.cache` | the shared cache and its budget |
| `mason.gitlab` | GitLab's API with each user's token |
| `mason.repos` | repo lists, status, PRs, merges |
| `mason.defaults` | doctor, sync, fixes |
| `mason.rules` | branch protection and rulesets |
| `mason.branches` | branches |
| `mason.catalog` | every repo setting |
| `mason.versions` | version files, bumps |
| `mason.releases` | releases and tags |
| `mason.packages` | container images |
| `mason.events` | runs, approvals, events |
| `mason.extras` | security alerts and the other extra views |
| `mason.issues` | issues |
| `mason.workflows` | workflow hardening |
| `mason.stats` | stats |
| `mason.handbook` | handbook profiles and adopt |
| `mason.templates` | starter files |
| `mason.plugins` | installed plugins |
| `mason.market` | the signed plugin index |
| `mason.cli` | the web console runs CLI commands (`build_parser`, `main`) |

### What the core uses from the add-on (HTTP)

Only with `mason login <URL>` (or `MASON_SERVER` and `MASON_KEY`): `mason.transport.OperatorTransport`, `mason.login`
and `mason.config.operator_settings` call these endpoints of the add-on's `/api/v1`:

| Endpoint | For |
| --- | --- |
| `POST /api/v1/device/code`, `POST /api/v1/device/token` | the device login that gives the CLI an API key |
| `GET /api/v1/me` | who the key belongs to (`mason whoami`) |
| `GET /api/v1/settings` | the user's defaults repo and orgs saved in the web app |
| `/api/v1/github/rest/...`, `POST /api/v1/github/graphql` | GitHub's APIs through the add-on, with the user's token |

## Later

The add-on may move to its own repo (`mason-web`). The handbook's `multi-tool` profile asks for one package with
the web UI built into it, so that needs a handbook change first (issue #88).
