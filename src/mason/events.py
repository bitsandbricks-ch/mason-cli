"""What happened to a repo, pull request, issue, release or workflow run on GitHub, as one list of events.

Every event is a dict: {at, who, what, detail, more, url, source, state}; `at` is an ISO time, `state` is
"ok", "bad", "warn" or "" (how the web app colours it), `source` is "github" here ("gitlab" in
gitlab.py, "mason" for the audit rows the operator adds). Lists come newest first.

Also the text of a workflow run's page (run_detail), which mason had no view of before.
"""

from __future__ import annotations

import urllib.parse

from mason.core import RateLimited, ago, api

MORE = 4000  # the most text one event carries
TIMELINE_PAGES = 5  # 500 timeline items is plenty for one PR or issue
SKIP = {"subscribed", "unsubscribed", "mentioned", "comment_deleted", "user_blocked"}
GOOD = {"success", "approved", "merged", "completed", "published", "neutral", "skipped"}
BAD = {"failure", "failed", "changes_requested", "timed_out", "cancelled", "startup_failure", "action_required"}


def event(at, what: str, who: str = "", detail: str = "", url: str = "", state: str = "",
          source: str = "github") -> dict:
    """`detail` shows as one line; when it has more than that, all of it (cut at MORE) is in `more`."""
    text = str(detail or "").strip()
    line = first_line(text)
    return {"at": at or "", "who": who or "", "what": what, "detail": line, "url": url or "", "state": state,
            "source": source, "more": text[:MORE] if text and text != line else ""}


def first_line(text, limit: int = 240) -> str:
    """The first line that says something ("== repo" headers of command output don't)."""
    lines = [x.strip() for x in str(text or "").splitlines() if x.strip()]
    line = next((x for x in lines if not x.startswith("==")), lines[0] if lines else "")
    return line if len(line) <= limit else line[: limit - 1] + "…"


def state_of(word) -> str:
    w = str(word or "").lower()
    return "ok" if w in GOOD else "bad" if w in BAD else "warn" if w in ("in_progress", "queued", "waiting",
                                                                          "pending", "requested", "running") else ""


def newest_first(events: list[dict]) -> list[dict]:
    return sorted(events, key=lambda e: e.get("at") or "", reverse=True)


def login(obj) -> str:
    return (obj or {}).get("login") or (obj or {}).get("name") or ""


# ── pull requests and issues: the timeline ───────────────────────────────────


def timeline(repo: str, number: int) -> list[dict]:
    found, page = [], 1
    while page <= TIMELINE_PAGES:
        got = api("GET", f"/repos/{repo}/issues/{number}/timeline?per_page=100&page={page}") or []
        found += got
        if len(got) < 100:
            break
        page += 1
    return found


