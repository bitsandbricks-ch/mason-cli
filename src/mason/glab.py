"""GitLab on this machine: the CLI reaches GitLab through the glab CLI, as it reaches GitHub through gh.

`glab auth login` signs glab in; mason then hands every GitLab call to `glab api`, so it never sees a
GitLab token either. Answers go through the same cache as the web app's (mason.gitlab.GitLab), and the
mason commands for GitLab projects are the web app's too (mason.gitlab): only the transport differs.

Which projects: the GitLab groups and projects in your config (`gitlab_groups`, `gitlab_projects`) or in
the defaults (`gitlab_groups`), named `gitlab:group/project` next to GitHub's `owner/name`. With none set,
mason doesn't touch GitLab, and doesn't need glab, unless you name a `gitlab:` project.
"""

from __future__ import annotations

import contextvars
import os
import subprocess

from mason import config, core
from mason import gitlab as GL
from mason.core import ago, say

INSTALL = "https://gitlab.com/gitlab-org/cli#installation"


class Glab(GL.GitLab):
    """GitLab's REST and GraphQL APIs through `glab api`: mason never sees the token."""

    name = "glab"

    def __init__(self, web: str = "https://gitlab.com", cache: str | None = None):
        web = web.rstrip("/")
        super().__init__("", api_url=f"{web}/api/v4", web=web, cache=cache)
        self.user_agent = "mason"
        self.host = web.split("://", 1)[-1]

    def _auth(self) -> dict:
        return {}

    def run(self, args: list[str], stdin: bytes | None = None) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(["glab", *args], input=stdin, capture_output=True, check=False,
                                  env={**os.environ, "NO_COLOR": "1"})
        except FileNotFoundError as err:
            raise RuntimeError(f"GitLab needs the glab CLI: install it ({INSTALL}), then glab auth login") from err

    def request(self, method: str, url: str, body: bytes | None = None, accept: str = "application/json",
                headers: dict | None = None) -> tuple[int, dict, bytes]:
        path = "graphql" if url == self.graphql_url else self._path(url).lstrip("/")
        args = ["api", "--include", "--method", method, "--hostname", self.host, path]
        for k, v in (headers or {}).items():
            args += ["--header", f"{k}: {v}"]
        if body is not None:
            args += ["--input", "-"]
        self.stats["requests"] += 1
        proc = self.run(args, body)
        status, got, data = parse(proc.stdout)
        if status is None:
            why = proc.stderr.decode(errors="replace").strip()[:300] or f"exit {proc.returncode}"
            raise RuntimeError(f"glab api {method} {path}: {why}")
        res = self.resource(url)
        self._note_rate(got, res)
        if status == 304:
            return 304, got, b""
        if status >= 400:
            self._fail(method, url, status, got, data, res)
        return status, got, data

    def logged_in(self) -> bool:
        return self.run(["auth", "status", "--hostname", self.host]).returncode == 0

    def login(self) -> str:
        """The signed-in user's username (an error when glab isn't signed in to this host)."""
        return (self.api("GET", "/user") or {}).get("username") or "?"


def parse(out: bytes) -> tuple[int | None, dict, bytes]:
    """`glab api --include`'s output -> (status, headers with lowercase names, body); None when it has none."""
    head, sep, data = out.partition(b"\r\n\r\n")
    lines = head.decode(errors="replace").split("\r\n")
    first = lines[0].split()
    if not sep or len(first) < 2 or not first[0].startswith("HTTP/") or not first[1].isdigit():
        return None, {}, b""
    headers = {}
    for line in lines[1:]:
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    return int(first[1]), headers, data


# ── the client of this machine ───────────────────────────────────────────────

# The CLI and the TUI set it: glab may be used. Never in the web app, which has its users' own tokens.
LOCAL: contextvars.ContextVar = contextvars.ContextVar("mason_glab_local", default=False)
_client: Glab | None = None


def web_url() -> str:
    return (os.environ.get("GITLAB_URL") or config.user_config().get("gitlab_url") or "https://gitlab.com").rstrip("/")


