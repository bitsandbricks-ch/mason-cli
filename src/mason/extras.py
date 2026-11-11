"""What doctor checks beyond settings and rulesets: environments, Actions variables and secrets,
GitHub Pages and its domain, the homepage, CodeQL default setup, autolinks, Actions retention and fork
PR approval, and the default branch's name.

Each check reads GitHub only when the group (or the repo's .mason.toml) asks for that key. A finding
names an area; `doctor --fix` runs that area's fixer once. Secrets have no fixer: mason knows their
names, never their values, so a missing one is set with `mason secrets set` or in the web app.

    environments.production = { reviewers = ["mike", "team:acme/ops"], wait = 5, branches = ["main"],
                                prevent_self_review = true, secrets = ["DEPLOY_TOKEN"],
                                variables = { REGION = "eu" } }
    variables = { NODE_VERSION = "22" }        # Actions variables (values are not secret)
    secrets = ["NPM_TOKEN"]                    # Actions secrets that must exist
    pages = { build = "workflow", cname = "docs.acme.ch", https = true }   # or true / false
    homepage = true                            # the Pages address, or a URL
    code_scanning = true                       # CodeQL default setup
    autolinks = { "HUB-" = "https://tracker.acme.ch/HUB-<num>" }
    actions = { retention_days = 30, fork_pr_approval = "first_time_contributors" }
    branch = "main"                            # --fix renames the default branch
"""

from __future__ import annotations

import base64
import re
import urllib.parse
from dataclasses import dataclass

from mason import core
from mason.core import api, compact, say

SECRET_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
FORK_POLICIES = ("first_time_contributors_new_to_github", "first_time_contributors", "all_external_contributors")


@dataclass
class Finding:
    text: str
    area: str = ""  # "" when --fix can't do it (a secret's value, a branch name that's taken)


def q(name: str) -> str:
    return urllib.parse.quote(name, safe="")


def _get(path: str):
    """A GET that answers None on a 404 (the thing isn't there, or the token may not see it)."""
    try:
        return api("GET", path)
    except core.RateLimited:
        raise
    except RuntimeError as err:
        if "404" in str(err) or "Not Found" in str(err):
            return None
        raise


def findings(repo: str, state: dict, want: dict) -> list[Finding]:
    """Everything this module checks that differs from what the group wants."""
    out: list[Finding] = []
    label = want["label"]
    for check in (_environments, _variables, _secrets, _pages, _code_scanning, _autolinks, _actions, _branch):
        try:
            out += check(repo, state, want, label)
        except core.RateLimited:
            raise
        except RuntimeError as err:
            out.append(Finding(f"{check.__name__.strip('_').replace('_', ' ')}: couldn't read it ({short_err(err)})"))
    from mason import rules

    return out + rules.findings(repo, state, want)


def short_err(err: Exception) -> str:
    return str(err).splitlines()[0][:120]


def fix(repo: str, state: dict, want: dict, found: list[Finding]) -> list[str]:
    """Run the fixer of every area with a fixable finding; returns what it said it set."""
    from mason import rules

    done = []
    for area in dict.fromkeys(f.area for f in found if f.area):
        try:
            {**FIXERS, **rules.FIXERS}[area](repo, state, want)
            done.append(area)
        except core.RateLimited:
            raise
        except RuntimeError as err:
            say(f"   couldn't set {area}: {short_err(err)}")
    return done


# ── environments ─────────────────────────────────────────────────────────────


def reviewer_key(r: dict) -> str:
    """A live reviewer as the config names it: a login, or team:slug."""
    who = r.get("reviewer") or {}
    return f"team:{who.get('slug', '')}".lower() if r.get("type") == "Team" else str(who.get("login", "")).lower()


def wanted_reviewer(name: str) -> str:
    """mike -> mike; team:acme/ops and team:ops -> team:ops."""
    name = name.strip().lower()
    return "team:" + name.split(":", 1)[1].rsplit("/", 1)[-1] if name.startswith("team:") else name


def live_environments(repo: str) -> dict[str, dict]:
    got = _get(f"/repos/{repo}/environments?per_page=100") or {}
    return {e["name"]: e for e in got.get("environments") or []}


