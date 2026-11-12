"""The branches of one repo, and deleting them (see mason/branches.py).

    GET  /api/v1/repo/branches?repo=acme/web           {default, branches: [...], total, url}
    POST /api/v1/repo/branches/delete                  {repo, branches: [names], merged: false, dry_run}

The default branch and protected ones are refused; a branch with an open PR may go (GitHub closes the PR),
and the web app says so before it asks.
"""

from __future__ import annotations

from flask import Blueprint, abort, jsonify, request

from mason import branches as B
from mason import core
from mason.server.api.account import body
from mason.server.api.repos import is_gl, write_allowed
from mason.server.auth import audit, need
from mason.server.context import as_user, valid_repo

bp = Blueprint("branches", __name__, url_prefix="/api/v1/repo")
MAX = 100  # branches one delete takes


@bp.get("/branches")
@need("read")
def view():
    repo = valid_repo(request.args.get("repo", ""))
    with as_user() as (_gh, gl):
        if is_gl(repo) and gl is None:
            abort(409, "connect GitLab first")
        try:
            return jsonify(B.listing(repo, gl))
        except core.RateLimited as err:
            abort(429, str(err))
        except RuntimeError as err:
            abort(502, f"couldn't read the branches: {str(err).splitlines()[0][:200]}")


@bp.post("/branches/delete")
@need("write")
def delete():
    data = body()
    repo = valid_repo(str(data.get("repo", "")))
    raw = data.get("branches") or []
    if not isinstance(raw, list) or len(raw) > MAX:
        abort(400, f"send up to {MAX} branch names")
    try:
        names = [B.valid_name(n) for n in raw]
    except ValueError as err:
        abort(400, str(err))
    merged = bool(data.get("merged"))
    if not names and not merged:
        abort(400, "name the branches to delete")
    dry = write_allowed(bool(data.get("dry_run")))
    with as_user(False) as (_gh, gl):  # the list is read even in a dry run; delete() says what it would do
        if is_gl(repo) and gl is None:
            abort(409, "connect GitLab first")
        try:
            lines, ok = B.delete(repo, names, gl, merged=merged, dry=dry)
        except core.RateLimited as err:
            abort(429, str(err))
        except RuntimeError as err:
            abort(502, f"couldn't read the branches: {str(err).splitlines()[0][:200]}")
    audit("branches.delete", repo, dry, ok=ok, detail="\n".join(lines))
    return jsonify({"text": "\n".join(f"{repo}: {x}" for x in lines), "ok": ok})
