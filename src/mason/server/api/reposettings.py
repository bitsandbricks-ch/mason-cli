"""Every GitHub or GitLab setting of one repo (see mason/catalog.py): read them all, change the ones the API
writes, and keep a change in the repo's .mason.toml so doctor holds the repo to it.

    GET  /api/v1/repo/settings?repo=acme/web     every setting by area, and the lists (webhooks, members, ...)
    POST /api/v1/repo/settings                   {repo, changes: {key: value}, keep: false, mode, dry_run}

With keep, the changes doctor has a key for are also written to the repo's .mason.toml (or .mason/mason.toml),
through a pull request or straight on with auto_push, like the mason files panel.
"""

from __future__ import annotations

from flask import Blueprint, abort, jsonify, request

from mason import catalog, config, core
from mason.server.api import masonfiles as MF
from mason.server.api.account import body
from mason.server.api.repos import write_allowed
from mason.server.auth import audit, need
from mason.server.context import as_user, valid_repo

bp = Blueprint("reposettings", __name__, url_prefix="/api/v1/repo")


def provider(repo: str) -> str:
    return "gitlab" if MF.is_gl(repo) else "github"


@bp.get("/settings")
@need("read")
def view():
    repo = valid_repo(request.args.get("repo", ""))
    with as_user() as (_gh, gl):
        if MF.is_gl(repo) and gl is None:
            abort(409, "connect GitLab first")
        try:
            got = catalog.read_gitlab(gl, repo) if MF.is_gl(repo) else catalog.read_github(repo)
        except core.RateLimited as err:
            abort(429, str(err))
        except RuntimeError as err:
            abort(502, str(err))
        try:
            path, text = config.repo_file(lambda p: MF.read(gl, repo, p), repo)
            own = config.parse_defaults(text, path) if text else {}
        except RuntimeError:
            path, own = None, {}
    got["file"] = path or ""
    got["kept"] = kept_values(own)
    return jsonify(got)


def kept_values(own: dict) -> dict:
    """{dotted keep path: value} of what the repo's own .mason.toml says, for the panel's "kept" marks."""
    out: dict = {}

    def walk(prefix: str, d: dict):
        for k, v in d.items():
            path = f"{prefix}{k}"
            if isinstance(v, dict):
                walk(path + ".", v)
            else:
                out[path] = v

    walk("", {k: v for k, v in own.items() if k != "release"})
    return out


@bp.post("/settings")
@need("write")
def change():
    data = body()
    repo = valid_repo(str(data.get("repo", "")))
    if MF.is_org_repo(repo):
        abort(400, "an org's .mason repo holds defaults: change its own settings on GitHub")
    which = provider(repo)
    try:
        changes = catalog.clean(which, data.get("changes"))
    except ValueError as err:
        abort(400, str(err))
    keep = bool(data.get("keep"))
    dry = write_allowed(bool(data.get("dry_run")))
    lines: list[str] = []
    with as_user(dry) as (_gh, gl):
        if which == "gitlab" and gl is None:
            abort(409, "connect GitLab first")
        try:
            said = catalog.write_gitlab(gl, repo, changes) if which == "gitlab" else catalog.write_github(repo, changes)
        except core.RateLimited as err:
            abort(429, str(err))
        bad = catalog.failed(said)
        audit("repo.settings", repo, dry, ok=not bad,
              detail=", ".join(f"{k}={core.compact(v)}" for k, v in changes.items())
              + "".join(f"\n{x}" for x in said if x.startswith("failed: ")))
        lines += [f"{'[dry-run] ' if dry else ''}{repo}: {s}" for s in said]
        if bad and keep:
            keep = False
            lines.append("not kept in .mason.toml: GitHub refused some of it" if which == "github"
                         else "not kept in .mason.toml: GitLab refused some of it")
        values = catalog.kept(which, changes) if keep else {}
        if keep:
            path, text = config.repo_file(lambda p: MF.read(gl, repo, p), repo)
    if keep:
        skipped = [k for k in changes if not (catalog.find(which, k).keep)]
        if skipped:
            lines.append(f"not kept (doctor has no key for them): {', '.join(skipped)}")
        if values:
            if text is None:
                path = config.REPO_FOLDER_FILE if data.get("folder", True) else config.REPO_LAYER
            try:
                new = catalog.keep_text(text or "", values)
            except RuntimeError as err:
                abort(409, str(err))
            problems = MF.validate_settings(new)
            if problems:
                return jsonify({"problems": problems, "text": "\n".join(lines)}), 422
            if (text or "") == new:
                lines.append(f"{path} already says that")
            else:
                got = MF.commit(repo, {path: new}, str(data.get("mode") or "auto"), "Keep repo settings (Mason)",
                                "mason.settings", dry).get_json()
                lines.append(got.get("text", ""))
    MF.forget(repo)
    return jsonify({"text": "\n".join(lines) or "nothing changed", "ok": not bad})