def env_rules(env: dict) -> dict:
    """{wait, reviewers (set), prevent_self_review, branches ("protected", a set of patterns, or "all")}."""
    out: dict = {"wait": 0, "reviewers": set(), "prevent_self_review": False}
    for rule in env.get("protection_rules") or []:
        if rule.get("type") == "wait_timer":
            out["wait"] = rule.get("wait_timer") or 0
        if rule.get("type") == "required_reviewers":
            out["reviewers"] = {reviewer_key(r) for r in rule.get("reviewers") or []}
            out["prevent_self_review"] = bool(rule.get("prevent_self_review"))
    policy = env.get("deployment_branch_policy")
    out["branches"] = "all" if not policy else "protected" if policy.get("protected_branches") else "custom"
    return out


def branch_policies(repo: str, env: str) -> dict[str, dict]:
    got = _get(f"/repos/{repo}/environments/{q(env)}/deployment-branch-policies?per_page=100") or {}
    return {p["name"]: p for p in got.get("branch_policies") or []}


def wanted_branches(spec: dict):
    """None (not checked), "all", "protected", or a set of patterns (tag:v* for tags)."""
    b = spec.get("branches")
    if b is None:
        return None
    if isinstance(b, str):
        return b if b in ("all", "protected") else {b}
    return set(b) if b else "all"


def _environments(repo: str, state: dict, want: dict, label: str) -> list[Finding]:
    envs = want.get("environments") or {}
    if not envs:
        return []
    live = live_environments(repo)
    out = []
    for name, spec in envs.items():
        if name not in live:
            out.append(Finding(f"environment {name} is missing", "environments"))
            out += [Finding(f"environment {name}: secret {s} is missing (mason secrets set {s} {repo} --env {name})")
                    for s in spec.get("secrets") or []]
            continue
        have = env_rules(live[name])
        if "wait" in spec and have["wait"] != int(spec["wait"] or 0):
            out.append(Finding(f"environment {name}: wait is {have['wait']} min, {label} has {spec['wait']}",
                               "environments"))
        if "reviewers" in spec:
            wanted = {wanted_reviewer(r) for r in spec.get("reviewers") or []}
            if have["reviewers"] != wanted:
                out.append(Finding(f"environment {name}: reviewers are {', '.join(sorted(have['reviewers'])) or 'none'}"
                                   f", {label} has {', '.join(sorted(wanted)) or 'none'}", "environments"))
        if "prevent_self_review" in spec and have["prevent_self_review"] != bool(spec["prevent_self_review"]):
            out.append(Finding(f"environment {name}: prevent_self_review is {compact(have['prevent_self_review'])}, "
                               f"{label} has {compact(bool(spec['prevent_self_review']))}", "environments"))
        branches = wanted_branches(spec)
        if branches is not None:
            if isinstance(branches, set):
                got = set(branch_policies(repo, name)) if have["branches"] == "custom" else set()
                if have["branches"] != "custom" or got != branches:
                    shown = ", ".join(sorted(got)) if have["branches"] == "custom" else f"{have['branches']} branches"
                    out.append(Finding(f"environment {name}: deploys from {shown or 'no branch'}, "
                                       f"{label} has {', '.join(sorted(branches))}", "environments"))
            elif have["branches"] != branches:
                out.append(Finding(f"environment {name}: deploys from {have['branches']} branches, "
                                   f"{label} has {branches}", "environments"))
        if spec.get("variables"):
            got = {v["name"]: v.get("value") for v in (_get(
                f"/repos/{repo}/environments/{q(name)}/variables?per_page=30") or {}).get("variables") or []}
            for var, value in spec["variables"].items():
                if var.upper() not in got:
                    out.append(Finding(f"environment {name}: variable {var} is missing", "environments"))
                elif str(got[var.upper()]) != str(value):
                    out.append(Finding(f"environment {name}: variable {var} is {compact(got[var.upper()])}, "
                                       f"{label} has {compact(str(value))}", "environments"))
        if spec.get("secrets"):
            got = secret_names(repo, name)
            out += [Finding(f"environment {name}: secret {s} is missing (mason secrets set {s} {repo} --env {name})")
                    for s in spec["secrets"] if s.upper() not in got]
    return out


