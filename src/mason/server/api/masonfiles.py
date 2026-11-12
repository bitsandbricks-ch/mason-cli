"""A repo's own mason files in the web app: see where its rules come from, edit them, and write them back.

    GET  /api/v1/mason?repo=acme/web          the rules that stack for the repo, layer by layer, and its files
    PUT  /api/v1/mason/file                   save or remove one file (.mason.toml, .mason/mason.toml,
                                              .mason/rulesets/*.json; in an org's .mason repo: mason.toml,
                                              rulesets/**.json, files/**)
    POST /api/v1/mason/protect                set (or turn off) the repo's `protect` table
    POST /api/v1/mason/save-live              the repo's live rulesets as .mason/rulesets/*.json

Writes go through a pull request (merge request), straight onto the default branch (`commit`), or `auto`:
straight on when the repo has auto_push, else a pull request. Everything is validated before it's written,
and every write is in the audit log.
"""

from __future__ import annotations

import base64
import json
import re
import secrets
import urllib.parse

from flask import Blueprint, abort, g, jsonify, request

from mason import config, core, rules
from mason import defaults as D
from mason.server import gitlab as GL
from mason.server.api.account import body
from mason.server.api.defaults import check_path
from mason.server.api.defaults import validate as validate_defaults
from mason.server.api.repos import write_allowed
from mason.server.auth import audit, need
from mason.server.context import as_user, load_config, valid_repo

bp = Blueprint("masonfiles", __name__, url_prefix="/api/v1/mason")
SETTINGS_FILES = (config.REPO_LAYER, config.REPO_FOLDER_FILE)
RULESET_FILE = re.compile(r"^\.mason/rulesets/[A-Za-z0-9_.@ -]+\.json$")
ORG_FILE = re.compile(r"^(mason\.toml|rulesets/.+\.json|files/.+)$")
# what the protect form may set, and of which kind
PROTECT_KEYS = {"reviews": int, "checks": list, "signed_commits": bool, "linear_history": bool, "code_owners": bool,
                "resolve_threads": bool, "dismiss_stale": bool, "up_to_date": bool, "last_push_approval": bool,
                "merge_queue": bool, "branches": list, "name": str}


def is_gl(repo: str) -> bool:
    return repo.startswith(GL.PREFIX)


def is_org_repo(repo: str) -> bool:
    """The org's (or GitLab group's) own defaults repo: <org>/.mason."""
    return repo.rsplit("/", 1)[-1] == config.ORG_REPO


# ── validation ───────────────────────────────────────────────────────────────


def validate(repo: str, path: str, text: str) -> list[str]:
    if is_org_repo(repo):
        if path == config.DEFAULTS_FILE:
            problems = validate_defaults(path, text)
            try:
                raw = config.parse_defaults(text)
            except RuntimeError:
                return problems
            ignored = sorted(k for k in raw if k != "group")
            if ignored:
                problems.append(f"only [[group]] tables count in an org's .mason: {', '.join(ignored)} is ignored")
            return problems
        return validate_defaults(path, text)
    if path.endswith(".json"):
        return validate_defaults(f"rulesets/{path.rsplit('/', 1)[-1]}", text)
    return validate_settings(text)