def from_timeline(e: dict) -> dict | None:
    """One timeline item as an event (None for noise like subscriptions)."""
    kind = e.get("event") or ""
    if kind in SKIP:
        return None
    who = login(e.get("actor")) or login(e.get("user"))
    at = e.get("created_at")
    url = e.get("html_url") or ""
    if kind == "committed":
        author = e.get("author") or {}
        return event(author.get("date"), f"commit {str(e.get('sha') or '')[:7]}", author.get("name", ""),
                     e.get("message"), url)
    if kind == "commented":
        return event(at, "commented", who, e.get("body"), url)
    if kind == "reviewed":
        st = str(e.get("state") or "").lower()
        return event(e.get("submitted_at"), f"review: {st.replace('_', ' ')}", who, e.get("body"), url, state_of(st))
    if kind in ("labeled", "unlabeled"):
        return event(at, f"{'+' if kind == 'labeled' else '-'}label {(e.get('label') or {}).get('name', '')}", who)
    if kind in ("assigned", "unassigned"):
        return event(at, f"{kind} {login(e.get('assignee'))}", who)
    if kind in ("review_requested", "review_request_removed"):
        whom = login(e.get("requested_reviewer")) or (e.get("requested_team") or {}).get("name", "")
        return event(at, f"{'asked' if kind == 'review_requested' else 'no longer asks'} {whom} for a review", who)
    if kind == "ready_for_review":
        return event(at, "marked ready for review", who, state="ok")
    if kind == "convert_to_draft":
        return event(at, "turned back into a draft", who, state="warn")
    if kind in ("auto_merge_enabled", "auto_squash_enabled", "auto_rebase_enabled"):
        how = {"auto_squash_enabled": " (squash)", "auto_rebase_enabled": " (rebase)"}.get(kind, "")
        return event(at, f"auto-merge on{how}", who, state="ok")
    if kind == "auto_merge_disabled":
        return event(at, "auto-merge off", who, e.get("reason") or "", state="warn")
    if kind == "merged":
        return event(at, "merged", who, f"commit {str(e.get('commit_id') or '')[:7]}", state="ok")
    if kind == "closed":
        return event(at, "closed", who, e.get("state_reason") or "", state="warn")
    if kind == "reopened":
        return event(at, "reopened", who)
    if kind == "renamed":
        r = e.get("rename") or {}
        return event(at, "renamed", who, f"{r.get('from', '')} → {r.get('to', '')}")
    if kind == "head_ref_force_pushed":
        return event(at, "force-pushed the branch", who, state="warn")
    if kind == "head_ref_deleted":
        return event(at, "deleted the branch", who)
    if kind == "head_ref_restored":
        return event(at, "restored the branch", who)
    if kind == "base_ref_changed":
        return event(at, "changed the base branch", who)
    if kind == "cross-referenced":
        src = (e.get("source") or {}).get("issue") or {}
        where = ((src.get("repository") or {}).get("full_name") or "")
        return event(at, f"mentioned in {where}#{src.get('number', '')}", who, src.get("title"), src.get("html_url"))
    if kind == "referenced":
        return event(at, f"referenced by commit {str(e.get('commit_id') or '')[:7]}", who, url=e.get("commit_url", ""))
    if kind in ("milestoned", "demilestoned"):
        return event(at, f"{'added to' if kind == 'milestoned' else 'removed from'} milestone "
                         f"{(e.get('milestone') or {}).get('title', '')}", who)
    if kind == "deployed":
        return event(at, "deployed", who, state="ok")
    if kind == "line-commented":
        notes = e.get("comments") or [{}]
        c = notes[0]
        return event(c.get("created_at"), f"commented on {c.get('path', 'a line')}", login(c.get("user")),
                     c.get("body"), c.get("html_url"))
    return event(at, kind.replace("_", " ").replace("-", " ") or "event", who, url=url)


def pr_events(repo: str, number: int) -> list[dict]:
    """A pull request: opened, every timeline item, and the checks on its newest commit."""
    p = api("GET", f"/repos/{repo}/pulls/{number}") or {}
    out = [event(p.get("created_at"), "opened" + (" as a draft" if p.get("draft") else ""), login(p.get("user")),
                 p.get("title"), p.get("html_url"))]
    out += [x for x in (from_timeline(e) for e in timeline(repo, number)) if x]
    sha = (p.get("head") or {}).get("sha")
    if sha:
        out += check_events(repo, sha)
    return newest_first(out)


def issue_events(repo: str, number: int) -> list[dict]:
    i = api("GET", f"/repos/{repo}/issues/{number}") or {}
    out = [event(i.get("created_at"), "opened", login(i.get("user")), i.get("title"), i.get("html_url"))]
    out += [x for x in (from_timeline(e) for e in timeline(repo, number)) if x]
    return newest_first(out)


def check_events(repo: str, sha: str) -> list[dict]:
    try:
        runs = (api("GET", f"/repos/{repo}/commits/{sha}/check-runs?per_page=100") or {}).get("check_runs") or []
    except RateLimited:
        raise
    except RuntimeError:
        return []
    out = []
    for c in runs:
        word = c.get("conclusion") or c.get("status")
        took = duration(c.get("started_at"), c.get("completed_at"))
        out.append(event(c.get("completed_at") or c.get("started_at"), f"check {c.get('name', '?')}: {word}",
                         (c.get("app") or {}).get("slug", ""), took, c.get("html_url") or c.get("details_url"),
                         state_of(word)))
    return out