def reviewer_ids(repo: str, names: list[str]) -> list[dict]:
    out = []
    owner = repo.split("/")[0]
    for name in names:
        if name.lower().startswith("team:"):
            org_slug = name.split(":", 1)[1]
            org, _, slug = org_slug.rpartition("/")
            team = api("GET", f"/orgs/{org or owner}/teams/{slug}") or {}
            out.append({"type": "Team", "id": team.get("id")})
        else:
            out.append({"type": "User", "id": (api("GET", f"/users/{name}") or {}).get("id")})
    return out


def fix_environments(repo: str, state: dict, want: dict) -> None:
    for name, spec in (want.get("environments") or {}).items():
        body: dict = {}
        if "wait" in spec:
            body["wait_timer"] = int(spec["wait"] or 0)
        if "prevent_self_review" in spec:
            body["prevent_self_review"] = bool(spec["prevent_self_review"])
        if "reviewers" in spec:
            body["reviewers"] = reviewer_ids(repo, list(spec.get("reviewers") or []))
        branches = wanted_branches(spec)
        if branches == "all":
            body["deployment_branch_policy"] = None
        elif branches == "protected":
            body["deployment_branch_policy"] = {"protected_branches": True, "custom_branch_policies": False}
        elif branches:
            body["deployment_branch_policy"] = {"protected_branches": False, "custom_branch_policies": True}
        api("PUT", f"/repos/{repo}/environments/{q(name)}", body)
        if isinstance(branches, set):
            have = branch_policies(repo, name)
            for pattern in sorted(branches - set(have)):
                kind, _, pat = pattern.partition(":") if pattern.startswith("tag:") else ("branch", "", pattern)
                api("POST", f"/repos/{repo}/environments/{q(name)}/deployment-branch-policies",
                    {"name": pat, "type": kind})
            for pattern in sorted(set(have) - branches):
                api("DELETE", f"/repos/{repo}/environments/{q(name)}/deployment-branch-policies/{have[pattern]['id']}")
        if spec.get("variables"):
            set_variables(f"/repos/{repo}/environments/{q(name)}/variables", spec["variables"])
    say(f"   set environments {', '.join(want['environments'])}")


# ── variables and secrets ────────────────────────────────────────────────────


def _variables(repo: str, state: dict, want: dict, label: str) -> list[Finding]:
    if not want.get("variables"):
        return []
    got = {v["name"]: v.get("value") for v in (_get(f"/repos/{repo}/actions/variables?per_page=30") or {})
           .get("variables") or []}
    out = []
    for var, value in want["variables"].items():
        if var.upper() not in got:
            out.append(Finding(f"variable {var} is missing", "variables"))
        elif str(got[var.upper()]) != str(value):
            out.append(Finding(f"variable {var} is {compact(got[var.upper()])}, {label} has {compact(str(value))}",
                               "variables"))
    return out


def set_variables(base: str, wanted: dict) -> None:
    got = {v["name"]: v.get("value") for v in (_get(f"{base}?per_page=30") or {}).get("variables") or []}
    for var, value in wanted.items():
        if var.upper() not in got:
            api("POST", base, {"name": var, "value": str(value)})
        elif str(got[var.upper()]) != str(value):
            api("PATCH", f"{base}/{q(var)}", {"name": var, "value": str(value)})


def fix_variables(repo: str, state: dict, want: dict) -> None:
    set_variables(f"/repos/{repo}/actions/variables", want["variables"])
    say(f"   set variables {', '.join(want['variables'])}")


def secrets_path(repo: str, env: str | None = None) -> str:
    return f"/repos/{repo}/environments/{q(env)}/secrets" if env else f"/repos/{repo}/actions/secrets"


def secret_names(repo: str, env: str | None = None) -> set[str]:
    """The names of the secrets that are set (GitHub never gives values out)."""
    return {s["name"].upper() for s in (_get(f"{secrets_path(repo, env)}?per_page=100") or {}).get("secrets") or []}


def _secrets(repo: str, state: dict, want: dict, label: str) -> list[Finding]:
    if not want.get("secrets"):
        return []
    got = secret_names(repo)
    return [Finding(f"secret {s} is missing (mason secrets set {s} {repo})") for s in want["secrets"]
            if s.upper() not in got]


def wanted_secrets(want: dict | None) -> list[tuple[str | None, str]]:
    """(environment or None, name) of every secret the group wants."""
    if not want:
        return []
    out: list[tuple[str | None, str]] = [(None, s) for s in want.get("secrets") or []]
    for env, spec in (want.get("environments") or {}).items():
        out += [(env, s) for s in spec.get("secrets") or []]
    return out