def validate_settings(text: str) -> list[str]:
    """A repo's own .mason.toml: the keys a repo may set, checked like a group's."""
    if len(text) > 200_000:
        return ["the file is bigger than 200 KB"]
    try:
        raw = config.parse_defaults(text)
    except RuntimeError as err:
        return [str(err)]
    problems = []
    unknown = sorted(set(raw) - config.REPO_KEYS - {"release", "gitlab"})
    if unknown:
        problems.append(f"a repo's own file doesn't take {', '.join(unknown)} (groups only, or unknown)")
    settings = raw.get("settings") or {}
    if not isinstance(settings, dict):
        problems.append("settings must be a table")
    elif set(settings) - set(D.REPO_SETTINGS):
        problems.append(f"settings mason doesn't check: {', '.join(sorted(set(settings) - set(D.REPO_SETTINGS)))}")
    off = set(config._list(raw.get("skip"))) - set(config.CHECKS)
    if off:
        problems.append(f"skip doesn't know {', '.join(sorted(off))}")
    try:
        more = config._more(raw)
    except RuntimeError as err:
        return problems + [str(err)]
    for key in ("auto_fix", "auto_push", "auto_merge"):
        if key in raw and not isinstance(raw[key], bool):
            problems.append(f"{key} must be true or false")
    spec = more.get("protect")
    if isinstance(spec, dict):
        problems += protect_problems(spec)
    release = raw.get("release")
    if release is not None and not isinstance(release, dict):
        problems.append("[release] must be a table")
    elif release and release.get("tag") and "{version}" not in str(release["tag"]):
        problems.append('release.tag must contain {version}, e.g. "v{version}"')
    return problems


def protect_problems(spec: dict) -> list[str]:
    problems = []
    for key, value in spec.items():
        kind = PROTECT_KEYS.get(key)
        if key == "enabled":
            kind = bool
        if kind is None:
            if key != "merge_queue":
                problems.append(f"protect doesn't know {key} (it knows {', '.join(PROTECT_KEYS)})")
            continue
        if key == "merge_queue" and isinstance(value, dict):
            continue
        if kind is int and (isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10):
            problems.append(f"protect.{key} is a number from 0 to 10")
        elif kind is bool and not isinstance(value, bool):
            problems.append(f"protect.{key} is true or false")
        elif kind is list and not (isinstance(value, str) or (isinstance(value, list)
                                                               and all(isinstance(x, str) for x in value))):
            problems.append(f"protect.{key} is a list of names")
        elif kind is str and not isinstance(value, str):
            problems.append(f"protect.{key} is a name")
    return problems


def check_target(repo: str, path: str) -> str:
    path = check_path(path)
    if is_org_repo(repo):
        if not ORG_FILE.match(path):
            abort(400, "an org's .mason repo holds mason.toml, rulesets/**.json and files/**")
    elif path not in SETTINGS_FILES and not RULESET_FILE.match(path):
        abort(400, "a repo's mason files are .mason.toml, .mason/mason.toml and .mason/rulesets/*.json")
    if is_gl(repo) and path.endswith(".json") and not is_org_repo(repo):
        abort(400, "GitLab has no rulesets: use [gitlab] protected_branches, or protect")
    return path


# ── reading ──────────────────────────────────────────────────────────────────


def tree(gl, repo: str) -> list[str]:
    if is_gl(repo):
        return sorted(gl.blobs(repo)) if gl else []
    t = core.api("GET", f"/repos/{repo}/git/trees/HEAD?recursive=1") or {}
    return sorted(e["path"] for e in t.get("tree") or [] if e.get("type") == "blob")


def read(gl, repo: str, path: str) -> str | None:
    if is_gl(repo):
        return gl.file(repo, path) if gl else None
    return core.file_on(repo, path)


def mine(repo: str, paths: list[str]) -> list[str]:
    """The repo's own mason files among `paths` (an org's .mason: its mason.toml and rulesets)."""
    if is_org_repo(repo):
        return [p for p in paths if p == config.DEFAULTS_FILE or (p.startswith("rulesets/") and p.endswith(".json"))]
    own = [p for p in paths if p in SETTINGS_FILES or RULESET_FILE.match(p)]
    return own + [p for p in paths if p.startswith(".github/rulesets/") and p.endswith(".json")]


def origin_label(cfg, group) -> str:
    if group.name == config.REPO_LAYER:
        return "the repo"
    return group.origin or (str(cfg.source) if cfg.source else "your defaults")


