"""mason: your GitHub repos, across orgs, from one terminal.

Repos are named as owner/name, as a bare name when only one repo has it, or by
their group alias (the group's prefix dropped). name#12 is a PR. No names: every
repo of your orgs. --org and --group narrow that down.

  mason init your-org/your-defaults   point mason at a defaults repo (or a local folder)
  mason status | prs | runs           what's going on
  mason stats [--days 30]             PRs merged, time to merge, CI success, releases
  mason rerun name [--run ID]         re-run the failed jobs of a run
  mason releases [--problems]         latest releases, missing assets, failed release runs, unreleased versions
  mason releases --unreleased         repos whose version changed but isn't released yet
  mason packages [--problems]         container images: newest tags, release images, image builds
  mason bump name [patch|minor|major] a PR with the next version (or 1.4.0) and its changelog section
  mason release [names] [--yes]       tag v<version> where it is newer than the latest release
  mason release new name v1.4.0       create a release by hand (--title, --notes, --draft, --prerelease)
  mason release tag name [v1.4.0]     push only the tag (a workflow that publishes on tags makes the release)
  mason release view name [tag]       one release in full, with the repo's recent releases
  mason pr web#12 [--diff]            one PR in detail
  mason merge [names] [--now]         auto-merge open PRs (drafts and conflicts stay)
  mason approve                       runs waiting for you (environments, outside contributors)
  mason security                      Dependabot, secret and code scanning alerts
  mason doctor [names] [--fix]        settings, security, rulesets, environments, Pages and files against the defaults
  mason doctor --summary              one line per repo: ok, or how many issues
  mason settings name [area]          every GitHub setting of a repo, by area, with webhooks, keys, teams, ...
  mason settings name key=value ...   change settings (has_wiki=off, actions.allowed_actions=selected, ...)
  mason secrets [names]               the Actions secrets the defaults name: set or missing (names only)
  mason secrets set NAME [names]      store a secret's value (read from stdin) in each repo (--env ENV)
  mason issues [names] [--mine]       open issues; mason issue new|view|close|comment name[#12] ...
  mason workflows [names] [--fix]     unpinned actions, write-all tokens, script injection; --fix: PRs that pin
  mason sync [names]                  PRs that bring shared files in line
  mason auto [names]                  what the auto_* keys allow: fix, release, update, close stale, rerun
  mason new owner/name [--group G]    a new repo, set up the way its group wants
  mason tui                           all of it, full screen
  mason login https://mason          go through Mason (the web app) with an API key: no gh needed
  mason market [install NAME]         plugins from the signed plugin index
  mason serve [--check|--users]    run Mason, the web app (the [server] extra); --users: its accounts
  mason operator add|remove|list   who may open Mason's operator page (run where Mason runs)
"""

from __future__ import annotations

import argparse
import sys

from mason import __version__, auto, config, core, defaults, issues, packages, plugins, repos, versions, workflows

ON_REPOS = ("status", "prs", "merge", "runs", "rerun", "releases", "packages", "approve", "security", "doctor", "sync",
            "repos", "stats", "workflows", "issues", "auto")


def common_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--org", action="append", metavar="ORG", help="only this org or user (repeatable)")
    common.add_argument("--group", help="only repos of this group, or of an org: acme/ (GitLab: gitlab:grp/)")
    common.add_argument("--dry-run", action="store_true", help="show what would change, change nothing")
    return common


