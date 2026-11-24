"""`mason access`: who and what can reach each repo, read only, for an access review.

  people     direct collaborators and their role; outside collaborators are marked
  teams      teams with access and their permission
  keys       deploy keys: read only or write, created, last used
  hooks      webhooks: the host they post to (never the full address: it may carry a secret), events, last answer

mason never changes access. `--since FILE` compares with an earlier review (`mason --json access > review.json`)
and marks what is new since; `--stale DAYS` marks deploy keys unused that long. Reading keys and hooks needs
admin on the repo; what can't be read says so.
"""

from __future__ import annotations

import datetime as dt
import json
import urllib.parse

from mason import core
from mason.core import api_pages

KINDS = ("people", "teams", "keys", "hooks")
ROLES = {"admin": 0, "maintain": 1, "write": 2, "triage": 3, "read": 4}


def _days(stamp: str | None) -> int | None:
    if not stamp:
        return None
    then = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return (dt.datetime.now(dt.timezone.utc) - then).days


def repo_access(repo: str) -> dict:
    out: dict = {"repo": repo, "errors": {}}

    def read(kind: str, path: str) -> list:
        try:
            return api_pages(path)
        except RuntimeError as err:
            out["errors"][kind] = str(err).strip().splitlines()[0][:160]
            return []

    outside = {c.get("login") for c in read("people", f"/repos/{repo}/collaborators?affiliation=outside")}
    direct = read("people", f"/repos/{repo}/collaborators?affiliation=direct")
    out["people"] = sorted(({"login": c.get("login"), "role": c.get("role_name") or "",
                             "outside": c.get("login") in outside} for c in direct),
                           key=lambda p: (ROLES.get(p["role"], 9), p["login"] or ""))
    out["teams"] = [{"team": t.get("slug"), "permission": t.get("permission") or ""}
                    for t in read("teams", f"/repos/{repo}/teams")]
    out["keys"] = [{"id": k.get("id"), "title": k.get("title"), "read_only": bool(k.get("read_only")),
                    "created_at": k.get("created_at"), "last_used": k.get("last_used"),
                    "unused_days": _days(k.get("last_used") or k.get("created_at"))}
                   for k in read("keys", f"/repos/{repo}/keys")]
    out["hooks"] = [{"id": h.get("id"), "host": urllib.parse.urlparse((h.get("config") or {}).get("url") or "").hostname
                     or "", "events": list(h.get("events") or []), "active": h.get("active", True),
                     "last_code": (h.get("last_response") or {}).get("code")}
                    for h in read("hooks", f"/repos/{repo}/hooks")]
    return out


def ident(kind: str, e: dict) -> str:
    """What makes an entry the same one in a later review."""
    return {"people": lambda: f"{e['login']}:{e['role']}", "teams": lambda: f"{e['team']}:{e['permission']}",
            "keys": lambda: f"{e['id']}:{e['read_only']}", "hooks": lambda: f"{e['id']}:{e['host']}"}[kind]()


def known(path: str) -> dict[str, set[str]]:
    """{repo: {kind:ident}} from an earlier `mason --json access` (its result) or a plain list of repos."""
    try:
        with open(path) as f:
            doc = json.load(f)
    except (OSError, ValueError) as err:
        raise RuntimeError(f"{path}: {err}") from err
    rows = doc.get("result", doc) if isinstance(doc, dict) else doc
    out: dict[str, set[str]] = {}
    for r in rows or []:
        out[r["repo"]] = {f"{k}:{ident(k, e)}" for k in KINDS for e in r.get(k) or []}
    return out


def review(repos: list[str], since: str | None = None, stale: int = 0, writers: bool = False) -> list[dict]:
    before = known(since) if since else None
    found = core.pmap(repo_access, repos)
    for r in found:
        for kind in KINDS:
            for e in r[kind]:
                e["new"] = before is not None and f"{kind}:{ident(kind, e)}" not in before.get(r["repo"], set())
                e["stale"] = kind == "keys" and bool(stale) and (e["unused_days"] or 0) >= stale
        if writers:
            r["people"] = [p for p in r["people"] if ROLES.get(p["role"], 9) <= ROLES["write"]]
    return found


def show(repos: list[str], since: str | None = None, stale: int = 0, writers: bool = False) -> None:
    found = review(repos, since, stale, writers)
    core.emit(found)
    if core.json_mode():
        return

    def mark(e: dict) -> str:
        return ("new " if e.get("new") else "") + ("stale" if e.get("stale") else "")

    core.table(["repo", "who", "role", "outside", ""],
               [[r["repo"], p["login"], p["role"], "outside" if p["outside"] else "", mark(p)]
                for r in found for p in r["people"]])
    teams = [[r["repo"], t["team"], t["permission"], mark(t)] for r in found for t in r["teams"]]
    if teams:
        core.say("")
        core.table(["repo", "team", "permission", ""], teams)
    keys = [[r["repo"], k["title"] or "", "read only" if k["read_only"] else "WRITE", core.ago(k["last_used"])
             if k["last_used"] else "never", mark(k)] for r in found for k in r["keys"]]
    if keys:
        core.say("")
        core.table(["repo", "deploy key", "access", "last used", ""], keys)
    hooks = [[r["repo"], h["host"], ",".join(h["events"]), "on" if h["active"] else "off",
              str(h["last_code"] or "-"), mark(h)] for r in found for h in r["hooks"]]
    if hooks:
        core.say("")
        core.table(["repo", "webhook host", "events", "active", "last answer", ""], hooks)
    errors = [f"{r['repo']}: {k}: {e}" for r in found for k, e in r["errors"].items()]
    for e in dict.fromkeys(errors):
        core.say(f"couldn't read {e}")
    new = sum(1 for r in found for k in KINDS for e in r[k] if e.get("new"))
    outside = sum(1 for r in found for p in r["people"] if p["outside"])
    core.say(f"\n{len(found)} repos: {outside} outside collaborator(s)"
             + (f", {new} new since {since}" if since else "") + "  (mason never changes access: review it on GitHub)")
