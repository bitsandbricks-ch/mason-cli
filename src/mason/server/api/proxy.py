"""The GitHub proxy for `mason` and `mason tui` signed in to the operator (OperatorTransport).

The CLI sends GitHub REST and GraphQL calls here with its API key; the operator makes them with
the key owner's own GitHub token. So the CLI needs no gh and no GitHub token, and an API key can
be revoked in one place.

Not everything is passed on:
* reads (GET, GraphQL queries) only on the parts of the API mason reads,
* writes only for the calls mason and its plugins make, and only with a write key or a session,
* never: deleting repos, changing who has access, keys, hooks, or anything about the user's account.
"""

from __future__ import annotations

import json
import re

from flask import Blueprint, Response, abort, g, request

from mason import core
from mason.server import oauth
from mason.server.auth import audit, can_write, need
from mason.transport import HttpError

bp = Blueprint("proxy", __name__, url_prefix="/api/v1/github")

R = r"/repos/[\w.-]+/[\w.-]+"
READ = [re.compile(p) for p in (
    r"/user$", r"/user/repos$", r"/user/orgs$", r"/user/memberships/orgs/[\w.-]+$", r"/rate_limit$",
    r"/orgs/[\w.-]+(/repos|/packages|/packages/container/[^/]+/versions|/members/[\w.-]+)?$",
    r"/users/[\w.-]+(/repos|/packages|/packages/container/[^/]+/versions)?$",
    R + r"(/.*)?$",
)]
WRITE = {
    "PATCH": [R + "$", R + r"/pulls/\d+$", R + r"/rulesets/\d+$", R + r"/labels/[^/]+$", R + r"/issues/\d+$",
              R + r"/actions/variables/[^/]+$", R + r"/environments/[^/]+/variables/[^/]+$",
              R + r"/code-scanning/default-setup$", R + r"/properties/values$"],
    "PUT": [R + r"/contents/.+$", R + r"/pulls/\d+/merge$", R + r"/pulls/\d+/update-branch$",
            R + r"/rulesets/\d+$", R + r"/automated-security-fixes$",
            R + r"/private-vulnerability-reporting$", R + r"/immutable-releases$", R + r"/environments/[^/]+$",
            R + r"/environments/[^/]+/secrets/[^/]+$", R + r"/topics$",
            R + r"/vulnerability-alerts$",
            R + r"/actions/permissions(/workflow|/artifact-and-log-retention|/fork-pr-contributor-approval)?$",
            R + r"/actions/secrets/[^/]+$", R + r"/pages$"],
    "POST": [R + r"/labels$", R + r"/issues$", R + r"/git/refs$", R + r"/pulls$", R + r"/rulesets$",
             R + r"/actions/runs/\d+/approve$",
             R + r"/actions/runs/\d+/pending_deployments$", R + r"/actions/runs/\d+/(rerun(-failed-jobs)?|cancel)$",
             R + r"/generate$", r"/user/repos$", r"/orgs/[\w.-]+/repos$", R + r"/releases$", R + r"/git/tags$",
             R + r"/issues/\d+/comments$", R + r"/dispatches$", R + r"/actions/workflows/[^/]+/dispatches$",
             R + r"/environments/[^/]+/deployment-branch-policies$", R + r"/environments/[^/]+/variables$",
             R + r"/actions/variables$", R + r"/pages$", R + r"/autolinks$", R + r"/branches/[^/]+/rename$"],
    "DELETE": [R + r"/git/refs/heads/.+$", R + r"/automated-security-fixes$", R + r"/private-vulnerability-reporting$",
               R + r"/immutable-releases$", R + r"/rulesets/\d+$", R + r"/vulnerability-alerts$",
               R + r"/environments/[^/]+/deployment-branch-policies/\d+$", R + r"/pages$", R + r"/autolinks/\d+$"],
}
WRITE_RE = {m: [re.compile(p) for p in ps] for m, ps in WRITE.items()}
# Secrets: names can be listed and values stored (encrypted on the CLI's side with the repo's public key),
# never deleted through here. Variables are settings like any other.
NEVER = re.compile(r"/(collaborators|invitations|keys|hooks|transfer|"
                   r"teams|members|interaction-limits)(/|$)|/user/(emails|keys|gpg_keys|ssh_signing_keys)")
