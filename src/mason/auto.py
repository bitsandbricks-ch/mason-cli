"""`mason auto`: everything a repo's .mason.toml (or its group) lets mason do on its own, in one run.

Run it by hand, from cron, or from a scheduled workflow. Per repo, only what is switched on:

    auto_fix = true             doctor fixes the drift (as `mason doctor --fix`)
    auto_release = true         push the version tag once the version file is ahead of the latest release
    auto_update_branch = true   bring open PRs that are behind their base up to date
    auto_close_stale = 60       close PRs and issues untouched for 60 days (labels keep, pinned, security stay)
    auto_rerun_failed = 1       rerun the failed jobs of each workflow's latest run on the default branch, once
    auto_delete_branches = 14   delete the branches of PRs merged more than 14 days ago
    dependabot = { auto_merge = "minor" }   auto-merge Dependabot PRs up to that kind of update
    alerts = "https://hooks.slack.com/..."  post the problems doctor finds that weren't there last time

Nothing runs where nothing is switched on, so `mason auto` over every repo is safe.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import urllib.parse
import urllib.request

from mason import config, core, defaults, rules, versions
from mason import repos as R
from mason.core import api, say

KEEP_LABELS = {"keep", "pinned", "security"}
LEVELS = {"patch": 0, "minor": 1, "major": 2}
BUMP = re.compile(r"\bfrom v?(\d+)\.(\d+)(?:\.(\d+))? to v?(\d+)\.(\d+)(?:\.(\d+))?")


def run(cfg, repos: list[str]) -> None:
    mores = {r: config.more_of(cfg, r) for r in repos if not r.startswith("gitlab:")}
    checked = [r for r in mores if config.auto(cfg, r, "auto_fix") or mores[r].get("alerts")]
    ctx = defaults.doctor_ctx(cfg, checked, False, True) if checked else {}
    core.for_each(list(mores), one, {"cfg": cfg, "more": mores, "doctor": ctx}, parallel=False)


def one(repo: str, ctx: dict) -> None:
    cfg, more = ctx["cfg"], ctx["more"][repo]
    did = False
    if ctx["doctor"] and repo in ctx["doctor"]["groups"]:
        text = core.capture(defaults.doctor, repo, ctx["doctor"])
        for line in text.rstrip("\n").splitlines():
            say(line)
        if more.get("alerts"):
            alert(repo, str(more["alerts"]), [x[5:] for x in text.splitlines() if x.startswith("   - ")])
        did = True
    steps = (("auto_release", release), ("auto_update_branch", update_branches), ("auto_close_stale", close_stale),
             ("auto_rerun_failed", rerun_failed), ("auto_delete_branches", delete_branches))
    for key, step in steps:
        if more.get(key):
            try:
                step(cfg, repo, more[key])
            except core.RateLimited:
                raise
            except RuntimeError as err:
                say(f"   {key}: {str(err).splitlines()[0][:150]}")
            did = True
    level = (more.get("dependabot") or {}).get("auto_merge") if rules.on(more.get("dependabot")) else None
    if level:
        merge_dependabot(repo, "minor" if level is True else str(level))
        did = True
    if not did:
        say("   nothing to do on its own")


# ── the steps ────────────────────────────────────────────────────────────────


def release(cfg, repo: str, _on) -> None:
    st = versions.state(cfg, repo)
    if not st.get("file"):
        say("   auto_release: no version file")
    elif st.get("todo") and not versions.tag_exists(repo, st["tag"]):
        versions.release(cfg, repo, yes=True)


def update_branches(cfg, repo: str, _on) -> None:
    for p in open_prs(repo):
        if p.get("draft"):
            continue
        full = api("GET", f"/repos/{repo}/pulls/{p['number']}") or {}
        if full.get("mergeable_state") == "behind":
            api("PUT", f"/repos/{repo}/pulls/{p['number']}/update-branch", {})
            say(f"   updated #{p['number']} with {full.get('base', {}).get('ref', 'its base')}")


def close_stale(cfg, repo: str, days) -> None:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=int(days))
    items = api("GET", f"/repos/{repo}/issues?state=open&sort=updated&direction=asc&per_page=100") or []
    for it in items:
        stamp = str(it.get("updated_at") or "2100-01-01T00:00:00Z")
        when = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if when > cutoff or {x.get("name", "").lower() for x in it.get("labels") or []} & KEEP_LABELS:
            continue
        kind = "PR" if it.get("pull_request") else "issue"
        api("POST", f"/repos/{repo}/issues/{it['number']}/comments",
            {"body": f"Closed by mason: no activity for {days} days (`auto_close_stale`). Reopen it if it's still "
                     "needed; a `keep` label stops this."})
        body = {"state": "closed"} if kind == "PR" else {"state": "closed", "state_reason": "not_planned"}
        api("PATCH", f"/repos/{repo}/{'pulls' if kind == 'PR' else 'issues'}/{it['number']}", body)
        say(f"   closed {kind} #{it['number']} {it.get('title', '')[:60]} (untouched since {when:%Y-%m-%d})")


def rerun_failed(cfg, repo: str, attempts) -> None:
    base = (api("GET", f"/repos/{repo}") or {}).get("default_branch") or "main"
    runs = (api("GET", f"/repos/{repo}/actions/runs?branch={urllib.parse.quote(base)}&per_page=50") or {})
    latest: dict = {}
    for r in runs.get("workflow_runs") or []:
        latest.setdefault(r.get("workflow_id"), r)
    for r in latest.values():
        if r.get("status") == "completed" and r.get("conclusion") == "failure" and \
                int(r.get("run_attempt") or 1) <= int(attempts):
            api("POST", f"/repos/{repo}/actions/runs/{r['id']}/rerun-failed-jobs", {})
            say(f"   reran the failed jobs of {r.get('name', 'a run')} (attempt {int(r.get('run_attempt') or 1) + 1})")


def delete_branches(cfg, repo: str, days) -> None:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=int(days))
    info = api("GET", f"/repos/{repo}") or {}
    keep = {info.get("default_branch") or "main"} | {p["head"]["ref"] for p in open_prs(repo)}
    closed = api("GET", f"/repos/{repo}/pulls?state=closed&sort=updated&direction=desc&per_page=100") or []
    gone = []
    for p in closed:
        head = p.get("head") or {}
        merged = p.get("merged_at")
        if not merged or (head.get("repo") or {}).get("full_name") != repo or head.get("ref") in keep:
            continue
        if dt.datetime.fromisoformat(merged.replace("Z", "+00:00")) > cutoff:
            continue
        try:
            api("DELETE", f"/repos/{repo}/git/refs/heads/{head['ref']}")
            gone.append(head["ref"])
        except RuntimeError:  # deleted already, or protected
            pass
    if gone:
        say(f"   deleted {len(gone)} merged branches: {', '.join(gone[:8])}{' ...' if len(gone) > 8 else ''}")


def merge_dependabot(repo: str, level: str) -> None:
    allowed = LEVELS.get(level, 1)
    for p in open_prs(repo):
        if (p.get("user") or {}).get("login") != "dependabot[bot]" or p.get("draft") or p.get("auto_merge"):
            continue
        kind = bump_kind(p.get("title", ""))
        if kind is None or LEVELS[kind] > allowed:
            continue
        merged, why = R.auto_merge(repo, p["number"], "squash")
        say(f"   #{p['number']} {p['title'][:60]}: " + (why[:120] if why else "merged" if merged else "auto-merge on"))


def bump_kind(title: str) -> str | None:
    """'Bump x from 1.2.3 to 1.3.0' -> 'minor'; None when the title says no versions."""
    m = BUMP.search(title)
    if not m:
        return None
    a = [int(x or 0) for x in m.groups()[:3]]
    b = [int(x or 0) for x in m.groups()[3:]]
    return "major" if b[0] != a[0] else "minor" if b[1] != a[1] else "patch"


def open_prs(repo: str) -> list[dict]:
    return api("GET", f"/repos/{repo}/pulls?state=open&per_page=100") or []


# ── alerts ───────────────────────────────────────────────────────────────────


def seen_file():
    return config.config_dir() / "alerts.json"


def alert(repo: str, url: str, problems: list[str]) -> None:
    """Post the problems that weren't there last time to the repo's `alerts` webhook. Only from the
    command line: the web app doesn't send requests to addresses a repo names."""
    if config.OVERRIDE.get() is not None:
        say("   alerts: only `mason auto` on the command line sends them")
        return
    if not url.startswith("https://"):
        say("   alerts: the address must start with https://")
        return
    path = seen_file()
    try:
        seen = json.loads(path.read_text())
    except (OSError, ValueError):
        seen = {}
    new = [p for p in problems if p not in set(seen.get(repo) or [])]
    seen[repo] = problems
    if new and not core.dry_run():
        text = f"mason: {repo} has {len(new)} new problem(s)\n" + "\n".join(f"- {p}" for p in new)
        host = urllib.parse.urlparse(url).hostname or ""
        body = {"content": text[:1900]} if host.endswith(("discord.com", "discordapp.com")) else \
            {"text": text} if host.endswith("slack.com") else {"text": text, "repo": repo, "problems": new}
        req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=15).close()  # noqa: S310 (https only, checked above)
            say(f"   alerts: sent {len(new)} new problem(s)")
        except OSError as err:
            say(f"   alerts: couldn't send ({str(err)[:120]})")
            return
    elif new:
        say(f"   [dry-run] alerts: {len(new)} new problem(s)")
    if not core.dry_run():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(seen, indent=1))
