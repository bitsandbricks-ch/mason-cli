"""The web console: type `mason status`, `mason doctor --fix web` ... and see what the CLI would print.

The command runs in the operator with your GitHub token and your settings; commands that only make
sense on your own machine (init, tui, open, config files) are refused, and so are plugin commands
that don't say they are safe for the web (a plugin lists those in `web_commands`).
"""

from __future__ import annotations

import contextvars
import shlex

from flask import Blueprint, abort, jsonify

from mason import cli, config, core, plugins
from mason.server.api.account import body
from mason.server.auth import audit, can_write, need
from mason.server.context import as_user, user_settings

bp = Blueprint("console", __name__, url_prefix="/api/v1")

READS = {"status", "prs", "pr", "runs", "releases", "packages", "security", "repos", "plugins", "stats", "workflows",
         "issues", "handbook", "exceptions", "access"}
WRITES = {"merge", "approve", "doctor", "sync", "new", "rerun", "bump", "release", "issue", "auto", "adopt"}
# write unless --dry-run (doctor, workflows: unless no --fix; release: unless --list or no names; issue: view)
LOCAL = {"serve", "init", "tui", "open", "config", "login", "logout", "whoami", "market", "key", "check", "lint",
         "drift"}


def web_commands(only_on: bool = False) -> set[str]:
    """Plugin commands for the console. only_on: just those of the plugins this user has on (and the operator
    hasn't switched off for everyone); all of them count when telling whether a line writes."""
    from mason.server.api.plugins import active
    out = set()
    for p in (active() if only_on else plugins.load()):
        out |= set(getattr(p, "web_commands", ()) or ())
    return out


def parsed(argv: list[str]):
    """What the CLI itself will read from argv, or None when it won't read it. Asking its parser, not the
    words: `--fi` is --fix to argparse, and after `--` a --dry-run is only a name."""
    parser, _ = cli.build_parser()
    try:
        return parser.parse_known_args(argv)[0]
    except SystemExit:
        return None


def is_write(argv: list[str]) -> bool:
    cmd = argv[0]
    ns = parsed(argv)
    if ns is None:  # it will only print its usage; counted as a write all the same, to be safe
        return cmd in WRITES or cmd in web_commands()
    if getattr(ns, "dry_run", False):
        return False
    if cmd in ("doctor", "workflows"):
        return bool(getattr(ns, "fix", False))
    if cmd == "issue":
        return getattr(ns, "action", None) != "view"
    if cmd == "release":
        return not getattr(ns, "list", False) and bool(getattr(ns, "repos", None))
    return cmd in WRITES or cmd in web_commands()


@bp.get("/console/commands")
@need("read")
def commands():
    plug = sorted(web_commands(only_on=True))
    return jsonify({"reads": sorted(READS), "writes": sorted(WRITES), "plugins": plug,
                    "help": core.capture(cli.main, ["--help"])})


@bp.post("/console")
@need("read")
def run():
    data = body()
    line = str(data.get("line") or "").strip()
    try:
        argv = shlex.split(line)
    except ValueError as err:
        abort(400, f"can't read that line: {err}")
    if argv and argv[0] == "mason":
        argv = argv[1:]
    if not argv:
        abort(400, "type a command, e.g. mason status")
    cmd = argv[0]
    if cmd in ("help", "--help", "-h"):
        return jsonify({"text": core.capture(cli.main, ["--help"]), "write": False})
    if cmd in LOCAL:
        if cmd in ("check", "lint"):
            abort(400, f"`mason {cmd}` reads a checkout on your own machine: run it there or in CI")
        abort(400, f"`mason {cmd}` works on your own machine, not in the operator (Settings has the same)")
    if cmd not in READS | WRITES | web_commands(only_on=True):  # a plugin switched off is off here too
        abort(400, f"`mason {cmd}` isn't available in the web console")
    # "read it from stdin" (- or --notes=-): a web request has none, and the server's would hang or be empty
    if any(a == "-" or (a.startswith("--") and a.endswith("=-")) for a in argv[1:]):
        abort(400, "the web console can't read text from stdin: put the text in quotes instead of -")
    write = is_write(argv)
    if write and not can_write():
        abort(403, "this API key is read-only: add --dry-run")
    if cmd == "doctor" and not write and not getattr(parsed(argv), "dry_run", False) and not can_write():
        argv.insert(1, "--no-auto")  # (before any --) a repo's auto_fix doesn't turn a read-only key into a write
    if cmd in ("approve", "rerun", "release") and write and "--yes" not in argv:
        argv.insert(1, "--yes")  # nobody can answer y/N here; the console asked before sending
    s = user_settings(__import__("flask").g.user)
    mine = {k: s[k] for k in ("defaults", "ref", "orgs", "repos", "exclude") if s.get(k)}
    mine["org_defaults"] = s.get("org_defaults") is not False
    with as_user():
        token = config.OVERRIDE.set(mine)
        try:
            # in a copy of the context: the CLI sets its dry run for the context (set_dry_run), and on a server
            # thread that serves the next request too, that setting outlived the command
            text = contextvars.copy_context().run(core.capture, cli.main, argv)
        except core.RateLimited as err:
            abort(429, str(err))
        finally:
            config.OVERRIDE.reset(token)
    if write or (cmd == "doctor" and "(auto_fix)" in text):
        audit(f"console.{cmd}", line[:300], dry_run=False, detail=text)
    return jsonify({"text": text, "write": write})