MUTATIONS = {"markPullRequestReadyForReview", "enablePullRequestAutoMerge", "disablePullRequestAutoMerge",
             "mergePullRequest", "convertPullRequestToDraft"}

# GraphQL tokens. Commas and comments count as space, and a "#" or "(" inside a string is only text: a
# regex over the raw query could be fooled by `deleteRef, (input: ...)` or a comment before the "(".
TOKEN = re.compile(r'''"""(?:\\"""|(?!""").)*"""|"(?:\\.|[^"\\\n])*"'''  # block and plain strings
                   r"|\.\.\.|[A-Za-z_]\w*|-?\d[\w.+-]*|[!$&()\[\]{}:=@|]", re.S)
SPACE = re.compile(r"[\s,\ufeff]+|#[^\n\r]*")  # one run at a time: the loop in tokens() takes the next


def tokens(text: str) -> list[str] | None:
    """The document's tokens, or None when something in it isn't GraphQL."""
    out, i = [], 0
    while i < len(text):
        m = SPACE.match(text, i)
        if m:
            i = m.end()
            continue
        m = TOKEN.match(text, i)
        if not m:
            return None
        out.append(m.group())
        i = m.end()
    return out


def _skip(toks: list[str], i: int, open_: str, close: str) -> int:
    """Past the bracket at toks[i] and everything up to its partner."""
    depth = 0
    while i < len(toks):
        depth += toks[i] == open_
        depth -= toks[i] == close
        i += 1
        if depth == 0:
            return i
    raise ValueError("unbalanced")


def operations(query: str) -> list[tuple[str, list[str] | None]]:
    """Each operation of the document: its type and its top fields (None when they can't be told, such as
    a fragment spread). Raises ValueError when it isn't a GraphQL document."""
    toks = tokens(query)
    if not toks:
        raise ValueError("empty")
    ops, i = [], 0
    while i < len(toks):
        kind = "query" if toks[i] == "{" else toks[i]
        if kind not in ("query", "mutation", "subscription", "fragment"):
            raise ValueError(kind)
        if toks[i] != "{":
            i += 1
        while i < len(toks) and toks[i] != "{":  # name, variables, type condition, directives
            i = _skip(toks, i, "(", ")") if toks[i] == "(" else i + 1
        if i >= len(toks):
            raise ValueError("no selection")
        end = _skip(toks, i, "{", "}")
        fields: list[str] | None = []
        j = i + 1
        while j < end - 1:
            t = toks[j]
            if t == "...":
                fields = None
                j += 1
                continue
            if t == "(":
                j = _skip(toks, j, "(", ")")
                continue
            if t == "{":
                j = _skip(toks, j, "{", "}")
                continue
            if t == "@":  # a directive: its name is not a field
                j += 2
                continue
            if t[0].isalpha() or t[0] == "_":
                if j + 1 < end and toks[j + 1] == ":":  # an alias: the field is the name after it
                    j += 2
                    t = toks[j] if j < end else ""
                if fields is not None:
                    fields.append(t)
            j += 1
        if kind != "fragment":
            ops.append((kind, fields))
        i = end
    return ops


def transport():
    t = oauth.github(g.user)
    if t is None:
        abort(409, "connect GitHub first (Settings › Accounts in the operator)")
    return t


TEAM = re.compile(r"/orgs/[\w.-]+/teams/[\w.-]+$")  # an environment's reviewer team: its id
LISTED = re.compile(R + r"/(hooks|keys)$")  # doctor's webhooks and deploy_keys: the lists, read only


# Flask has decoded the path once: an encoded dot or slash left in it would reach GitHub as one more level
# to decode, and so could climb out of the repo the patterns checked (contents/%2e%2e/%2e%2e/user/keys).
SNEAKY = re.compile(r"\.\.|//|\\|%(2e|2f|5c)", re.I)