def client():
    """GitLab for this context: the web app's for its user, else glab on this machine (None in the web app
    when the user hasn't connected GitLab)."""
    gl = config.GITLAB.get()
    if gl is not None or not LOCAL.get():
        return gl
    global _client
    if _client is None:
        gl = Glab(web_url(), cache=core.CACHE)
        if not gl.logged_in():
            raise RuntimeError(f"Sign in to GitLab first: glab auth login --hostname {gl.host}")
        _client = gl
    return _client


def wanted(cfg) -> tuple[list[str], list[str]]:
    """(GitLab groups, GitLab projects) mason looks after: from MASON_GITLAB_GROUPS, your config or the defaults."""
    mine = config.user_config()
    env = [g.strip() for g in os.environ.get("MASON_GITLAB_GROUPS", "").split(",") if g.strip()]
    groups = env or config._list(mine.get("gitlab_groups")) or config._list((cfg.raw or {}).get("gitlab_groups"))
    projects = config._list(mine.get("gitlab_projects")) + config._list((cfg.raw or {}).get("gitlab_projects"))
    return [g.removeprefix(GL.PREFIX).strip("/") for g in groups], [GL.full(p) for p in projects]


def wanted_here(names: list[str] | None = None) -> bool:
    """Does this machine use GitLab (a gitlab: name, MASON_GITLAB_GROUPS or GitLab in your config)? Before the
    defaults are read, so mason can tell whether it needs gh at all."""
    if any(str(n).startswith(GL.PREFIX) for n in names or []):
        return True
    mine = config.user_config()
    return bool(os.environ.get("MASON_GITLAB_GROUPS", "").strip() or mine.get("gitlab_groups")
                or mine.get("gitlab_projects"))


def projects(cfg) -> dict[str, dict]:
    """{gitlab:path: info} of the projects mason looks after on this machine; {} when none are set."""
    if not LOCAL.get():  # the web app lists its users' projects itself (server.context.gitlab_projects)
        return {}
    groups, extra = wanted(cfg)
    if not (groups or extra):
        return {}
    gl = client()
    if gl is None:
        return {}
    key = ("cli_projects", tuple(groups), tuple(extra), tuple(cfg.exclude))
    cache = gl.caches.space("gl_listing")
    if key not in cache:
        cache[key] = GL.projects(gl, groups, extra, cfg.exclude, mine=False)
    return cache[key]


def split(repos: list[str]) -> tuple[list[str], list[str]]:
    """(GitHub repos, GitLab projects)."""
    return [r for r in repos if not r.startswith(GL.PREFIX)], [r for r in repos if r.startswith(GL.PREFIX)]


def need() -> GL.GitLab:
    gl = client()
    if gl is None:
        raise RuntimeError("connect GitLab first")
    return gl


# ── the commands' GitLab half (the GitHub half is in repos, defaults, issues, stats) ──


def status_rows(cfg, repos: list[str]) -> list[list[str]]:
    rows = GL.status_rows(need(), cfg, repos)
    return [[r["repo"], r["group"], r["released"], "" if r["released"] == "missing" else
             f"{r['ready']}/{r['drafts']}", r["ci"]] for r in rows]


def prs(repos: list[str]) -> int:
    """The open merge requests, like `mason prs` shows PRs; returns how many."""
    rows = GL.mr_rows(need(), repos)
    for repo in repos:
        mine = sorted((r for r in rows if r["repo"] == repo), key=lambda r: r["number"])
        if not mine:
            continue
        say(f"== {repo}")
        for r in mine:
            bits = ["draft" if r["draft"] else "ready", f"pipeline {r['checks']}"]
            if r["review"]:
                bits.append(r["review"])
            if not r["draft"]:
                bits.append(r["merge"])
            if r["auto"]:
                bits.append("auto-merge on")
            say(f"   !{r['number']} {r['title']}  ({r['author'] or '?'}, {r['branch']})")
            say(f"      {' · '.join(bits)}\n      {r['url']}")
    return len(rows)


def runs(repos: list[str], limit: int = 3, failed: bool = False) -> None:
    rows = GL.runs(need(), repos, limit, failed)
    for repo in repos:
        mine = [r for r in rows if r["repo"] == repo]
        if not mine:
            continue
        say(f"== {repo}")
        for r in mine:
            if "error" in r:
                say(f"   error: {r['error']}")
                continue
            say(f"   {r['state'] or '?':<18} {r['name']} · {r['event']} · {r['branch']} · {ago(r['created'])}"
                f"\n      {r['url']}")