def layer_rows(cfg, repo: str) -> list[dict]:
    """Every layer that stacks for `repo`, least important first: what it says about protection."""
    from mason.repos import listing

    topics = (listing(cfg).get(repo) or {}).get("topics") if not is_gl(repo) else None
    try:
        layers = list(cfg.layers_of(repo, topics))
    except RuntimeError as err:
        return [{"source": "error", "error": str(err)}]
    out = []
    for grp in layers:
        try:
            names = sorted(cfg.rulesets_of(grp))
        except RuntimeError as err:
            names = [f"(couldn't read: {err})"]
        out.append({"group": grp.name, "source": origin_label(cfg, grp), "repo": grp.origin or "",
                    "protect": grp.more.get("protect"), "rulesets": names,
                    "folder": grp.rulesets or "", "skip": list(grp.skip),
                    "auto_push": grp.auto_push})
    return out


def own_layer(gl, repo: str) -> tuple[str | None, dict]:
    """(path, raw) of the repo's own settings file ({} without one)."""
    path, text = config.repo_file(lambda p: read(gl, repo, p), repo)
    if not text:
        return None, {}
    try:
        return path, config.parse_defaults(text, f"{repo}/{path}")
    except RuntimeError:
        return path, {}


def effective(rows: list[dict], own: dict) -> tuple[dict | None, bool, str]:
    """The protect table that stacks (None when off), whether it's skipped, and who set it last."""
    spec, last = {}, ""
    for row in rows:
        p = row.get("protect")
        if p:
            spec = {**spec, **p}
            last = row["source"]
    mine_ = own.get("protect")
    if mine_ is not None:
        spec = {**spec, **(mine_ if isinstance(mine_, dict) else {"enabled": bool(mine_)})}
        last = "the repo"
    skipped = "protect" in {s for row in rows for s in row.get("skip") or []} | set(config._list(own.get("skip")))
    return (spec if spec and rules.on(spec) else None), skipped, last


@bp.get("")
@need("read")
def view():
    repo = valid_repo(request.args.get("repo", ""))
    with as_user() as (_gh, gl):
        if is_gl(repo) and gl is None:
            abort(409, "connect GitLab first")
        cfg = load_config()
        try:
            paths = tree(gl, repo)
        except RuntimeError as err:
            abort(502, f"{repo}: {err}")
        files = []
        for p in mine(repo, paths):
            text = read(gl, repo, p) or ""
            files.append({"path": p, "text": text, "problems": validate(repo, p, text) if p != ".github/rulesets"
                          and not p.startswith(".github/") else [], "editable": not p.startswith(".github/")})
        out = {"repo": repo, "provider": "gitlab" if is_gl(repo) else "github", "files": files,
               "kind": "org" if is_org_repo(repo) else "repo"}
        if is_org_repo(repo):
            return jsonify(out)
        rows = layer_rows(cfg, repo)
        own_path, own = own_layer(gl, repo)
        spec, skipped, last = effective(rows, own)
        own_rs = sorted(D.ruleset_files(repo)) if not is_gl(repo) else []
        rows.append({"group": config.REPO_LAYER, "source": "the repo", "repo": repo, "file": own_path,
                     "protect": own.get("protect"), "rulesets": own_rs, "folder": ".mason/rulesets",
                     "skip": config._list(own.get("skip")), "auto_push": own.get("auto_push")})
        live, protected_by, branch = [], [], ""
        if not is_gl(repo):
            try:
                info = core.api("GET", f"/repos/{repo}") or {}
                branch = info.get("default_branch") or "main"
                found = D.live_rulesets(repo)
                live = sorted(found)
                ids = {str(rs.get("id")): name for name, rs in found.items()}
                protected_by = [re.sub(r"^ruleset (\d+)$", lambda m: f"ruleset {ids.get(m.group(1), m.group(1))}", p)
                                for p in rules.protection_of(repo, branch)]
            except core.RateLimited as err:
                abort(429, str(err))
            except RuntimeError as err:
                out["live_error"] = str(err).splitlines()[0][:200]
        auto_push = config.auto(cfg, repo, "auto_push") if not is_gl(repo) else GL.auto_of(gl, cfg, repo, "auto_push")
        out.update({"layers": rows, "settings_file": own_path, "own": {"protect": own.get("protect"),
                                                                        "skip": config._list(own.get("skip"))},
                    "protect": spec, "protect_from": last, "protect_skipped": skipped,
                    "default_branch": branch, "live_rulesets": live, "protected_by": protected_by,
                    "auto_push": auto_push, "org_repos": [w for w in config.org_candidates(repo)]})
    return jsonify(out)


