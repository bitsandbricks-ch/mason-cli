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
TOKEN = re.compile(r'''
    (?P<skip>[\s,\ufeff]+|\#[^\n\r]*)
  | (?P<block>"""(?:\\"""|(?!""").)*""")
  | (?P<string>"(?:\\.|[^"\\\n\r])*")
  | (?P<spread>\.\.\.)
  | (?P<name>[_A-Za-z][_0-9A-Za-z]*)
  | (?P<number>-?[0-9][0-9.eE+-]*)
  | (?P<punct>[!$&()\[\]{}:=@|])
''', re.S | re.X)


class BadQuery(ValueError):
    pass


def _tokens(query: str) -> list[str]:
    out, pos = [], 0
    while pos < len(query):
        m = TOKEN.match(query, pos)
        if not m:
            raise BadQuery(f"can't read the query at {query[pos:pos + 20]!r}")
        pos = m.end()
        if m.lastgroup == "skip":
            continue
        out.append("" if m.lastgroup in ("block", "string") else m.group())  # strings are never names
    return out


def _skip(tokens: list[str], i: int, open_: str, close: str) -> int:
    """The index after the balanced group that starts at tokens[i] == open_."""
    depth = 0
    while i < len(tokens):
        depth += (tokens[i] == open_) - (tokens[i] == close)
        i += 1
        if depth == 0:
            return i
    raise BadQuery(f"a {open_} isn't closed")


def operations(query: str) -> list[tuple[str, list[str]]]:
    """[(query|mutation|subscription, the fields it selects at the top)] of a GraphQL document, read
    like GitHub reads it: comments, commas, aliases and strings can't hide a field. A fragment spread at
    the top of a mutation counts as the field "...", which is never allowed."""
    t, i, ops = _tokens(query), 0, []
    while i < len(t):
        if t[i] == "fragment":  # fragment Name on Type @dir { ... }
            while i < len(t) and t[i] != "{":
                i += 1
            i = _skip(t, i, "{", "}")
            continue
        kind = "query"
        if t[i] in ("query", "mutation", "subscription"):
            kind = t[i]
            i += 1
            while i < len(t) and t[i] != "{":  # name, (variables = defaults), @directives(args)
                i = _skip(t, i, "(", ")") if t[i] == "(" else i + 1
        if i >= len(t) or t[i] != "{":
            raise BadQuery("not a GraphQL query")
        end = _skip(t, i, "{", "}")
        fields, j = [], i + 1
        while j < end - 1:
            if t[j] == "...":
                fields.append("...")
                j += 1
                continue
            if t[j] == "(":
                j = _skip(t, j, "(", ")")
            elif t[j] == "{":
                j = _skip(t, j, "{", "}")
            elif t[j] == "@":
                j += 2  # the directive's name; its arguments are skipped as a group
            elif t[j] == ":":
                fields[-1:] = []  # what came before was an alias
                j += 1
            else:
                fields.append(t[j])
                j += 1
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


def allowed(method: str, path: str) -> bool:
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
    if ".." in path or "//" in path:
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
    if not isinstance(payload, dict):
        abort(400, "send a JSON object: {query, variables}")
    query = str(payload.get("query") or "")
    try:
        ops = operations(query)
    except BadQuery as err:
        abort(400, str(err))
    if len(ops) != 1:  # which one GitHub runs would depend on operationName, which isn't passed on
        abort(400, "send one GraphQL operation" if ops else "not a GraphQL query")
    kind, fields = ops[0]
    if kind == "subscription":
        abort(403, "no subscriptions")
    if kind == "mutation":
        if not can_write():
            abort(403, "this API key is read-only")
        names = set(fields) - {"__typename"}
        if not names or names - MUTATIONS:
            abort(403, f"the operator doesn't pass these mutations on: {', '.join(sorted(names - MUTATIONS)) or '?'}")
        audit("proxy.graphql", ", ".join(sorted(names)))
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