def build_parser() -> tuple[argparse.ArgumentParser, dict]:
    p = argparse.ArgumentParser(prog="mason", description=__doc__.split("\n\n", 1)[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=__doc__.split("\n\n", 1)[1])
    p.add_argument("--version", action="version", version=f"mason {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    common = common_parser()
    names = "owner/name, name, group alias; name#12 for one PR"
    helps = {
        "status": "one line per repo: group, release, PRs, CI",
        "prs": "open PRs with checks, reviews, conflicts, auto-merge",
        "merge": "auto-merge (or --now) open PRs",
        "runs": "latest workflow runs",
        "rerun": "re-run the failed jobs of the newest failed run",
        "releases": "latest release, its assets and release runs",
        "packages": "container images: newest tags, release images, image builds",
        "approve": "approve runs waiting for you",
        "security": "open security alerts",
        "doctor": "check repos against the defaults",
        "sync": "open PRs with the group's shared files",
        "repos": "the repos mason sees and their groups",
        "stats": "PRs merged, time to merge, CI success, releases over the last days",
        "workflows": "risky workflows: unpinned actions, write-all tokens, script injection",
        "issues": "open issues across repos, by label, assignee or age",
        "auto": "what the repos' auto_* keys let mason do on its own: fix, release, tidy up (cron-friendly)",
    }
    for cmd in ON_REPOS:
        sp = sub.add_parser(cmd, parents=[common], help=helps[cmd])
        sp.add_argument("repos", nargs="*", help=names)
        if cmd == "merge":
            sp.add_argument("--now", action="store_true", help="merge right away, not via auto-merge")
            sp.add_argument("--admin", action="store_true",
                            help="merge right away past the branch rules, where GitHub lets you bypass them")
            sp.add_argument("--ready", action="store_true", help="mark named draft PRs ready first")
            sp.add_argument("--method", choices=("squash", "merge", "rebase"), default="squash")
        if cmd == "approve":
            sp.add_argument("--yes", action="store_true", help="approve without asking")
        if cmd == "rerun":
            sp.add_argument("--run", type=int, help="this run id instead of the newest failed one")
            sp.add_argument("--yes", action="store_true", help="re-run without asking")
        if cmd == "runs":
            sp.add_argument("--limit", type=int, default=3)
            sp.add_argument("--failed", action="store_true")
        if cmd in ("releases", "packages"):
            sp.add_argument("--problems", action="store_true", help="only what's missing or failed")
        if cmd == "releases":
            sp.add_argument("--unreleased", action="store_true",
                            help="only repos whose version file is newer than the latest release")
        if cmd == "doctor":
            sp.add_argument("--fix", action="store_true", help="apply settings and rulesets where they drifted")
            sp.add_argument("--no-auto", action="store_true",
                            help="only check, also repos whose .mason.toml or group sets auto_fix")
            sp.add_argument("--summary", action="store_true", help="one line per repo: ok, or how many issues")
        if cmd == "issues":
            sp.add_argument("--state", choices=("open", "closed", "all"), default="open")
            sp.add_argument("--label", action="append", metavar="LABEL", help="only with this label (repeatable)")
            sp.add_argument("--assignee", help="only assigned to this login (none: unassigned, *: any)")
            sp.add_argument("--mine", action="store_true", help="only assigned to you")
            sp.add_argument("--stale", type=int, default=0, metavar="DAYS", help="only untouched for DAYS days")
            sp.add_argument("--limit", type=int, default=20, help="per repo (max 100)")
        if cmd == "workflows":
            sp.add_argument("--fix", action="store_true", help="open a PR per repo that pins the actions to SHAs")
        if cmd == "stats":
            sp.add_argument("--days", type=int, default=30)
        if cmd == "sync":
            sp.add_argument("--only", action="append", metavar="PATH", help="only this file (repeatable)")
    sp = sub.add_parser("bump", parents=[common], help="open a PR with the next version and changelog section")
    sp.add_argument("repos", nargs="+", metavar="name", help=f"{names}; the last may be the level")
    sp.add_argument("--auto-merge", action="store_true", help="merge the PR once its checks pass")
    sp = sub.add_parser("release", parents=[common], help="tag v<version> where it is newer than the latest release")
    sp.add_argument("repos", nargs="*", help=f"{names}; none: list what each repo would release")
    sp.add_argument("--yes", action="store_true", help="push the tags without asking")
    sp.add_argument("--list", action="store_true", help="only list versions against the latest releases")
    sp.add_argument("--title", default="", help="new: the release title (default: the tag)")
    sp.add_argument("--notes", default="", help="new: the release notes, Markdown (- reads them from stdin)")
    sp.add_argument("--draft", action="store_true", help="new: save it as a draft")
    sp.add_argument("--prerelease", action="store_true", help="new: mark it as a pre-release")
    sp.add_argument("--target", default="", help="new, tag: branch or commit for the tag (default: the default branch)")
    sp.add_argument("--generate-notes", action="store_true", help="new: GitHub writes the notes from merged PRs")
    sp = sub.add_parser("secrets", parents=[common], help="Actions secrets the defaults name; `set NAME` stores one")
    sp.add_argument("repos", nargs="*", help=f"{names}; or: set NAME [names]")
    sp.add_argument("--env", default=None, help="set: an environment's secret instead of the repo's")
    sp = sub.add_parser("settings", parents=[common], help="every setting of a repo; key=value changes one")
    sp.add_argument("target", help="the repo")
    sp.add_argument("changes", nargs="*", help="an area to show, or key=value pairs to set (see --keys)")
    sp.add_argument("--keys", action="store_true", help="show each setting's key")
    sp = sub.add_parser("branches", parents=[common], help="a repo's branches; `delete NAME...` deletes some")
    sp.add_argument("target", help="the repo")
    sp.add_argument("names", nargs="*", help="delete NAME...: the branches to delete")
    sp.add_argument("--merged", action="store_true", help="delete: every merged branch too")
    sp.add_argument("--yes", action="store_true", help="delete: don't ask first")
    sp = sub.add_parser("pr", parents=[common], help="one PR in detail")
    sp.add_argument("target", help="name#12 or a PR URL")
    sp.add_argument("--diff", action="store_true")
    sp.add_argument("--body", action="store_true", help="the whole description")
    sp = sub.add_parser("issue", parents=[common], help="create, show, close, reopen or comment on an issue")
    sp.add_argument("action", choices=("new", "view", "close", "reopen", "comment"))
    sp.add_argument("target", help="new: the repo; else name#12 or an issue URL")
    sp.add_argument("text", nargs="?", default="", help="new: the title; comment: the comment")
    sp.add_argument("--body", default="", help="new: the description (- reads it from stdin)")
    sp.add_argument("--label", action="append", metavar="LABEL", help="new: a label (repeatable)")
    sp.add_argument("--assignee", action="append", metavar="LOGIN", help="new: assign (repeatable)")
    sp.add_argument("--not-planned", action="store_true", help="close: as not planned")
    sp = sub.add_parser("open", parents=[common], help="print (and open or copy) a repo or PR link")
    sp.add_argument("target", help="name or name#12")
    sp.add_argument("--actions", action="store_true")
    sp.add_argument("--releases", action="store_true")
    sp = sub.add_parser("init", help="point mason at a defaults repo (owner/repo or a local folder)")
    sp.add_argument("defaults", help="owner/repo or a folder with mason.toml")
    sp.add_argument("--ref", help="branch or tag of the defaults repo")
    sp.add_argument("--org", action="append", metavar="ORG", help="orgs for a new mason.toml")
    sp = sub.add_parser("new", parents=[common], help="create a repo the way its group wants it")
    sp.add_argument("repo", help="owner/name (name alone when mason knows one org)")
    sp.add_argument("--public", action="store_true", help="public (default: private)")
    sp.add_argument("--description", default="")
    sub.add_parser("config", help="show where mason looks and what it found")
    sp = sub.add_parser("login", help="sign in to Mason (the web app) with an API key")
    sp.add_argument("url", help="Mason's URL, e.g. https://mason.mortar.ch")
    sp.add_argument("--read", action="store_true", help="a read-only key")
    sp.add_argument("--key", help="use this API key instead of approving a code in the browser")
    sub.add_parser("logout", help="forget Mason's API key")
    sub.add_parser("whoami", help="how mason reaches GitHub, and as whom")
    sp = sub.add_parser("market", help="plugins in the plugin index: list, install, sign")
    sp.add_argument("action", nargs="?", default="list", choices=("list", "install", "keygen", "sign", "verify"))
    sp.add_argument("name", nargs="?", help="plugin to install, or the index file to sign/verify")
    sp.add_argument("--index", help="index URL or file (default: MASON_PLUGIN_INDEX or the official one)")
    sp.add_argument("--key", help="sign: the private key (PEM); verify/list: trusted public keys, comma separated")
    sub.add_parser("plugins", help="installed plugins")
    sp = sub.add_parser("tui", parents=[common], help="full screen (needs: pipx inject mason-cli textual)")

    handlers: dict = {}
    for plugin in plugins.load():
        try:
            handlers.update(plugin.add_commands(sub) or {})
        except Exception as err:  # argparse conflicts and the like
            plugins.errors.append(f"{plugin.name}: {err}")
    return p, handlers


def show_config() -> None:
    mine = config.user_config()
    print(f"config file  {config.config_file()}{'' if config.config_file().exists() else ' (none yet)'}")
    cfg = config.load()
    print(f"defaults     {cfg.source or 'none (mason init <owner/repo or folder>)'}")
    print(f"orgs         {', '.join(cfg.orgs) or 'none'}")
    if cfg.repos:
        print(f"extra repos  {', '.join(cfg.repos)}")
    if mine.get("orgs"):
        print(f"your orgs    {', '.join(mine['orgs'])} (from your config)")
    print(f"groups       {len(cfg.groups)}")
    for g in cfg.groups:
        bits = [f"match {g.match}" if g.match else "the rest"]
        if g.reference:
            bits.append(f"from {g.reference}")
        if g.rulesets:
            bits.append(f"rulesets {g.rulesets}")
        if g.files:
            bits.append(f"files {g.files}")
        print(f"  {g.name}: {', '.join(bits)}")
    if not cfg.org_defaults:
        print("org defaults off (org_defaults = false)")
    else:
        found = config.defaults_of_orgs(cfg.orgs)
        print(f"org defaults {', '.join(o.where for o in found) or 'none'} (each org's {config.ORG_REPO} repo)")
        for o in found:
            if o.error:
                print(f"  {o.error}")
            for g in o.groups:
                print(f"  {g.name}: {'match ' + str(g.match) if g.match else 'the rest of the org'}")
    names = [p.name for p in plugins.load()]
    print(f"plugins      {', '.join(names) or 'none'}")
    for err in plugins.errors:
        print(f"  broken: {err}")


def init(args) -> None:
    values = config.user_config()
    values["defaults"] = args.defaults
    if args.ref:
        values["ref"] = args.ref
    source = config.Source(args.defaults, args.ref)
    if config.read_defaults(source)[1] is None:
        owners = args.org or ([] if source.local else [args.defaults.split("/")[0]])
        orgs = ", ".join(f'"{o}"' for o in owners)
        starter = config.STARTER.format(orgs=orgs)
        if source.local:
            source.local.mkdir(parents=True, exist_ok=True)
            (source.local / config.DEFAULTS_FILE).write_text(starter)
            print(f"wrote {source.local / config.DEFAULTS_FILE}")
        else:
            print(f"{args.defaults} has no {config.DEFAULTS_FILE} yet. Commit this as a start:\n")
            print(starter)
    path = config.save_user_config(values)
    print(f"mason now uses {source} (saved in {path})")


def list_repos(cfg, names: list[str]) -> None:
    for r in names:
        g = repos.group_of(cfg, r)
        alias = g.alias(r) if g else ""
        extra = f"  ({alias})" if g and alias != core.short(r) else ""
        print(f"{r:<45} {config.group_label(g, r)}{extra}")
    print(f"{len(names)} repos")


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["operator"]:  # mason operator add|remove|list [WHO]: on the host, against Mason's database
        from mason.server.app import main as server
        return server(argv)
    if argv[:1] == ["serve"]:  # the web app: mason serve [--host H] [--port P], --check, --users
        from mason.server.app import main as server
        rest = argv[1:]
        for flag in ("--check", "--users"):
            if flag in rest:
                return server([flag[2:], *(a for a in rest if a != flag)])
        server(["serve", *rest])
        return
    parser, handlers = build_parser()
    args, extra = parser.parse_known_args(argv)
    if extra and args.cmd not in handlers:
        parser.error(f"unrecognized arguments: {' '.join(extra)}")
    args._extra = extra  # plugin commands pass these on (options before their own arguments)
    core.set_dry_run(getattr(args, "dry_run", False))
    try:
        if args.cmd == "init":
            return init(args)
        if args.cmd == "config":
            return show_config()
        if args.cmd in ("login", "logout", "whoami"):
            from mason import login
            if args.cmd == "login":
                return login.login(args.url, "read" if args.read else "write", args.key)
            return login.logout() if args.cmd == "logout" else login.whoami()
        if args.cmd == "market":
            from mason import market
            return market.command(args.action, args.name, args.index, args.key)
        if args.cmd == "plugins":
            for p in plugins.load():
                print(f"{p.name:<16} {p.description}")
            for err in plugins.errors:
                print(f"broken: {err}")
            if not plugins.load() and not plugins.errors:
                print("No plugins installed (pipx inject mason-cli <package>).")
            return None
        if not core.transport().logged_in():
            sys.exit("Log in first: gh auth login (or mason login <Mason URL>)")
        if args.cmd in handlers:
            return handlers[args.cmd](args)
        cfg = config.load(getattr(args, "org", None))
        if args.cmd == "tui":
            try:
                from mason import tui
            except ImportError as err:
                sys.exit(f"The TUI needs Textual: pipx inject mason-cli textual. ({err})")
            return tui.run(cfg, dry_run=core.dry_run(), group=args.group)
        if args.cmd == "new":
            repo = args.repo if "/" in args.repo or len(cfg.orgs) != 1 else f"{cfg.orgs[0]}/{args.repo}"
            return defaults.create_repo(cfg, repo, args.group, args.public, args.description)
        if args.cmd in ("pr", "open"):
            repo, number = repos.resolve(cfg, args.target)
            if args.cmd == "open":
                return repos.open_page(repo, number, args.actions, args.releases)
            if not number:
                sys.exit("Name the PR: mason pr name#12")
            return repos.pr_detail(repo, number, args.diff, args.body)
        if args.cmd == "issue":
            return issue(cfg, args)
        if args.cmd == "bump":
            level = "patch"
            if len(args.repos) > 1 and versions.is_level(args.repos[-1]):
                level = args.repos.pop()
            names, _ = repos.pick_repos(cfg, args.repos, args.group)
            return versions.bump_all(cfg, names, level, args.auto_merge)
        if args.cmd == "secrets":
            return secrets_command(cfg, args)
        if args.cmd == "settings":
            return settings_command(cfg, args)
        if args.cmd == "branches":
            return branches_command(cfg, args)
        if args.cmd == "release" and args.repos[:1] in (["new"], ["view"], ["tag"]):
            return release_new_or_view(cfg, args)
        if args.cmd == "release":
            names, _ = repos.pick_repos(cfg, args.repos, args.group)
            if args.list or not args.repos:
                return versions.summary(cfg, names)
            return versions.release_all(cfg, names, args.yes)
        names, pick = repos.pick_repos(cfg, args.repos, args.group)
        if pick and args.cmd != "merge":
            sys.exit("name#12 works with merge, pr and open")
        return run(cfg, args, names, pick)
    except RuntimeError as err:
        sys.exit(str(err))


def secrets_command(cfg, args) -> None:
    """mason secrets [names] lists; mason secrets set NAME [names] [--env ENV] reads the value from stdin."""
    from mason import extras
    if args.repos[:1] != ["set"]:
        names, _ = repos.pick_repos(cfg, args.repos, args.group)
        return extras.secrets_list(cfg, names)
    if len(args.repos) < 2:
        sys.exit("Name the secret: mason secrets set NAME [names] [--env ENV]")
    name, rest = args.repos[1], args.repos[2:]
    if not rest:
        sys.exit("Name the repos too (a secret goes to every repo named): mason secrets set NAME web api")
    names, _ = repos.pick_repos(cfg, rest, args.group)
    if sys.stdin.isatty():
        import getpass
        value = getpass.getpass(f"Value of {name} (not shown): ")
    else:
        value = sys.stdin.read()
        value = value[:-1] if value.endswith("\n") else value
    return extras.secrets_set(names, name, value, args.env)


def release_new_or_view(cfg, args) -> None:
    """mason release new name TAG [...] and mason release view name [TAG]."""
    from mason import releases
    action, rest = args.repos[0], args.repos[1:]
    if not rest:
        sys.exit(f"Name the repo: mason release {action} name" + (" v1.4.0" if action == "new" else " [tag]"))
    repo, _ = repos.resolve(cfg, rest[0])
    tag = rest[1] if len(rest) > 1 else ""
    if action == "view":
        return releases.view(cfg, repo, tag or None)
    if action == "tag":
        tag = tag or releases.suggest_tag(cfg, repo)
        if not args.yes and not core.dry_run():
            try:
                answer = input(f"Push the tag {tag} on {args.target or 'the default branch'} of {repo}? [y/N] ")
            except EOFError:
                answer = ""
            if answer.strip().lower() not in ("y", "yes"):
                print("left as it is")
                return None
        releases.push_tag(repo, tag, args.target, cfg)
        return None
    if not tag:
        sys.exit("Name the tag: mason release new name v1.4.0")
    notes = sys.stdin.read() if args.notes == "-" else args.notes
    if not args.draft and not repo.startswith("gitlab:") and config.more_of(cfg, repo).get("release_drafts"):
        args.draft = True
        print("a draft: the repo's release_drafts says so (publish it on GitHub)")
    if not args.yes and not core.dry_run():
        what = "draft" if args.draft else "pre-release" if args.prerelease else "release"
        try:
            answer = input(f"Create the {what} {tag} of {repo}? [y/N] ")
        except EOFError:
            answer = ""
        if answer.strip().lower() not in ("y", "yes"):
            print("left as it is")
            return None
    releases.create(repo, tag, args.title, notes, args.draft, args.prerelease, args.target, args.generate_notes)
    return None


def settings_command(cfg, args) -> None:
    from mason import catalog

    repo, _ = repos.resolve(cfg, args.target)
    if repo.startswith("gitlab:"):
        sys.exit("GitLab projects' settings are in the web app (Mason reaches GitLab there)")
    pairs = [c for c in args.changes if "=" in c]
    if not pairs:
        catalog.show(catalog.read_github(repo), " ".join(args.changes), keys=args.keys)
        return
    try:
        changes = catalog.clean("github", dict(c.split("=", 1) for c in pairs))
    except ValueError as err:
        sys.exit(str(err))
    said = catalog.write_github(repo, changes)
    for line in said:
        core.say(f"{'[dry-run] ' if core.dry_run() else ''}{repo}: {line}")
    if catalog.failed(said):
        sys.exit(1)
    kept = [k for k in changes if catalog.find("github", k).keep]
    if kept:
        core.say(f"to keep them, add them to {repo}'s .mason.toml (the web app's settings panel can write it)")


def branches_command(cfg, args) -> None:
    from mason import branches

    repo, _ = repos.resolve(cfg, args.target)
    if repo.startswith("gitlab:"):
        sys.exit("GitLab projects' branches are in the web app (Mason reaches GitLab there)")
    if not args.names:
        if args.merged:
            sys.exit(f"delete the merged branches with: mason branches {args.target} delete --merged")
        return branches.show(branches.github(repo))
    if args.names[0] != "delete" or (len(args.names) == 1 and not args.merged):
        sys.exit("mason branches REPO delete NAME... (or delete --merged)")
    try:
        names = [branches.valid_name(n) for n in args.names[1:]]
    except ValueError as err:
        sys.exit(str(err))
    if not core.dry_run() and not args.yes:
        what = " and ".join(x for x in (", ".join(names), "every merged branch" if args.merged else "") if x)
        try:
            answer = input(f"Delete {what} of {repo}? [y/N] ")
        except EOFError:
            answer = ""
        if answer.strip().lower() not in ("y", "yes"):
            print("left as they are")
            return None
    lines, ok = branches.delete(repo, names, merged=args.merged)
    for line in lines:
        core.say(f"{repo}: {line}")
    if not ok:
        sys.exit(1)
    return None


def issue(cfg, args) -> None:
    repo, number = repos.resolve(cfg, args.target)
    if args.action == "new":
        body = sys.stdin.read() if args.body == "-" else args.body
        issues.create(repo, args.text, body, args.label, args.assignee)
        return
    if not number:
        sys.exit(f"Name the issue: mason issue {args.action} name#12")
    if args.action == "view":
        issues.view(repo, number)
    elif args.action == "comment":
        issues.comment(repo, number, sys.stdin.read() if args.text == "-" else args.text)
    else:
        issues.set_state(repo, number, args.action == "close", args.not_planned)


def run(cfg, args, names: list[str], pick: dict) -> None:
    if args.cmd == "repos":
        return list_repos(cfg, names)
    if args.cmd == "status":
        return repos.status(cfg, names)
    if args.cmd == "stats":
        from mason import stats
        return stats.show(names, args.days)
    if args.cmd == "prs":
        return repos.prs(cfg, names)
    if args.cmd == "runs":
        return repos.runs(names, args.limit, args.failed)
    if args.cmd == "rerun":
        if not args.repos:
            sys.exit("Name the repo: mason rerun hubra")
        return repos.rerun(names, args.run, args.yes)
    if args.cmd == "releases":
        return repos.releases(cfg, names, args.problems, args.unreleased)
    if args.cmd == "packages":
        return packages.packages(cfg, names, args.problems)
    if args.cmd == "approve":
        return repos.approve(names, args.yes)
    if args.cmd == "security":
        return repos.security(names)
    if args.cmd == "doctor":
        if args.summary and not args.fix:
            return defaults.doctor_summary(cfg, names)  # only checks, also where auto_fix is set
        return defaults.doctor_all(cfg, names, args.fix, not args.no_auto)
    if args.cmd == "workflows":
        return workflows.workflows(cfg, names, args.fix)
    if args.cmd == "issues":
        return issues.issues(names, args.state, args.label, args.assignee, args.mine, args.stale, args.limit)
    if args.cmd == "sync":
        ctx = defaults.sync_ctx(cfg, names, args.only)
        unknown = sorted({p for w in ctx["wants"].values() for p in w.get("unknown", [])})
        if unknown:
            sys.exit(f"not among the synced files: {', '.join(unknown)}")
        return core.for_each(names, defaults.sync, ctx)
    if args.cmd == "auto":
        return auto.run(cfg, names)
    if args.cmd == "merge":
        ctx = {"pick": pick, "now": args.now or args.admin, "ready": args.ready, "method": args.method,
               "bypass": args.admin}
        return core.for_each(names, repos.merge, ctx)
    return None


if __name__ == "__main__":
    main()
