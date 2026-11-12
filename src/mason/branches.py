"""The branches of one repo: each one's last commit, how far it is ahead of and behind the default branch,
whether it is merged into it, whether anything protects it, and the newest PR (or MR) that came from it.
Deleting one refuses the default branch and protected ones; GitHub and GitLab still have the last word.

    mason branches web                 the list
    mason branches web delete a b      delete branches a and b (asks first; --dry-run only says it)
    mason branches web delete --merged delete every merged branch that isn't the default or protected

The web app's repo page shows the same list (GET /api/v1/repo/branches) and deletes from it.
"""

from __future__ import annotations

import fnmatch
import re
import urllib.parse

from mason import core
from mason.core import ago

LIMIT = 500  # branches read at most; the rest is counted, not listed
NAME = re.compile(r"^[^\x00-\x20~^:?*\[\\]+$")  # what git allows in a branch name (roughly), and no spaces

GH_QUERY = """query($owner: String!, $name: String!, $base: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    refs(refPrefix: "refs/heads/", first: 100, after: $after) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        name
        branchProtectionRule { pattern }
        compare(headRef: $base) { aheadBy behindBy }
        target { ... on Commit { oid committedDate messageHeadline author { name user { login } } } }
        associatedPullRequests(first: 1, orderBy: {field: UPDATED_AT, direction: DESC}) {
          nodes { number title state isDraft url }
        }
      }
    }
  }
}"""


def valid_name(name) -> str:
    """A branch name from outside (the web app, the command line), or ValueError."""
    name = str(name or "").strip()
    if not name or len(name) > 250 or not NAME.match(name) or ".." in name or name.startswith(("-", "/")) \
            or name.endswith(("/", ".", ".lock")):
        raise ValueError(f"not a branch name: {name[:80]!r}")
    return name


def row(name: str, default: str, *, sha="", date="", author="", message="", ahead=None, behind=None,
        merged=False, protected=None, pr=None, url="") -> dict:
    is_default = name == default
    return {"name": name, "default": is_default, "protected": list(protected or []), "sha": sha, "date": date,
            "ago": ago(date) if date else "", "author": author, "message": message, "ahead": ahead,
            "behind": behind, "merged": bool(merged) and not is_default, "pr": pr, "url": url,
            "deletable": not is_default and not protected}


def ordered(rows: list[dict]) -> list[dict]:
    """The default branch first, then the newest commit first (a-z on a tie)."""
    rows = sorted(rows, key=lambda r: r["name"])
    rows.sort(key=lambda r: r["date"] or "", reverse=True)
    rows.sort(key=lambda r: not r["default"])
    return rows


# ── GitHub ───────────────────────────────────────────────────────────────────


def _ref_matches(pattern: str, name: str, default: str) -> bool:
    if pattern == "~ALL":
        return True
    if pattern == "~DEFAULT_BRANCH":
        return name == default
    ref = f"refs/heads/{name}"
    return fnmatch.fnmatchcase(ref, pattern if pattern.startswith("refs/") else f"refs/heads/{pattern}")


def ruleset_guards(repo: str) -> list[tuple[str, list[str], list[str]]]:
    """(name, include, exclude) of every active branch ruleset on the repo (its org's too). A repo the user
    can't read rulesets of has none here: GitHub still refuses a delete they don't allow."""
    try:
        listed = core.api("GET", f"/repos/{repo}/rulesets?includes_parents=true&per_page=100") or []
    except core.RateLimited:
        raise
    except RuntimeError:
        return []
    out = []
    for item in listed:
        if item.get("target", "branch") != "branch" or item.get("enforcement", "active") != "active":
            continue
        try:
            rs = core.api("GET", f"/repos/{repo}/rulesets/{int(item['id'])}") or {}
        except core.RateLimited:
            raise
        except (RuntimeError, KeyError, ValueError):
            continue
        if rs.get("target", "branch") != "branch" or rs.get("enforcement", "active") != "active":
            continue
        cond = (rs.get("conditions") or {}).get("ref_name") or {}
        out.append((rs.get("name") or item.get("name") or "ruleset", list(cond.get("include") or ["~ALL"]),
                    list(cond.get("exclude") or [])))
    return out