# ── writing ──────────────────────────────────────────────────────────────────


def write(gl, repo: str, changes: dict[str, str | None], mode: str, message: str) -> str:
    """Write files (None removes one) in one go: a pull/merge request, or straight onto the default branch."""
    if is_gl(repo):
        info = gl.api("GET", gl.project(repo)) or {}
        base = info.get("default_branch") or "main"
        branch = base if mode == "commit" else f"mason/settings-{secrets.token_hex(3)}"
        actions = []
        for path, text in changes.items():
            exists = gl.file(repo, path, base) is not None
            if text is None and not exists:
                continue
            actions.append({"action": "delete" if text is None else ("update" if exists else "create"),
                            "file_path": path, **({} if text is None else {"content": text})})
        if not actions:
            raise RuntimeError("nothing to change")
        commit = {"branch": branch, "commit_message": message, "actions": actions}
        if mode != "commit":
            commit["start_branch"] = base
        gl.api("POST", f"{gl.project(repo)}/repository/commits", commit)
        if mode == "commit":
            return f"{info.get('web_url', '')}/-/tree/{base}"
        mr = gl.api("POST", f"{gl.project(repo)}/merge_requests", {
            "source_branch": branch, "target_branch": base, "title": message, "remove_source_branch": True,
            "description": f"Opened from Mason by {g.user.name}."}) or {}
        return mr.get("web_url", "")
    info = core.api("GET", f"/repos/{repo}") or {}
    base = info.get("default_branch") or "main"
    branch = base if mode == "commit" else f"mason/settings-{secrets.token_hex(3)}"
    if mode != "commit":
        head = core.api("GET", f"/repos/{repo}/git/ref/heads/{base}")["object"]["sha"]
        core.api("POST", f"/repos/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": head})
    for path, text in changes.items():
        got = core.get_file(repo, path, branch)
        sha = got[1] if got else None
        q = urllib.parse.quote(path)
        if text is None:
            if sha:
                core.api("DELETE", f"/repos/{repo}/contents/{q}", {"message": message, "sha": sha, "branch": branch})
            continue
        put = {"message": message, "branch": branch, "content": base64.b64encode(text.encode()).decode()}
        if sha:
            put["sha"] = sha
        core.api("PUT", f"/repos/{repo}/contents/{q}", put)
    if mode == "commit":
        return f"{core.transport().web}/{repo}/tree/{base}"
    return core.transport().pr_create(repo, base, branch, message, f"{message}\n\nOpened from Mason by {g.user.name}.")


def land_github(cfg, repo: str, changes: dict[str, str], message: str) -> tuple[str, bool]:
    """Like `mason sync`: straight onto the default branch with auto_push (a PR when that's refused), else a
    PR, auto-merged with auto_merge."""
    from mason.repos import land

    base = (core.api("GET", f"/repos/{repo}") or {}).get("default_branch") or "main"
    files = {}
    for path, text in changes.items():
        got = core.get_file(repo, path, base)
        files[path] = (text, got[1] if got else None)
    got: list = []
    text = core.capture(lambda: got.append(land(cfg, repo, base, f"mason/settings-{secrets.token_hex(3)}", files,
                                                message, message, f"{message}\n\nOpened from Mason by {g.user.name}.",
                                                said="")))
    if not got:  # capture keeps the error as text
        raise RuntimeError(text.strip().removeprefix("error: ") or "couldn't write the files")
    return got[0]


def pick_mode(gl, cfg, repo: str, mode: str) -> str:
    if mode not in ("auto", "pr", "commit"):
        abort(400, "mode is auto, pr or commit")
    if mode != "auto":
        return mode
    if is_org_repo(repo):
        return "pr"
    on = GL.auto_of(gl, cfg, repo, "auto_push") if is_gl(repo) else config.auto(cfg, repo, "auto_push")
    return "commit" if on else "pr"