def secret_status(repo: str, want: dict | None) -> list[dict]:
    """[{env, name, set}] for the secrets the group wants, plus the ones set that it doesn't name."""
    wanted = wanted_secrets(want)
    envs = list(dict.fromkeys([None] + [e for e, _ in wanted if e]))
    out = []
    for env in envs:
        got = secret_names(repo, env)
        names = [n for e, n in wanted if e == env]
        out += [{"env": env, "name": n, "set": n.upper() in got, "wanted": True} for n in names]
        out += [{"env": env, "name": n, "set": True, "wanted": False} for n in sorted(got)
                if n not in {x.upper() for x in names}]
    return out


def set_secret(repo: str, name: str, value: str, env: str | None = None) -> None:
    """Encrypt `value` with the repo's (or environment's) public key and store it. Mason keeps nothing."""
    from mason.sealedbox import seal

    if not SECRET_NAME.match(name) or name.upper().startswith("GITHUB_"):
        raise RuntimeError(f"Not a secret name GitHub takes: {name} (letters, digits, _; not GITHUB_...)")
    if not value:
        raise RuntimeError("GitHub doesn't store an empty secret")
    if len(value.encode()) > 48 * 1024:
        raise RuntimeError("A secret holds at most 48 KB")
    base = secrets_path(repo, env)
    if core.dry_run():
        say(f"   [dry-run] PUT {base}/{name}")
        return
    key = api("GET", f"{base}/public-key") or {}
    box = seal(value.encode(), base64.b64decode(key["key"]))
    api("PUT", f"{base}/{name}", {"encrypted_value": base64.b64encode(box).decode(), "key_id": key["key_id"]})


# ── Pages and the homepage ───────────────────────────────────────────────────


def pages_spec(want: dict) -> dict | None:
    """None: not checked; {} for off; {"on": True, build, branch, path, cname, https} for on."""
    p = want.get("pages")
    if p is None:
        return None
    if p is False:
        return {}
    spec = dict(p) if isinstance(p, dict) else {}
    if spec.get("enabled") is False:
        return {}
    spec["on"] = True
    return spec


def _pages(repo: str, state: dict, want: dict, label: str) -> list[Finding]:
    spec = pages_spec(want)
    home = want.get("homepage")
    if spec is None and home is None:
        return []
    have = _get(f"/repos/{repo}/pages")
    state["pages"] = have
    out = []
    if spec is not None:
        if not spec:
            if have:
                out.append(Finding(f"Pages is on, {label} has it off", "pages"))
        elif not have:
            out.append(Finding(f"Pages is off, {label} has it on", "pages"))
        else:
            out += pages_drift(have, spec, label)
    if home is not None:
        url = (have or {}).get("html_url", "") if home is True else str(home or "")
        if home is True and not url:
            out.append(Finding("homepage: Pages is off, so there's no address to use"))
        elif (state["info"].get("homepage") or "").rstrip("/") != url.rstrip("/"):
            out.append(Finding(f"homepage is {state['info'].get('homepage') or 'empty'}, {label} has {url or 'empty'}",
                               "homepage"))
    return out


def pages_drift(have: dict, spec: dict, label: str) -> list[Finding]:
    out = []
    if spec.get("build") and have.get("build_type") and have["build_type"] != spec["build"]:
        out.append(Finding(f"Pages builds with {have['build_type']}, {label} has {spec['build']}", "pages"))
    src = have.get("source") or {}
    for key in ("branch", "path"):
        if spec.get(key) and src.get(key) != spec[key]:
            out.append(Finding(f"Pages {key} is {src.get(key) or 'unset'}, {label} has {spec[key]}", "pages"))
    if "cname" in spec and (have.get("cname") or "") != (spec["cname"] or ""):
        out.append(Finding(f"Pages domain is {have.get('cname') or 'none'}, {label} has {spec['cname'] or 'none'}",
                           "pages"))
    if "https" in spec and bool(have.get("https_enforced")) != bool(spec["https"]):
        out.append(Finding(f"Pages HTTPS is {'on' if have.get('https_enforced') else 'off'}, "
                           f"{label} has {'on' if spec['https'] else 'off'}", "pages"))
    return out