def merge(repos: list[str], ctx: dict) -> None:
    gl = need()
    core.for_each(repos, lambda repo, c: GL.merge(gl, repo, c), ctx)


def approve(repos: list[str], yes: bool) -> int:
    """Blocked deployments and manual jobs; asks before each unless `yes`. Returns how many were waiting."""
    gl = need()
    found = GL.waiting(gl, repos)
    for w in found:
        print(f"== {w['repo']}  {w['branch']}  {w['name']} ({ago(w['created'])})")
        print(f"   waits for: {w['waits_for']}\n   {w['url']}")
        verb = "Approve" if w["kind"] == "deployment" else "Play"
        if not yes and not core.dry_run():
            try:
                answer = input(f"   {verb} it? [y/N] ")
            except EOFError:
                answer = ""
            if answer.strip().lower() not in ("y", "yes"):
                print("   left waiting")
                continue
        if core.dry_run():
            print(f"   [dry-run] {verb.lower()} it")
            continue
        try:
            GL.approve(gl, w["repo"], w["kind"], w["id"])
        except RuntimeError as err:
            print(f"   error: {err}")
    return len(found)


def doctor(cfg, repos: list[str], fix: bool = False, auto: bool = True) -> None:
    gl = need()
    core.for_each(repos, lambda repo, c: GL.doctor(gl, cfg, repo, fix, auto), {})


def doctor_report(cfg, repos: list[str]) -> dict[str, dict]:
    """What doctor finds per project, for `mason doctor --summary` (only checks)."""
    from mason import defaults as D
    gl = need()
    text = core.capture(core.for_each, repos, lambda repo, c: GL.doctor(gl, cfg, repo, False, False), {})
    return D.parse_report(text)


def sync(cfg, repos: list[str], only: list[str] | None = None) -> None:
    gl = need()
    core.for_each(repos, lambda repo, c: GL.sync(gl, cfg, repo, only), {})


def issues(repos: list[str], state: str = "open", labels: list[str] | None = None, assignee: str | None = None,
           mine: bool = False, stale_days: int = 0, limit: int = 20) -> None:
    from mason import issues as I
    gl = need()
    if mine:
        assignee = gl.login()

    def report(repo: str, ctx: dict) -> None:
        rows = GL.issues(gl, repo, state, labels, assignee, limit)
        I.show_rows(I.stale(rows, stale_days) if stale_days else rows, state)

    core.for_each(repos, report, {})


def stats(repos: list[str], days: int = 30) -> list[dict]:
    return GL.stats(need(), repos, days)


def security(repos: list[str]) -> None:
    gl = need()

    def one(repo: str, ctx: dict) -> None:
        rows, notes = GL.alerts(gl, repo)
        for n in notes:
            say(f"   {n}")
        if not rows and not notes:
            say("   no open vulnerabilities")
        for a in rows:
            say(f"   {a['severity']:<9} {a['kind']:<20} {a['title'][:80]}\n      {a['url']}")

    core.for_each(repos, one, {})


def releases(cfg, repos: list[str], problems: bool = False) -> None:
    gl = need()
    for info in core.pmap(lambda r: GL.release_info(gl, cfg, r), repos):
        rel = info["release"] or {}
        trouble = ([info["error"]] if info["error"] else []) + \
            [f"missing asset {m}" for m in info["missing"]] + \
            [f"failed {r['name']} ({r['head_branch']})" for r in info["runs"][:1] if r["conclusion"] == "failure"]
        if problems and not trouble:
            continue
        say(f"== {info['repo']}  {rel.get('tag_name') or 'no release'}"
            + (f" ({ago(rel.get('published_at'))})" if rel else ""))
        for t in trouble:
            say(f"   {t}")
        if rel.get("html_url"):
            say(f"   {rel['html_url']}")


def whoami() -> None:
    """How mason reaches GitLab on this machine, and as whom."""
    gl = Glab(web_url())
    try:
        if not gl.logged_in():
            print(f"GitLab: glab isn't signed in to {gl.host} (glab auth login --hostname {gl.host})")
            return
        print(f"GitLab: {gl.login()} on {gl.host}, through glab")
    except RuntimeError as err:
        print(f"GitLab: {err}")