def forget(repo: str) -> None:
    """Drop what mason remembers of the repo's settings, so the next check reads the new files."""
    config._repo_loaded.pop(repo, None)
    config._org_loaded.pop(repo, None)
    config._loaded.clear()


def commit(repo: str, changes: dict[str, str | None], mode: str, message: str, what: str, dry: bool = False):
    """Write `changes`; a dry run only says what it would write."""
    with as_user(False) as (_gh, gl):  # dry runs answer below, before anything is written
        if is_gl(repo) and gl is None:
            abort(409, "connect GitLab first")
        cfg = load_config()
        how = pick_mode(gl, cfg, repo, mode)
        if dry:
            where = "straight onto the default branch" if how == "commit" else "in a pull request"
            lines = [f"[dry-run] {'remove' if t is None else 'write'} {p} {where}" for p, t in changes.items()]
            lines += [f"\n--- {p}\n{t}" for p, t in changes.items() if t is not None]
            audit(what, f"{repo}: {', '.join(changes)}", True)
            return jsonify({"url": "", "mode": how, "dry": True, "text": "\n".join(lines)})
        try:
            if mode == "auto" and not is_gl(repo) and not is_org_repo(repo) and None not in changes.values():
                url, pushed = land_github(cfg, repo, changes, message)  # auto_push, a PR when that's refused
                how = "commit" if pushed else "pr"
            else:
                url = write(gl, repo, changes, how, message)
        except core.RateLimited as err:
            abort(429, str(err))
        except RuntimeError as err:
            audit(what, f"{repo}: {', '.join(changes)}", ok=False, detail=str(err))
            abort(502, str(err))
        forget(repo)
    audit(what, f"{repo}: {', '.join(changes)} ({how})", detail=url)
    verb = "pushed to the default branch" if how == "commit" else "opened"
    return jsonify({"url": url, "mode": how, "text": f"{verb}: {url}"})


@bp.post("/validate")
@need("read")
def post_validate():
    data = body()
    repo = valid_repo(str(data.get("repo", "")))
    path = check_target(repo, str(data.get("path", "")))
    return jsonify({"problems": validate(repo, path, str(data.get("text") or ""))})


@bp.put("/file")
@need("write")
def put_file():
    data = body()
    repo = valid_repo(str(data.get("repo", "")))
    path = check_target(repo, str(data.get("path", "")))
    delete = bool(data.get("delete"))
    text = str(data.get("text") or "")
    problems = [] if delete else validate(repo, path, text)
    if problems and not data.get("force"):
        return jsonify({"problems": problems}), 422
    message = str(data.get("message") or f"{'Remove' if delete else 'Update'} {path} (Mason)")[:200]
    return commit(repo, {path: None if delete else text}, str(data.get("mode") or "auto"), message, "mason.write",
                  write_allowed(bool(data.get("dry_run"))))


# ── the protect table, as text ───────────────────────────────────────────────


def toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {toml_value(x)}" for k, x in v.items()) + " }"
    return json.dumps(str(v))


HEADER = re.compile(r"^\s*\[")