def guarded_by(name: str, default: str, guards) -> list[str]:
    def hit(patterns):
        return any(_ref_matches(p, name, default) for p in patterns)

    return [f"ruleset {n}" for n, inc, exc in guards if hit(inc) and not hit(exc)]


def _pr_of(node: dict) -> dict | None:
    prs = ((node.get("associatedPullRequests") or {}).get("nodes")) or []
    if not prs:
        return None
    p = prs[0]
    state = str(p.get("state") or "").lower()
    if state == "open" and p.get("isDraft"):
        state = "draft"
    return {"number": p.get("number"), "title": p.get("title") or "", "state": state, "url": p.get("url") or ""}


def github(repo: str) -> dict:
    """{"default", "branches": [row], "total", "url"} of a GitHub repo."""
    info = core.api("GET", f"/repos/{repo}") or {}
    default = info.get("default_branch") or "main"
    owner, _, name = repo.partition("/")
    nodes, after, total = [], None, 0
    while len(nodes) < LIMIT:
        got = core.graphql(GH_QUERY, owner=owner, name=name, base=default, after=after)
        refs = ((got.get("repository") or {}).get("refs")) or {}
        total = refs.get("totalCount") or 0
        nodes += refs.get("nodes") or []
        page = refs.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")
    guards = ruleset_guards(repo)
    web = f"{getattr(core.transport(), 'web', 'https://github.com')}/{repo}"
    rows = []
    for n in nodes[:LIMIT]:
        c = n.get("target") or {}
        who = c.get("author") or {}
        cmp = n.get("compare") or None
        # compare(headRef: default) on the branch: the default's commits the branch lacks are "aheadBy"
        ahead = cmp.get("behindBy") if cmp else None
        behind = cmp.get("aheadBy") if cmp else None
        pr = _pr_of(n)
        guard = guarded_by(n["name"], default, guards)
        if n.get("branchProtectionRule"):
            guard.insert(0, "branch protection")
        rows.append(row(n["name"], default, sha=c.get("oid", ""), date=c.get("committedDate", ""),
                        author=(who.get("user") or {}).get("login") or who.get("name") or "",
                        message=c.get("messageHeadline", ""), ahead=ahead, behind=behind,
                        merged=ahead == 0 or (pr or {}).get("state") == "merged", protected=guard, pr=pr,
                        url=f"{web}/tree/{urllib.parse.quote(n['name'], safe='/')}"))
    return {"default": default, "branches": ordered(rows), "total": max(total, len(rows)), "url": f"{web}/branches"}


def delete_github(repo: str, name: str) -> None:
    core.api("DELETE", f"/repos/{repo}/git/refs/heads/{urllib.parse.quote(name, safe='/')}")


# ── GitLab ───────────────────────────────────────────────────────────────────


def gitlab(gl, repo: str) -> dict:
    """The same for a GitLab project (GitLab says merged and protected itself; it has no ahead/behind here)."""
    proj = gl.project(repo)
    info = gl.api("GET", proj) or {}
    default = info.get("default_branch") or "main"
    web = info.get("web_url") or ""
    items = gl.pages(f"{proj}/repository/branches", limit=LIMIT)
    mrs: dict[str, dict] = {}
    for m in gl.pages(f"{proj}/merge_requests?state=all&order_by=updated_at&sort=desc", limit=300):
        if m.get("source_project_id") not in (None, info.get("id")) or m.get("source_branch") in mrs:
            continue
        state = {"opened": "open", "locked": "open"}.get(m.get("state"), m.get("state") or "")
        if state == "open" and (m.get("draft") or m.get("work_in_progress")):
            state = "draft"
        mrs[m.get("source_branch")] = {"number": m.get("iid"), "title": m.get("title") or "", "state": state,
                                       "url": m.get("web_url") or ""}
    rows = []
    for b in items[:LIMIT]:
        c = b.get("commit") or {}
        pr = mrs.get(b["name"])
        rows.append(row(b["name"], default, sha=c.get("id", ""), date=c.get("committed_date") or "",
                        author=c.get("author_name") or "", message=c.get("title") or "",
                        merged=b.get("merged") or (pr or {}).get("state") == "merged",
                        protected=["protected branch"] if b.get("protected") else [], pr=pr,
                        url=b.get("web_url") or ""))
    return {"default": default, "branches": ordered(rows), "total": len(items),
            "url": f"{web}/-/branches" if web else ""}