def fix_pages(repo: str, state: dict, want: dict) -> None:
    spec = pages_spec(want)
    have = state.get("pages")
    if spec is None:
        return
    if not spec:
        api("DELETE", f"/repos/{repo}/pages")
        say("   turned Pages off")
        return
    build = spec.get("build") or (have or {}).get("build_type") or "workflow"
    source = {"branch": spec.get("branch") or ((have or {}).get("source") or {}).get("branch")
              or state.get("default_branch") or "main",
              "path": spec.get("path") or ((have or {}).get("source") or {}).get("path") or "/"}
    if not have:
        api("POST", f"/repos/{repo}/pages", {"build_type": build, **({"source": source} if build == "legacy" else {})})
        say("   turned Pages on")
    body: dict = {"build_type": build}
    if build == "legacy":
        body["source"] = source
    if "cname" in spec:
        body["cname"] = spec["cname"] or None
    if len(body) > 1 or (have and have.get("build_type") != build):
        api("PUT", f"/repos/{repo}/pages", body)
    if "https" in spec:
        try:
            api("PUT", f"/repos/{repo}/pages", {"https_enforced": bool(spec["https"])})
        except RuntimeError as err:  # the certificate isn't issued yet (a new domain takes a while)
            say(f"   Pages HTTPS: not yet ({short_err(err)}); run doctor --fix again once the certificate is there")
    say("   set Pages" + (f" ({spec['cname']})" if spec.get("cname") else ""))


def fix_homepage(repo: str, state: dict, want: dict) -> None:
    home = want.get("homepage")
    url = (state.get("pages") or {}).get("html_url", "") if home is True else str(home or "")
    api("PATCH", f"/repos/{repo}", {"homepage": url})
    say(f"   set homepage {url or '(empty)'}")


# ── code scanning, autolinks, Actions, the default branch ───────────────────


def _code_scanning(repo: str, state: dict, want: dict, label: str) -> list[Finding]:
    on = want.get("code_scanning")
    if on is None:
        return []
    have = (_get(f"/repos/{repo}/code-scanning/default-setup") or {}).get("state")
    if (have == "configured") != bool(on):
        return [Finding(f"CodeQL default setup is {have or 'off'}, {label} has it {'on' if on else 'off'}",
                        "code_scanning")]
    return []


def fix_code_scanning(repo: str, state: dict, want: dict) -> None:
    on = bool(want["code_scanning"])
    api("PATCH", f"/repos/{repo}/code-scanning/default-setup", {"state": "configured" if on else "not-configured"})
    say(f"   CodeQL default setup {'on' if on else 'off'}")


def autolink_spec(value) -> dict:
    """"https://x/<num>" or {url = "...", alphanumeric = false}."""
    if isinstance(value, dict):
        return {"url": str(value.get("url", "")), "alphanumeric": bool(value.get("alphanumeric", True))}
    return {"url": str(value), "alphanumeric": True}


def _autolinks(repo: str, state: dict, want: dict, label: str) -> list[Finding]:
    links = want.get("autolinks") or {}
    if not links:
        return []
    have = {a["key_prefix"]: a for a in _get(f"/repos/{repo}/autolinks") or []}
    state["autolinks"] = have
    out = []
    for prefix, value in links.items():
        spec = autolink_spec(value)
        got = have.get(prefix)
        if not got:
            out.append(Finding(f"autolink {prefix} is missing", "autolinks"))
        elif got.get("url_template") != spec["url"] or bool(got.get("is_alphanumeric", True)) != spec["alphanumeric"]:
            out.append(Finding(f"autolink {prefix} goes to {got.get('url_template')}, {label} has {spec['url']}",
                               "autolinks"))
    return out


def fix_autolinks(repo: str, state: dict, want: dict) -> None:
    have = state.get("autolinks") or {}
    for prefix, value in want["autolinks"].items():
        spec = autolink_spec(value)
        got = have.get(prefix)
        if got and got.get("url_template") == spec["url"] and bool(got.get("is_alphanumeric", True)) == \
                spec["alphanumeric"]:
            continue
        if got:  # GitHub can't change one: replace it
            api("DELETE", f"/repos/{repo}/autolinks/{got['id']}")
        api("POST", f"/repos/{repo}/autolinks",
            {"key_prefix": prefix, "url_template": spec["url"], "is_alphanumeric": spec["alphanumeric"]})
    say(f"   set autolinks {', '.join(want['autolinks'])}")


