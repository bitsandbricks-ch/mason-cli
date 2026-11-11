"""The shorter repo keys (config.MORE) as doctor sees them.

Some become what doctor already knows how to check and fix:

    protect = { reviews = 1, checks = ["test"], signed_commits = true }  -> a ruleset named "protect"
    dependabot = { ecosystems = ["pip", "github-actions"], interval = "weekly" }  -> .github/dependabot.yml
    renovate = true                                                    -> renovate.json
    codeowners = { "*" = ["@mike"], "/docs/" = ["@acme/docs"] }        -> .github/CODEOWNERS
    release_notes = { categories = { Features = ["feature"] } }        -> .github/release.yml
    templates = true                                                   -> required issue and PR templates
    skip_until = { code_scanning = 2027-01-01 }                        -> skip, until that day

The generated files reach the repo with `mason sync` (or straight away with auto_push), like shared files.
The rest are checks of their own: CODEOWNERS errors, discussion categories, the social preview,
`archive_after` (--fix archives), custom `properties` (--fix sets them), and `webhooks` and
`deploy_keys` (checked only: mason never changes who has access).
"""

from __future__ import annotations

import datetime as dt
import json

from mason import core
from mason.core import api, git_blob_sha, graphql
from mason.extras import Finding, _get

PROTECT = "protect"
MERGE_QUEUE = {"check_response_timeout_minutes": 60, "grouping_strategy": "ALLGREEN", "max_entries_to_build": 5,
               "max_entries_to_merge": 5, "merge_method": "SQUASH", "min_entries_to_merge": 1,
               "min_entries_to_merge_wait_minutes": 5}
TEMPLATES = (".github/pull_request_template.md|.github/PULL_REQUEST_TEMPLATE.md|pull_request_template.md|"
             "docs/pull_request_template.md|.github/PULL_REQUEST_TEMPLATE",
             ".github/ISSUE_TEMPLATE/config.yml|.github/ISSUE_TEMPLATE/config.yaml|.github/ISSUE_TEMPLATE/bug_report.md|"
             ".github/ISSUE_TEMPLATE/bug_report.yml|.github/ISSUE_TEMPLATE/feature_request.md|"
             ".github/ISSUE_TEMPLATE/feature_request.yml|.github/ISSUE_TEMPLATE.md")


def on(spec) -> bool:
    """A table key is on unless it says enabled = false (`dependabot = false`)."""
    return spec is not None and spec is not False and not (isinstance(spec, dict) and spec.get("enabled") is False)


# ── what the keys add to a wanted state ─────────────────────────────────────


def prepare(want: dict) -> dict:
    """Fold the MORE keys into `want` (baseline and overlay call it before `skip`)."""
    more = want.get("more") or {}
    today = dt.date.today()
    expired = []
    for check, until in (more.get("skip_until") or {}).items():
        day = until if isinstance(until, dt.date) else dt.date.fromisoformat(str(until)[:10])
        if today <= day:
            want["skip"] = set(want.get("skip") or ()) | {check}
        else:
            expired.append(f"skip of {check} ran out on {day.isoformat()}: it's checked again")
    want["expired_skips"] = expired
    generated = set()
    if on(more.get("protect")):
        rs = protect_ruleset(more["protect"])
        want["rulesets"] = {**want.get("rulesets", {}), rs["name"]: rs}
        generated.add(rs["name"])
    want["generated_rulesets"] = generated | set(want.get("generated_rulesets") or ())
    for path, text in generated_files(more).items():
        want["files"] = {**want.get("files", {}), path: git_blob_sha(text)}
        want["texts"] = {**want.get("texts", {}), path: text}
    if more.get("templates"):
        want["required_files"] = list(dict.fromkeys(list(want.get("required_files") or []) + list(TEMPLATES)))
    return want