def delete_gitlab(gl, repo: str, name: str) -> None:
    gl.write("DELETE", f"{gl.project(repo)}/repository/branches/{urllib.parse.quote(name, safe='')}")


# ── both ─────────────────────────────────────────────────────────────────────


def listing(repo: str, gl=None) -> dict:
    if repo.startswith("gitlab:"):
        if gl is None:
            raise RuntimeError("connect GitLab first")
        return gitlab(gl, repo)
    return github(repo)


def delete(repo: str, names: list[str], gl=None, merged: bool = False,
           dry: bool | None = None) -> tuple[list[str], bool]:
    """Delete branches (and with `merged`, every merged one besides): (what happened, line by line; all went).
    The list is read first, so the default branch, protected ones and names that aren't there are refused here."""
    dry = core.dry_run() if dry is None else dry
    have = {r["name"]: r for r in listing(repo, gl)["branches"]}
    wanted = list(dict.fromkeys(names))
    if merged:
        wanted += [n for n, r in have.items() if r["merged"] and r["deletable"] and n not in wanted]
    lines, ok = [], True
    if not wanted:
        return ["no branch to delete" + (" (none is merged)" if merged else "")], True
    for n in wanted:
        r = have.get(n)
        if r is None:
            lines.append(f"skipped {n}: no such branch")
            ok = False
            continue
        if r["default"]:
            lines.append(f"skipped {n}: it's the default branch")
            ok = False
            continue
        if r["protected"]:
            lines.append(f"skipped {n}: protected ({', '.join(r['protected'])})")
            ok = False
            continue
        pr = r.get("pr") or {}
        closes = f" (its open {'MR !' if repo.startswith('gitlab:') else 'PR #'}{pr.get('number')} closes)" \
            if pr.get("state") in ("open", "draft") else ""
        if dry:
            lines.append(f"[dry-run] delete {n}{closes}")
            continue
        try:
            if repo.startswith("gitlab:"):
                delete_gitlab(gl, repo, n)
            else:
                delete_github(repo, n)
            lines.append(f"deleted {n}{closes}")
        except core.RateLimited:
            raise
        except RuntimeError as err:
            lines.append(f"failed: {n}: {str(err).splitlines()[0][:200]}")
            ok = False
    return lines, ok


def show(data: dict, mark: str = "#") -> None:
    """The list as a table (the CLI); `mark` is "!" for GitLab's MRs."""
    rows = data["branches"]
    if not rows:
        core.say("no branches")
        return
    out = []
    for r in rows:
        if r["default"]:
            state = "default"
        elif r["merged"]:
            state = "merged"
        elif r["ahead"] is not None:
            state = f"+{r['ahead']} -{r['behind']}"
        else:
            state = ""
        p = r["pr"]
        out.append([r["name"], state, r["ago"] or "-", (r["author"] or "-")[:20],
                    "protected" if r["protected"] else "", f"{mark}{p['number']} {p['state']}" if p else ""])
    core.table(["branch", "state", "commit", "by", "", "PR"], out)
    if data["total"] > len(rows):
        core.say(f"... and {data['total'] - len(rows)} more")