def with_protect(text: str, spec) -> str:
    """`text` (a repo's .mason.toml) with its protect replaced: a [protect] table, `protect = false`, or (None)
    nothing. Comments and every other line stay as they are."""
    lines = text.splitlines()
    out, i, at = [], 0, None
    top = True  # still before the first [table]
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\s*\[\s*protect\s*\]\s*(#.*)?$", line):
            at = len(out) if at is None else at
            i += 1
            while i < len(lines) and not HEADER.match(lines[i]):
                i += 1
            continue
        if HEADER.match(line):
            top = False
        if top and re.match(r"^\s*protect\s*=", line):
            at = len(out) if at is None else at
            i += 1
            continue
        out.append(line)
        i += 1
    while out and not out[-1].strip():
        out.pop()
    if spec is None:
        return "\n".join(out) + "\n" if out else ""
    if spec is False:  # a top-level key: it must come before the first table
        first = next((n for n, x in enumerate(out) if HEADER.match(x)), len(out))
        out.insert(min(at, first) if at is not None else first, "protect = false")
        return "\n".join(out) + "\n"
    block = ["[protect]"] + [f"{k} = {toml_value(v)}" for k, v in spec.items()]
    return "\n".join(out + ([""] if out else []) + block) + "\n"


def clean_protect(raw) -> dict | bool | None:
    """The form's protect table: known keys of the right kind, empty ones left out (None: inherit)."""
    if raw is None or raw is False:
        return raw
    if not isinstance(raw, dict):
        abort(400, "protect is a table, false (off here) or null (as the groups say)")
    out = {}
    for key, kind in PROTECT_KEYS.items():
        if key not in raw or raw[key] in (None, "", []):
            continue
        v = raw[key]
        if kind is list:
            v = [x.strip() for x in (v.split(",") if isinstance(v, str) else v) if str(x).strip()]
            if not v:
                continue
        elif kind is int:
            try:
                v = int(v)
            except (TypeError, ValueError):
                abort(400, f"protect.{key} is a number")
        elif kind is bool:
            if not v:
                continue
            v = bool(v)
        else:
            v = str(v).strip()
        out[key] = v
    problems = protect_problems(out)
    if problems:
        abort(400, "; ".join(problems))
    return out


@bp.post("/protect")
@need("write")
def set_protect():
    """Set the repo's own protect: a table on top of the groups', false (off in this repo), or null (drop the
    repo's own, so the groups decide)."""
    data = body()
    repo = valid_repo(str(data.get("repo", "")))
    if is_org_repo(repo):
        abort(400, "edit the groups' protect in the org's mason.toml")
    spec = clean_protect(data.get("protect"))
    with as_user() as (_gh, gl):
        if is_gl(repo) and gl is None:
            abort(409, "connect GitLab first")
        path, text = config.repo_file(lambda p: read(gl, repo, p), repo)
    if text is None:
        path = config.REPO_FOLDER_FILE if data.get("folder", True) else config.REPO_LAYER
    new = with_protect(text or "", spec)
    problems = validate_settings(new)
    if problems:
        return jsonify({"problems": problems}), 422
    if (text or "") == new:
        return jsonify({"text": f"{path} already says that", "url": "", "mode": ""})
    what = "turn off branch protection" if spec is False else "drop the repo's own protect" if spec is None \
        else "set branch protection"
    return commit(repo, {path: new or None}, str(data.get("mode") or "auto"), f"{what[0].upper()}{what[1:]} (Mason)",
                  "mason.protect", write_allowed(bool(data.get("dry_run"))))


@bp.post("/save-live")
@need("write")
def save_live():
    """The repo's live rulesets (or the named ones) as .mason/rulesets/<name>.json, so they're kept in the repo
    and doctor holds the repo to them."""
    data = body()
    repo = valid_repo(str(data.get("repo", "")))
    if is_gl(repo) or is_org_repo(repo):
        abort(400, "only a GitHub repo has live rulesets to save")
    only = {str(x) for x in data.get("names") or []}
    with as_user():
        try:
            live = D.live_rulesets(repo)
        except RuntimeError as err:
            abort(502, str(err))
    changes = {}
    for name, rs in live.items():
        if only and name not in only:
            continue
        clean = {k: rs[k] for k in D.RULESET_FIELDS if k in rs}
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "ruleset"
        changes[f".mason/rulesets/{slug}.json"] = json.dumps(clean, indent=2) + "\n"
    if not changes:
        abort(404, f"{repo} has no rulesets" + (" of those names" if only else ""))
    return commit(repo, changes, str(data.get("mode") or "auto"), "Keep the live rulesets in .mason/rulesets (Mason)",
                  "mason.save_live", write_allowed(bool(data.get("dry_run"))))