def protect_ruleset(spec: dict) -> dict:
    """A ruleset from the protect table."""
    rules: list[dict] = [{"type": "deletion"}, {"type": "non_fast_forward"}]
    if "reviews" in spec or spec.get("code_owners") or spec.get("resolve_threads"):
        rules.append({"type": "pull_request", "parameters": {
            "required_approving_review_count": int(spec.get("reviews") or 0),
            "dismiss_stale_reviews_on_push": bool(spec.get("dismiss_stale", False)),
            "require_code_owner_review": bool(spec.get("code_owners", False)),
            "require_last_push_approval": bool(spec.get("last_push_approval", False)),
            "required_review_thread_resolution": bool(spec.get("resolve_threads", False))}})
    if spec.get("checks"):
        rules.append({"type": "required_status_checks", "parameters": {
            "strict_required_status_checks_policy": bool(spec.get("up_to_date", False)),
            "required_status_checks": [{"context": str(c)} for c in core_list(spec["checks"])]}})
    if spec.get("signed_commits"):
        rules.append({"type": "required_signatures"})
    if spec.get("linear_history"):
        rules.append({"type": "required_linear_history"})
    if spec.get("merge_queue"):
        mq = spec["merge_queue"]
        rules.append({"type": "merge_queue", "parameters": {**MERGE_QUEUE, **(mq if isinstance(mq, dict) else {})}})
    branches = core_list(spec.get("branches")) or ["~DEFAULT_BRANCH"]
    return {"name": str(spec.get("name") or PROTECT), "target": "branch", "enforcement": "active",
            "conditions": {"ref_name": {"include": [b if b.startswith(("~", "refs/")) else f"refs/heads/{b}"
                                                    for b in branches], "exclude": []}},
            "rules": rules}


def core_list(value) -> list[str]:
    if value is None:
        return []
    return [value] if isinstance(value, str) else [str(v) for v in value]


def generated_files(more: dict) -> dict[str, str]:
    out = {}
    if on(more.get("dependabot")):
        out[".github/dependabot.yml"] = dependabot_yml(more["dependabot"])
    if on(more.get("renovate")):
        spec = more["renovate"] if isinstance(more["renovate"], dict) else {}
        body = {"$schema": "https://docs.renovatebot.com/renovate-schema.json",
                "extends": core_list(spec.get("extends")) or ["config:recommended"]}
        out["renovate.json"] = json.dumps(body, indent=2) + "\n"
    owners = {k: v for k, v in (more.get("codeowners") or {}).items() if k != "enabled"}
    if owners:
        lines = [f"{pattern} {' '.join(core_list(who))}" for pattern, who in owners.items()]
        out[".github/CODEOWNERS"] = "# Written by mason (codeowners in mason.toml)\n" + "\n".join(lines) + "\n"
    if on(more.get("release_notes")):
        out[".github/release.yml"] = release_yml(more["release_notes"])
    return out


def y(value) -> str:
    """A YAML scalar (JSON strings are YAML)."""
    return json.dumps(value)


def dependabot_yml(spec: dict) -> str:
    ecosystems = core_list(spec.get("ecosystems")) or ["github-actions"]
    interval = str(spec.get("interval") or "weekly")
    lines = ["# Written by mason (dependabot in mason.toml)", "version: 2", "updates:"]
    for eco in ecosystems:
        lines += [f"  - package-ecosystem: {y(eco)}", f"    directory: {y(str(spec.get('directory') or '/'))}",
                  "    schedule:", f"      interval: {y(interval)}"]
        if spec.get("group"):
            lines += ["    groups:", f"      {eco.replace('-', '_')}:", "        patterns:", "          - \"*\""]
    return "\n".join(lines) + "\n"


def release_yml(spec: dict) -> str:
    lines = ["# Written by mason (release_notes in mason.toml)", "changelog:"]
    exclude = core_list(spec.get("exclude"))
    if exclude:
        lines += ["  exclude:", "    labels:"] + [f"      - {y(x)}" for x in exclude]
    cats = spec.get("categories") or {"Features": ["feature", "enhancement"], "Fixes": ["bug", "fix"],
                                      "Other changes": ["*"]}
    lines.append("  categories:")
    for title, labels in cats.items():
        lines += [f"    - title: {y(title)}", "      labels:"] + [f"        - {y(x)}" for x in core_list(labels)]
    return "\n".join(lines) + "\n"


# ── checks of their own ─────────────────────────────────────────────────────


def findings(repo: str, state: dict, want: dict) -> list[Finding]:
    more = want.get("more") or {}
    off = want.get("skip") or set()
    out = [Finding(t) for t in want.get("expired_skips") or []]
    for key, check in (("codeowners", _codeowners), ("discussions", _discussions), ("social_preview", _social),
                       ("archive", _archive), ("properties", _properties), ("webhooks", _webhooks),
                       ("deploy_keys", _deploy_keys)):
        if key in off:
            continue
        try:
            out += check(repo, state, more, want["label"])
        except core.RateLimited:
            raise
        except RuntimeError as err:
            out.append(Finding(f"{key.replace('_', ' ')}: couldn't read it ({str(err).splitlines()[0][:120]})"))
    return out