def duration(start, end) -> str:
    from datetime import datetime
    if not start or not end:
        return ""
    try:
        secs = int((datetime.fromisoformat(end.replace("Z", "+00:00"))
                    - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds())
    except ValueError:
        return ""
    return f"took {secs // 60}m {secs % 60}s" if secs >= 60 else f"took {secs}s"


# ── a repo: its activity feed and workflow runs ──────────────────────────────


def from_feed(e: dict, web: str = "https://github.com") -> dict | None:
    """One /repos/{repo}/events item (GitHub's activity feed) as an event."""
    kind, p = e.get("type") or "", e.get("payload") or {}
    who, at, repo = login(e.get("actor")), e.get("created_at"), (e.get("repo") or {}).get("name", "")
    if kind == "PushEvent":
        ref = str(p.get("ref") or "").removeprefix("refs/heads/")
        commits = p.get("commits") or []
        n = p.get("size") if p.get("size") is not None else len(commits)
        msg = commits[-1].get("message") if commits else ""
        what = f"pushed {n} commit{'' if n == 1 else 's'} to {ref}" if n else f"pushed to {ref}"
        head = p.get("head") or ""
        return event(at, what, who, msg, f"{web}/{repo}/commit/{head}" if head else "")
    if kind == "PullRequestEvent":
        pr = p.get("pull_request") or {}
        action = "merged" if p.get("action") == "closed" and pr.get("merged") else p.get("action", "")
        return event(at, f"{action} PR #{pr.get('number') or p.get('number', '')}", who, pr.get("title"),
                     pr.get("html_url"), "ok" if action == "merged" else "")
    if kind == "PullRequestReviewEvent":
        pr, rv = p.get("pull_request") or {}, p.get("review") or {}
        st = str(rv.get("state") or "").lower()
        return event(at, f"review on PR #{pr.get('number', '')}: {st.replace('_', ' ')}", who, pr.get("title"),
                     rv.get("html_url") or pr.get("html_url"), state_of(st))
    if kind in ("IssueCommentEvent", "PullRequestReviewCommentEvent", "CommitCommentEvent"):
        c = p.get("comment") or {}
        on = p.get("issue") or p.get("pull_request") or {}
        where = f" on #{on['number']}" if on.get("number") else ""
        return event(at, f"commented{where}", who, c.get("body"), c.get("html_url"))
    if kind == "IssuesEvent":
        i = p.get("issue") or {}
        return event(at, f"{p.get('action', '')} issue #{i.get('number', '')}", who, i.get("title"), i.get("html_url"))
    if kind == "ReleaseEvent":
        r = p.get("release") or {}
        return event(at, f"{p.get('action', '')} release {r.get('tag_name', '')}", who, r.get("name"),
                     r.get("html_url"), "ok")
    if kind in ("CreateEvent", "DeleteEvent"):
        verb = "created" if kind == "CreateEvent" else "deleted"
        return event(at, f"{verb} {p.get('ref_type', '')} {p.get('ref') or ''}".strip(), who,
                     state="" if kind == "CreateEvent" else "warn")
    if kind == "WatchEvent":
        return event(at, "starred", who)
    if kind == "ForkEvent":
        f = p.get("forkee") or {}
        return event(at, "forked", who, f.get("full_name"), f.get("html_url"))
    if kind == "MemberEvent":
        return event(at, f"{p.get('action', '')} member {login(p.get('member'))}", who)
    if kind == "PublicEvent":
        return event(at, "made public", who, state="warn")
    if kind == "GollumEvent":
        return event(at, "edited the wiki", who)
    return event(at, kind.removesuffix("Event") or "event", who)


def run_event(r: dict) -> dict:
    word = r.get("conclusion") or r.get("status")
    where = r.get("head_branch") or ""
    msg = first_line((r.get("head_commit") or {}).get("message")) or r.get("display_title") or ""
    return event((r.get("updated_at") if r.get("conclusion") else None) or r.get("created_at"),
                 f"run {r.get('name', '?')}: {word}", login(r.get("triggering_actor")) or login(r.get("actor")),
                 f"{r.get('event', '')} on {where}" + (f": {msg}" if msg else "") if where else msg,
                 r.get("html_url"), state_of(word))


def repo_events(repo: str, web: str = "https://github.com", limit: int = 50) -> list[dict]:
    """GitHub's activity feed of the repo (pushes, PRs, reviews, releases, tags...) and its newest runs."""
    feed = api("GET", f"/repos/{repo}/events?per_page={limit}") or []
    out = [x for x in (from_feed(e, web) for e in feed) if x]
    try:
        runs = (api("GET", f"/repos/{repo}/actions/runs?per_page=15") or {}).get("workflow_runs") or []
    except RateLimited:
        raise
    except RuntimeError:
        runs = []
    out += [run_event(r) for r in runs]
    return newest_first(out)


# ── a release ────────────────────────────────────────────────────────────────


def release_events(repo: str, tag: str) -> list[dict]:
    """A release: created, published, each asset uploaded, and the workflow runs of its tag."""
    q = urllib.parse.quote(tag, safe="")
    rel = api("GET", f"/repos/{repo}/releases/tags/{q}") or {}
    who, url = login(rel.get("author")), rel.get("html_url", "")
    out = [event(rel["created_at"], f"created the release {tag}", who, f"on {rel.get('target_commitish') or '?'}", url)
           ] if rel.get("created_at") else []
    if rel.get("published_at"):
        kind = "pre-release" if rel.get("prerelease") else "release"
        out.append(event(rel.get("published_at"), f"published the {kind} {rel.get('name') or tag}", who, url=url,
                         state="ok"))
    elif rel.get("draft"):
        out.append(event(rel.get("created_at"), "saved as a draft", who, url=url, state="warn"))
    for a in rel.get("assets") or []:
        size = f"{(a.get('size') or 0) / 1024:.0f} KB, {a.get('download_count', 0)} downloads"
        out.append(event(a.get("created_at"), f"uploaded {a.get('name')}", login(a.get("uploader")), size,
                         a.get("browser_download_url")))
    try:
        runs = (api("GET", f"/repos/{repo}/actions/runs?branch={q}&per_page=20") or {}).get("workflow_runs") or []
    except RateLimited:
        raise
    except RuntimeError:
        runs = []
    out += [run_event(r) for r in runs if r.get("head_branch") == tag]
    return newest_first(out)


# ── a workflow run ───────────────────────────────────────────────────────────


def run_jobs(repo: str, run_id: int) -> tuple[dict, list[dict]]:
    run = api("GET", f"/repos/{repo}/actions/runs/{int(run_id)}") or {}
    got = api("GET", f"/repos/{repo}/actions/runs/{int(run_id)}/jobs?filter=latest&per_page=100") or {}
    jobs = got.get("jobs") or []
    return run, jobs


def run_events(repo: str, run_id: int) -> list[dict]:
    """A run: started, each job and failed step with times, and its end."""
    run, jobs = run_jobs(repo, run_id)
    out = [event(run.get("created_at"), f"started by {run.get('event', '?')}",
                 login(run.get("triggering_actor")) or login(run.get("actor")),
                 f"{run.get('head_branch', '')} {str(run.get('head_sha') or '')[:7]}", run.get("html_url"))]
    for j in jobs:
        word = j.get("conclusion") or j.get("status")
        out.append(event(j.get("completed_at") or j.get("started_at"), f"job {j.get('name')}: {word}",
                         j.get("runner_name") or "", duration(j.get("started_at"), j.get("completed_at")),
                         j.get("html_url"), state_of(word)))
        for s in j.get("steps") or []:
            if s.get("conclusion") in BAD:
                out.append(event(s.get("completed_at"), f"step {s.get('name')}: {s.get('conclusion')}", "",
                                 f"in {j.get('name')}", j.get("html_url"), "bad"))
    if run.get("conclusion"):
        out.append(event(run.get("updated_at"), f"finished: {run['conclusion']}", "",
                         duration(run.get("run_started_at") or run.get("created_at"), run.get("updated_at")),
                         run.get("html_url"), state_of(run["conclusion"])))
    return newest_first(out)


def run_detail(repo: str, run_id: int) -> str:
    """The text of a run's page: what ran, on what, how it ended, every job with its steps."""
    run, jobs = run_jobs(repo, run_id)
    word = run.get("conclusion") or run.get("status") or "?"
    head = run.get("head_commit") or {}
    lines = [f"{run.get('name', '?')} #{run.get('run_number', '')}", run.get("html_url", ""), "",
             f"  state    {word}" + (f" (attempt {run['run_attempt']})" if (run.get("run_attempt") or 1) > 1 else ""),
             f"  event    {run.get('event', '?')} by "
             f"{login(run.get('triggering_actor')) or login(run.get('actor')) or '?'}",
             f"  branch   {run.get('head_branch', '')} @ {str(run.get('head_sha') or '')[:7]}",
             f"  commit   {first_line(head.get('message'))}",
             f"  started  {ago(run.get('run_started_at') or run.get('created_at'))}"
             + (f", {duration(run.get('run_started_at') or run.get('created_at'), run.get('updated_at'))}"
                if run.get("conclusion") else ""),
             f"  file     {run.get('path', '')}", "", f"Jobs ({len(jobs)}):"]
    for j in jobs:
        jw = j.get("conclusion") or j.get("status") or "?"
        took = duration(j.get("started_at"), j.get("completed_at"))
        lines.append(f"  {jw:<10} {j.get('name')}" + (f"  ({took.removeprefix('took ')})" if took else ""))
        for s in j.get("steps") or []:
            sw = s.get("conclusion") or s.get("status") or "?"
            if sw in ("success", "skipped") and jw == "success":
                continue
            lines.append(f"    {'- ' if sw in BAD else '  '}{sw:<10} {s.get('name')}")
        if jw in BAD:
            lines.append(f"             {j.get('html_url', '')}")
    return "\n".join(lines)
