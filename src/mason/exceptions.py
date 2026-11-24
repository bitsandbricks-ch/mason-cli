"""`mason exceptions`: every check a repo skips for a while (`skip_until`), with why and for how long.

    skip_until = { code_scanning = 2027-01-01 }
    skip_until = { code_scanning = { until = 2027-01-01, reason = "CodeQL can't build the C part yet" } }

In a group, an org's .mason or the repo's own .mason.toml. Until the date doctor leaves the check out; after it,
the check counts again and doctor says the exception ran out. This lists them all, soonest first, so nothing
expires by surprise and nothing stays skipped for good: `--soon DAYS` (default 30) marks the ones ending soon.
"""

from __future__ import annotations

import datetime as dt

from mason import config, core


def entries(cfg, repos: list[str], today: dt.date | None = None) -> list[dict]:
    today = today or dt.date.today()

    def one(repo: str) -> list[dict]:
        try:
            more = config.more_of(cfg, repo)
        except RuntimeError as err:
            return [{"repo": repo, "check": "", "until": "", "reason": "", "days": None, "error": str(err)}]
        out = []
        for check, value in (more.get("skip_until") or {}).items():
            until = value.get("until") if isinstance(value, dict) else value
            reason = str(value.get("reason") or "") if isinstance(value, dict) else ""
            try:
                day = until if isinstance(until, dt.date) else dt.date.fromisoformat(str(until)[:10])
            except ValueError:
                out.append({"repo": repo, "check": check, "until": str(until), "reason": reason, "days": None,
                            "error": "not a date"})
                continue
            out.append({"repo": repo, "check": check, "until": day.isoformat(), "reason": reason,
                        "days": (day - today).days, "error": ""})
        return out

    found = [e for chunk in core.pmap(one, repos) for e in chunk]
    return sorted(found, key=lambda e: (e["days"] is None, e["days"] if e["days"] is not None else 0, e["repo"]))


def state(e: dict, soon: int) -> str:
    if e["error"]:
        return f"error: {e['error']}"
    if e["days"] < 0:
        return "ran out: checked again"
    if e["days"] <= soon:
        return f"ends in {e['days']}d"
    return f"{e['days']}d left"


def show(cfg, repos: list[str], soon: int = 30) -> None:
    found = [e for e in entries(cfg, repos) if e["check"] or e["error"]]
    for e in found:
        e["state"] = state(e, soon)
    core.emit(found)
    if not found:
        core.say("no exceptions: no repo skips a check for a while (skip_until)")
        return
    core.table(["repo", "check", "until", "state", "reason"],
               [[e["repo"], e["check"], e["until"], e["state"], e["reason"] or "-"] for e in found])
    ending = sum(1 for e in found if not e["error"] and 0 <= e["days"] <= soon)
    gone = sum(1 for e in found if not e["error"] and e["days"] < 0)
    core.say(f"\n{len(found)} exception(s): {ending} ending within {soon} days, {gone} ran out (remove them)")