def _codeowners(repo: str, state: dict, more: dict, label: str) -> list[Finding]:
    if not on(more.get("codeowners")):
        return []
    got = _get(f"/repos/{repo}/codeowners/errors")
    if got is None:
        return [Finding("CODEOWNERS is missing")] if not more["codeowners"].keys() - {"enabled"} else []
    return [Finding(f"CODEOWNERS line {e.get('line')}: {e.get('message', e.get('kind', '?')).splitlines()[0]}")
            for e in got.get("errors") or []]


def _discussions(repo: str, state: dict, more: dict, label: str) -> list[Finding]:
    wanted = more.get("discussions") or []
    if not wanted:
        return []
    owner, name = repo.split("/", 1)
    data = graphql("query($o: String!, $n: String!) { repository(owner: $o, name: $n) { hasDiscussionsEnabled "
                   "discussionCategories(first: 50) { nodes { name } } } }", o=owner, n=name)
    r = data.get("repository") or {}
    if not r.get("hasDiscussionsEnabled"):
        return [Finding("discussions are off (set has_discussions = true in settings)")]
    have = {n["name"].lower() for n in (r.get("discussionCategories") or {}).get("nodes") or []}
    missing = [c for c in wanted if c.lower() not in have]
    return [Finding(f"discussion categories missing: {', '.join(missing)} (GitHub only adds them on the web: "
                    f"{core.WEB}/{repo}/discussions/categories)")] if missing else []


def _social(repo: str, state: dict, more: dict, label: str) -> list[Finding]:
    if not more.get("social_preview"):
        return []
    owner, name = repo.split("/", 1)
    data = graphql("query($o: String!, $n: String!) { repository(owner: $o, name: $n) { usesCustomOpenGraphImage } }",
                   o=owner, n=name)
    if (data.get("repository") or {}).get("usesCustomOpenGraphImage"):
        return []
    return [Finding(f"no social preview image (upload one on the web: {core.WEB}/{repo}/settings)")]


def _archive(repo: str, state: dict, more: dict, label: str) -> list[Finding]:
    months = more.get("archive_after")
    if not months:
        return []
    pushed = (api("GET", f"/repos/{repo}") or {}).get("pushed_at")
    if not pushed:
        return []
    when = dt.datetime.fromisoformat(pushed.replace("Z", "+00:00"))
    idle = (dt.datetime.now(dt.timezone.utc) - when).days // 30
    if idle >= int(months):
        return [Finding(f"no push for {idle} months ({label} archives after {months}): archive it", "archive")]
    return []


def fix_archive(repo: str, state: dict, want: dict) -> None:
    api("PATCH", f"/repos/{repo}", {"archived": True})
    core.say("   archived it (unarchive in the repo's settings)")


def _properties(repo: str, state: dict, more: dict, label: str) -> list[Finding]:
    wanted = {k: v for k, v in (more.get("properties") or {}).items() if k != "enabled"}
    if not wanted:
        return []
    have = {p["property_name"]: p.get("value") for p in _get(f"/repos/{repo}/properties/values") or []}
    return [Finding(f"property {k} is {have.get(k) or '(unset)'}, {label} has {v}", "properties")
            for k, v in wanted.items() if str(have.get(k)) != str(v) and have.get(k) != v]


def fix_properties(repo: str, state: dict, want: dict) -> None:
    wanted = {k: v for k, v in (want["more"].get("properties") or {}).items() if k != "enabled"}
    api("PATCH", f"/repos/{repo}/properties/values",
        {"properties": [{"property_name": k, "value": v} for k, v in wanted.items()]})
    core.say(f"   set properties {', '.join(wanted)}")


def _webhooks(repo: str, state: dict, more: dict, label: str) -> list[Finding]:
    wanted = more.get("webhooks") or []
    if not wanted:
        return []
    have = {(h.get("config") or {}).get("url", "").rstrip("/") for h in _get(f"/repos/{repo}/hooks") or []}
    return [Finding(f"webhook {u} is missing (add it in the repo's settings)") for u in wanted
            if u.rstrip("/") not in have]


def _deploy_keys(repo: str, state: dict, more: dict, label: str) -> list[Finding]:
    wanted = more.get("deploy_keys") or []
    if not wanted:
        return []
    have = {k.get("title", "") for k in _get(f"/repos/{repo}/keys") or []}
    return [Finding(f"deploy key {t} is missing (add it in the repo's settings)") for t in wanted if t not in have]


FIXERS = {"archive": fix_archive, "properties": fix_properties}


def about(more: dict) -> str:
    """owner, team and notes, for headers: 'owner mike, team ops'."""
    bits = [f"{k} {more[k]}" for k in ("owner", "team") if more.get(k)]
    return ", ".join(bits)
