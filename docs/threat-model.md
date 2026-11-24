# Threat model

What Mason protects, where it can be reached, and what stops misuse. The controls themselves are
described in [the web app's security model](mason.md#security-model); this page says which threat each
one answers. Update it when a new way in is added (an API, a plugin hook, a webhook, an agent).

## What Mason guards

| Asset | Where it lives |
| --- | --- |
| Users' GitHub and GitLab OAuth tokens | The web app's database, encrypted with `MASON_SECRET_KEY` (Fernet) |
| `MASON_SECRET_KEY` | The environment, or `MASON_DATA/secret.key` (mode 0600) when unset |
| Sessions and API keys | The database, as SHA-256 hashes only |
| Plugin secrets (per user) | The database, encrypted like tokens |
| Actions secret values | Never stored: sealed with the repo's public key and passed on once |
| The repos themselves | GitHub and GitLab; Mason writes to them with the user's own token |
| The audit log | The database, bounded in size and age |

On its own, the CLI and TUI hold no token at all: they call GitHub through the gh CLI (and GitLab
through glab).

## Ways in

| Entry point | Who reaches it | Trust |
| --- | --- | --- |
| Web UI and `/api/v1` | Anyone who can reach the server; open sign-in by default | Untrusted until signed in |
| OAuth callbacks and the device flow | GitHub, GitLab and the browser | Bound to the browser by a short-lived cookie |
| API keys (`mason login`, scripts) | The CLI, TUI and scripts | Scoped `read` or `write`, optional expiry |
| The GitHub proxy for signed-in CLIs | API keys | An allowlist of the calls mason makes |
| The operator page | Operators only, with a browser session | Granted only on the host with `mason operator add` |
| Defaults repos (`mason.toml`, `.mason`) and a repo's `.mason.toml` | Whoever can push to those repos | Input: parsed and validated, never run |
| Installed plugins | Whoever runs Mason (`pip install`, `mason market install`) | Fully trusted code inside the server |
| The plugin index | The marketplace (this repo's `plugins/index.json` by default) | Trusted only with a valid Ed25519 signature |
| Alert webhooks (`alerts` key) | Mason sends to them | Outbound only, `https` only |

## Threats and what answers them

| Threat | Answer |
| --- | --- |
| Someone uses another user's GitHub rights | Every GitHub and GitLab call uses the signed-in user's own token; the server never falls back to one of its own |
| A stolen database leaks tokens | Tokens and plugin secrets are encrypted at rest; sessions and keys are stored hashed |
| Session theft or CSRF | `__Host-`, `Secure`, `HttpOnly`, `SameSite=Lax` cookies; every change needs `X-CSRF-Token` and a matching `Origin`; idle and absolute timeouts |
| A leaked API key does damage | Keys are scoped, can expire, show their last use and can be revoked; creating keys, deleting the account and installing plugins need a browser session |
| A signed-in CLI uses the proxy for more than mason does | Allowlisted methods and paths; deleting repos, changing access, keys, hooks and account settings are never passed on; encoded `..` and slashes are refused |
| Open sign-in fills the disk or the GitHub quota | Throttles per address, per user and for new accounts; caps per user on keys, sessions, settings, secrets and audit rows; `MASON_MAX_USERS` |
| Cross-site scripting | Strict CSP (`self` only, no inline scripts or styles), no `v-html` in the UI, `X-Frame-Options: DENY` |
| A user reads or changes another user's settings | Every setting belongs to one user and is looked up by the session's user on the server; operators can't read them either |
| A tampered plugin index installs bad code | Unsigned or wrongly signed indexes are shown but nothing installs from them; installs happen on the host, never from the web |
| Nobody can tell what happened | Sign-ins, keys, every change and every dry run are audited, with who and how |

## Known limits

- **Plugins run with the server's rights.** An installed plugin can read whatever the server process
  can, for every user. Only install plugins you would run as Mason itself.
- **The built-in GitHub sign-in can't revoke tokens.** Without `GITHUB_CLIENT_SECRET`, Mason deletes its
  copy but the token stays valid at GitHub until the user revokes it there; the UI links to that page.
- **Throttle counters live in memory**, per process: a restart resets them, and several processes count
  separately (the image runs one).
- **`MASON_SECRET_KEY` has no rotation yet.** Changing it makes stored tokens unreadable, so every user
  signs in again.
- TODO (Mike): who owns `MASON_SECRET_KEY` and the OAuth client secrets on a public deployment, and how
  often they rotate (the handbook asks each secret to have an owner and a rotation plan).