def allowed(method: str, path: str) -> bool:
    if SNEAKY.search(path):
        return False
    if method in ("GET", "HEAD") and (TEAM.match(path) or LISTED.match(path)):
        return True
    if NEVER.search(path):
        return False
    if method in ("GET", "HEAD"):
        return any(p.match(path) for p in READ)
    return any(p.match(path) for p in WRITE_RE.get(method, []))


@bp.route("/rest/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@need("read")
def rest(path: str):
    path = "/" + path
    if SNEAKY.search(path):
        abort(400, "bad path")
    if request.method != "GET" and not can_write():
        abort(403, "this API key is read-only")
    if not allowed(request.method, path):
        abort(403, f"the operator doesn't pass {request.method} {path} on")
    t = transport()
    query = request.query_string.decode()
    full = path + (("?" + query) if query else "")
    accept = request.headers.get("Accept") or "application/vnd.github+json"
    if accept not in ("application/vnd.github+json", "application/json", "application/octet-stream",
                      "application/vnd.github.diff"):
        accept = "application/vnd.github+json"
    data = request.get_data() if request.method in ("POST", "PUT", "PATCH", "DELETE") else None
    try:
        if request.method == "GET":  # through this user's own cache, revalidated with ETags
            status, headers, raw = t.get_raw(full, accept=accept)
        else:
            try:
                status, headers, raw = t.request(request.method, t.api_url + full, data or None, accept=accept)
            finally:  # the operator's own pages must not show what this write changed as it was
                t.forget(path)
    except HttpError as err:
        return Response(err.body or b"{}", status=err.status, content_type="application/json")
    except core.RateLimited as err:
        return Response(json.dumps({"message": str(err)}), status=429, content_type="application/json",
                        headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(err.reset or 0)})
    except RuntimeError as err:
        abort(502, str(err))
    if request.method != "GET":
        audit(f"proxy.{request.method.lower()}", path)
    low = {k.lower(): v for k, v in headers.items()}
    etag = low.get("etag")
    if request.method == "GET" and etag and etag in request.headers.get("If-None-Match", ""):
        resp = Response(status=304)
    else:
        resp = Response(raw, status=status, content_type=low.get("content-type") or "application/json")
    for h in ("X-RateLimit-Remaining", "X-RateLimit-Limit", "X-RateLimit-Reset", "ETag", "Last-Modified"):
        v = low.get(h.lower())
        if v:
            resp.headers[h] = v
    if request.method == "GET" and not low.get("x-ratelimit-remaining") and t.last_rate:
        resp.headers["X-RateLimit-Remaining"] = str(t.last_rate["remaining"])
        resp.headers["X-RateLimit-Limit"] = str(t.last_rate["limit"])
        resp.headers["X-RateLimit-Reset"] = str(t.last_rate["reset"])
    return resp


@bp.post("/graphql")
@need("read")
def graphql():
    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query") or "")
    try:
        ops = operations(query)
    except ValueError:
        abort(400, "not a GraphQL query")
    kinds = {k for k, _ in ops}
    if "subscription" in kinds:
        abort(403, "no subscriptions")
    if len(ops) != 1:  # GitHub would need an operation name, which isn't passed on: one operation only
        abort(400, "one operation per call")
    kind, fields = ops[0]
    if kind == "mutation":
        if not can_write():
            abort(403, "this API key is read-only")
        if not fields or set(fields) - MUTATIONS:  # None: a fragment spread hides what it does
            names = sorted(set(fields or []) - MUTATIONS)
            abort(403, f"the operator doesn't pass these mutations on: {', '.join(names) or '?'}")
        audit("proxy.graphql", ", ".join(sorted(set(fields))))
    variables = payload.get("variables") or {}
    if not isinstance(variables, dict):
        abort(400, "variables must be an object")
    t = transport()
    try:
        status, raw = t.graphql_raw(query, variables)
    except core.RateLimited as err:
        return Response(json.dumps({"message": str(err)}), status=429, content_type="application/json")
    except HttpError as err:
        return Response(err.body or b"{}", status=err.status, content_type="application/json")
    except RuntimeError as err:
        abort(502, str(err))
    return Response(raw, status=status, content_type="application/json")
