"""Doctor over time: `mason doctor --save` keeps each run, `mason drift` says what changed since.

    mason drift --now --notify https://hooks.slack.com/...   # nightly from cron or a scheduled workflow

`--now` runs doctor (checks only) and saves the result first. Each run is a JSON file in the history folder
(MASON_HISTORY, else ~/.local/state/mason/doctor; `--history DIR` for one run). `mason drift` compares the newest
run with the one before (`--days N`: with the newest run at least N days older) and lists, per repo, the new
problems and the fixed ones, then a line per run: how many repos were off. `--notify URL` posts the new
problems to a Slack, Discord or other https webhook, like the `alerts` key does for `mason auto`; only from the
command line. Runs older than `--keep` days (90) are deleted when a new one is saved.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

from mason import config, core, defaults


def folder(where: str | None = None) -> Path:
    if where or os.environ.get("MASON_HISTORY"):
        return Path(os.path.expanduser(where or os.environ["MASON_HISTORY"]))
    state = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return Path(state) / "mason" / "doctor"


def save(results: dict[str, dict], where: str | None = None, keep: int = 90,
         now: dt.datetime | None = None) -> Path:
    now = now or dt.datetime.now(dt.UTC)
    root = folder(where)
    root.mkdir(parents=True, exist_ok=True)
    doc = {"when": now.isoformat(timespec="seconds"),
           "repos": {r: {"problems": v.get("problems") or [], "error": v.get("error") or ""}
                     for r, v in results.items() if not v.get("reference")}}
    path = root / f"{now.strftime('%Y-%m-%dT%H%M%S')}.json"
    path.write_text(json.dumps(doc, indent=1))
    cut = now - dt.timedelta(days=keep)
    for old in runs(where):
        if dt.datetime.fromisoformat(old["when"]) < cut:
            (root / old["file"]).unlink(missing_ok=True)
    return path


def runs(where: str | None = None) -> list[dict]:
    """The saved runs, oldest first: {when, file, repos}."""
    out = []
    for f in sorted(folder(where).glob("*.json")):
        try:
            doc = json.loads(f.read_text())
            out.append({"when": doc["when"], "file": f.name, "repos": doc.get("repos") or {}})
        except (OSError, ValueError, KeyError):
            continue
    return out


def compare(before: dict, after: dict) -> list[dict]:
    """Per repo of `after`: problems that are new, and problems of `before` that are gone."""
    out = []
    for repo in sorted(set(before["repos"]) | set(after["repos"])):
        old = set((before["repos"].get(repo) or {}).get("problems") or [])
        now = (after["repos"].get(repo) or {}).get("problems") or []
        new = [p for p in now if p not in old]
        fixed = sorted(old - set(now)) if repo in after["repos"] else []
        if new or fixed:
            out.append({"repo": repo, "new": new, "fixed": fixed})
    return out


def pick(saved: list[dict], days: int) -> tuple[dict | None, dict | None]:
    """(the run to compare with, the newest run)."""
    if not saved:
        return None, None
    newest = saved[-1]
    if not days:
        return (saved[-2] if len(saved) > 1 else None), newest
    cut = dt.datetime.fromisoformat(newest["when"]) - dt.timedelta(days=days)
    older = [r for r in saved[:-1] if dt.datetime.fromisoformat(r["when"]) <= cut]
    return (older[-1] if older else saved[0] if len(saved) > 1 else None), newest


def notify(url: str, changes: list[dict]) -> None:
    from mason import auto
    new = [(c["repo"], p) for c in changes for p in c["new"]]
    if not new:
        return
    if config.OVERRIDE.get() is not None:
        core.say("notify: only `mason drift` on the command line sends them")
        return
    text = f"mason: {len(new)} new problem(s) in {len({r for r, _ in new})} repo(s)\n" + "\n".join(
        f"- {r}: {p}" for r, p in new)
    core.say(auto.post(url, text, {"problems": [{"repo": r, "problem": p} for r, p in new]}))


def drift(cfg, repos: list[str], now: bool = False, days: int = 0, url: str | None = None,
          where: str | None = None, keep: int = 90) -> None:
    if now:
        path = save(defaults.report(cfg, repos), where, keep)
        if not core.json_mode():
            core.say(f"saved {path}")
    saved = runs(where)
    before, after = pick(saved, days)
    if after is None:
        raise RuntimeError(f"No saved doctor runs in {folder(where)}: mason doctor --save (or mason drift --now)")
    names = set(repos)
    keep_repos = lambda run: {**run, "repos": {r: v for r, v in run["repos"].items() if r in names}} if names else run  # noqa: E731
    changes = compare(keep_repos(before), keep_repos(after)) if before else []
    trend = [{"when": r["when"], "off": sum(1 for v in keep_repos(r)["repos"].values() if v["problems"] or v["error"]),
              "problems": sum(len(v["problems"]) for v in keep_repos(r)["repos"].values()),
              "repos": len(keep_repos(r)["repos"])} for r in saved[-10:]]
    core.emit({"since": before["when"] if before else None, "newest": after["when"], "changes": changes,
               "trend": trend})
    if not core.json_mode():
        if not before:
            core.say(f"one run so far ({after['when']}): nothing to compare with yet")
        elif not changes:
            core.say(f"no change since {before['when']}")
        for c in changes:
            core.say(f"== {c['repo']}")
            for p in c["new"]:
                core.say(f"   + {p}")
            for p in c["fixed"]:
                core.say(f"   - fixed: {p}")
        core.say("")
        core.table(["run", "repos off", "problems"], [[t["when"], f"{t['off']}/{t['repos']}", str(t["problems"])]
                                                      for t in trend])
    if url and changes:
        notify(url, changes)