def _actions(repo: str, state: dict, want: dict, label: str) -> list[Finding]:
    acts = want.get("actions") or {}
    out = []
    if "retention_days" in acts:
        have = (_get(f"/repos/{repo}/actions/permissions/artifact-and-log-retention") or {}).get("days")
        if have != int(acts["retention_days"]):
            out.append(Finding(f"actions retention_days is {compact(have)}, {label} has {acts['retention_days']}",
                               "actions_more"))
    if "fork_pr_approval" in acts:
        if acts["fork_pr_approval"] not in FORK_POLICIES:
            return out + [Finding(f"actions fork_pr_approval must be one of {', '.join(FORK_POLICIES)}")]
        have = (_get(f"/repos/{repo}/actions/permissions/fork-pr-contributor-approval") or {}).get("approval_policy")
        if have != acts["fork_pr_approval"]:
            out.append(Finding(f"actions fork_pr_approval is {compact(have)}, {label} has {acts['fork_pr_approval']}",
                               "actions_more"))
    return out


def fix_actions_more(repo: str, state: dict, want: dict) -> None:
    acts = want["actions"]
    if "retention_days" in acts:
        api("PUT", f"/repos/{repo}/actions/permissions/artifact-and-log-retention",
            {"days": int(acts["retention_days"])})
    if acts.get("fork_pr_approval") in FORK_POLICIES:
        api("PUT", f"/repos/{repo}/actions/permissions/fork-pr-contributor-approval",
            {"approval_policy": acts["fork_pr_approval"]})
    say("   set Actions retention and fork PR approval")


def _branch(repo: str, state: dict, want: dict, label: str) -> list[Finding]:
    name = want.get("branch")
    if not name or state["default_branch"] == name:
        return []
    text = f"default branch is {state['default_branch']}, {label} has {name}"
    if _get(f"/repos/{repo}/branches/{q(name)}"):
        return [Finding(f"{text} (a branch {name} exists already: rename by hand)")]
    return [Finding(text, "branch")]


def fix_branch(repo: str, state: dict, want: dict) -> None:
    api("POST", f"/repos/{repo}/branches/{q(state['default_branch'])}/rename", {"new_name": want["branch"]})
    say(f"   renamed {state['default_branch']} to {want['branch']} (open PRs follow; clones need git branch -m)")


FIXERS = {"environments": fix_environments, "variables": fix_variables, "pages": fix_pages,
          "homepage": fix_homepage, "code_scanning": fix_code_scanning, "autolinks": fix_autolinks,
          "actions_more": fix_actions_more, "branch": fix_branch}


# ── mason secrets ────────────────────────────────────────────────────────────


def repo_want(cfg, repo: str) -> dict | None:
    """The secrets one repo should have (its stacked group plus its .mason.toml): names only, so no
    baseline with the reference repo's live state is needed."""
    from mason.config import merged, repo_layer
    from mason.repos import group_of

    group = group_of(cfg, repo)
    own = repo_layer(repo) if not repo.startswith("gitlab:") else None
    if not group and not own:
        return None
    want = {"secrets": list(group.secrets) if group else [], "environments": dict(group.environments) if group else {}}
    if own:
        want = {"secrets": merged("secrets", want["secrets"], own.secrets),
                "environments": merged("environments", want["environments"], own.environments)}
    return want


def secrets_list(cfg, repos: list[str]) -> None:
    """Every secret the defaults name for these repos, set or missing, and the ones set besides."""
    def one(repo: str, _ctx) -> None:
        rows = secret_status(repo, repo_want(cfg, repo))
        if not rows:
            say("   no secrets wanted or set")
        for r in rows:
            where = f"{r['env']}: " if r["env"] else ""
            state = "set" if r["set"] else "MISSING"
            extra = "" if r["wanted"] else "  (not in the defaults)"
            say(f"   {where}{r['name']:<28} {state}{extra}")
    core.for_each(repos, one, None)


def secrets_set(repos: list[str], name: str, value: str, env: str | None = None) -> None:
    for repo in repos:
        set_secret(repo, name, value, env)
        say(f"{repo}: set {name}" + (f" (environment {env})" if env else ""))
