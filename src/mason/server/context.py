"""Running mason's code for one user: their GitHub transport, their GitLab client and their settings.

Everything here is per request (contextvars), so two users' commands never share a token,
a cache, a dry run setting or output.
"""

from __future__ import annotations

import re
from contextlib import contextmanager

from flask import abort, g, request

from mason import config, core
from mason.cache import Spaces
from mason.server import oauth
from mason.transport import HttpTransport

# A name part is never "." or "..": those would be path steps in the API URL a name goes into
_PART = r"(?!\.\.?(?:/|$|#))[A-Za-z0-9_.-]+"
REPO = re.compile(rf"^{_PART}/{_PART}$")
ORG = re.compile(rf"^{_PART}$")
GITLAB_REPO = re.compile(rf"^gitlab:{_PART}(/{_PART})+$")
# what a list request may name: a repo, or a name mason finds in the orgs, either with #number
NAME = re.compile(rf"^({_PART}/)?{_PART}(#\d+)?$")
SETTING_KEYS = {"defaults": str, "ref": str, "orgs": list, "repos": list, "exclude": list,
                "gitlab_groups": list, "gitlab_repos": list, "theme": str, "plugins_off": list,
                "org_defaults": bool}
# The web app's themes (web/src/themes.js). "" is the default: bricks, or mortar on a light system.
THEMES = ("bricks", "mortar")


class NoTransport:
    """Stands in when a user has no GitHub login: the operator never falls back to a server-side gh."""

    name = "none"
    web = "https://github.com"

    def __init__(self, why: str = "connect GitHub first (Settings › Accounts)"):
        self.why = why
        self.caches = Spaces()

    def __getattr__(self, name):
        def refuse(*_a, **_kw):
            raise RuntimeError(self.why)
        return refuse


def valid_repo(value: str) -> str:
    value = (value or "").strip()
    if not (REPO.match(value) or GITLAB_REPO.match(value)):
        abort(400, f"not a repo name: {value[:80]!r}")
    return value


def number(value, what: str = "number") -> int:
    """A whole number from a request (a PR, issue or run), or 400: "abc" used to end as a 500."""
    try:
        n = int(value or 0)
    except (TypeError, ValueError):
        abort(400, f"{what}: a whole number, not {str(value)[:20]!r}")
    if n < 0:
        abort(400, f"{what}: a whole number, not {n}")
    return n


def user_settings(user) -> dict:
    s = user.settings
    blank = {list: [], str: "", bool: True}  # org_defaults: on unless turned off
    return {k: s.get(k, blank[t]) for k, t in SETTING_KEYS.items()}


def clean_settings(body: dict) -> dict:
    out = {}
    for k, t in SETTING_KEYS.items():
        if k not in body:
            continue
        v = body[k]
        if t is bool:
            if not isinstance(v, bool):
                abort(400, f"{k} must be true or false")
        elif t is list:
            if isinstance(v, str):
                v = [x.strip() for x in v.replace("\n", ",").split(",")]
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                abort(400, f"{k} must be a list of names")
            v = [x.strip() for x in v if x.strip()][:200]
            if any(len(x) > 200 or "\x00" in x for x in v):
                abort(400, f"{k}: a name is too long")
        else:
            if not isinstance(v, str) or len(v) > 300:
                abort(400, f"{k} must be a short text")
            v = v.strip()
        out[k] = v
    bad = [x for x in out.get("repos") or [] if not REPO.match(x)]
    if bad:  # a bare name has no owner: every list that asks GitHub about it would fail
        abort(400, f"extra repos are owner/name: {', '.join(bad[:5])}")
    bad = [x for x in out.get("orgs") or [] if not ORG.match(x)]
    if bad:
        abort(400, f"GitHub orgs are names like acme: {', '.join(bad[:5])}")
    if out.get("theme") and out["theme"] not in THEMES:
        abort(400, f"theme is one of {', '.join(THEMES)}")
    if out.get("defaults") and not (REPO.match(out["defaults"]) or GITLAB_REPO.match(out["defaults"])):
        abort(400, "defaults must be a repo (owner/name) or a GitLab project (gitlab:group/name)")
    return out


@contextmanager
def as_user(dry: bool | None = None):
    """mason's code runs inside this with the signed-in user's GitHub token and GitLab client."""
    user = g.user
    try:
        gh = oauth.github(user) or NoTransport()
        gl = oauth.gitlab(user)
    except RuntimeError as err:
        abort(409, str(err))
    gtoken = config.GITLAB.set(gl)
    named = [str(r).strip() for r in request.args.getlist("repo") if str(r).strip()]
    if request.args.get("fresh") == "1" and named:  # a follow-up on a few repos: only theirs are asked again
        for repo in named[:50]:
            t = gl if repo.startswith("gitlab:") else gh
            if isinstance(t, HttpTransport):
                t.forget_repos([repo])
            elif t is not None:  # the gh CLI: only mason's own status nodes are cached
                t.caches.forget_repo(repo)
    elif request.args.get("fresh") == "1":  # r in the web app: ask again, revalidating with ETags (cheap)
        for t in (gh, gl):
            store = getattr(t, "store", None)
            if store is not None:
                store.stale()
            if t is not None:
                for name in ("nodes", "gl_nodes"):
                    t.caches.pop(name, None)
    try:
        with core.using(gh, dry):
            yield gh, gl
    finally:
        config.GITLAB.reset(gtoken)


def load_config(orgs: list[str] | None = None):
    """This user's config: their settings plus their defaults repo (inside as_user)."""
    s = user_settings(g.user)
    mine = {k: s[k] for k in ("defaults", "ref", "orgs", "repos", "exclude") if s.get(k)}
    mine["org_defaults"] = s.get("org_defaults") is not False
    try:
        return config.load(orgs, mine=mine, env=False)
    except RuntimeError as err:
        abort(422, f"your defaults: {err}")


def gitlab_projects(gl, cfg) -> dict:
    from mason import gitlab as GL
    if gl is None:
        return {}
    s = user_settings(g.user)
    groups = s.get("gitlab_groups") or list((cfg.raw or {}).get("gitlab_groups") or [])
    extra = s.get("gitlab_repos") or []
    key = ("gl_projects", tuple(groups), tuple(extra), tuple(cfg.exclude))
    cache = gl.caches.space("gl_listing")
    if key not in cache:
        cache[key] = GL.projects(gl, groups, extra, cfg.exclude)
    return cache[key]
