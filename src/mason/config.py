"""Where mason looks, and what your repos should look like.

Two files:

* Your own config, `~/.config/mason/config.toml` (`mason config` shows it):

      defaults = "your-org/your-defaults"   # a GitHub repo, or a local folder
      ref = "main"                          # branch or tag of that repo
      orgs = ["another-org"]                # added to the orgs the defaults name

  MASON_DEFAULTS and MASON_ORGS (comma separated) override it for one run.

* `mason.toml` in the defaults repo, shared by everyone who points mason at it:

      orgs = ["your-org"]
      repos = ["someone/one-more-repo"]
      exclude = ["your-org/old-*"]

      [[group]]
      name = "plugins"
      match = { org = "your-org", prefix = "plugin-" }
      from = "your-org/plugin-template"     # live reference: its settings, rulesets, files
      files = [".gitignore", "LICENSE"]     # files that must match the reference
      require = { allow_auto_merge = true } # what the reference itself must have

      [[group]]
      name = "everything else"              # no match: takes the rest
      settings = { delete_branch_on_merge = true, has_wiki = false }
      security = { secret_scanning = "enabled" }
      immutable_releases = true
      rulesets = "rulesets/default"         # folder of ruleset JSON in the defaults repo
      release_assets = ["*.zip"]            # files every release must attach (`mason releases`)
      version = "pyproject.toml"            # where the version lives (`mason bump`, `mason release`)
      changelog = ["CHANGELOG.md"]          # changelogs `mason bump` adds the new section to
      files = "files/default"               # folder copied into each repo, path for path

  `match.org` takes GitHub orgs (any case) and GitLab groups, subgroups included (`org = "grp/sub"`).
  Every group that matches a repo stacks (see layers_of): the more specific one wins key by key.
  Where a group can be named to narrow a list
  (`--group`, the web app's group menu), `acme/` names the org acme instead, and `gitlab:grp/` a
  GitLab group. Keys mason doesn't know stay on the group for plugins (`group.extra`).

* `mason.toml` in a repo named `.mason` in an org (GitHub) or group (GitLab): that org's
  defaults for its own repos, like the `.github` repo. Only its `[[group]]` tables count, and
  only for repos of that org; its `rulesets` and `files` folders are read from the `.mason`
  repo. Which groups stack for a repo, least important first:

      1. your groups without `match` (the rest), only when no group of the org's `.mason` matches
      2. the org's `.mason` groups that match (GitLab: a parent group's, then the nearest group's)
      3. your groups that name the repo with `match`
      4. the repo's own `.mason.toml` (settings_of: environments, pages, secrets, settings ...)

  So the org's `.mason` replaces your catch-all for its repos, your own explicit groups go on
  top, and the repo itself has the last word. Org groups are named `org:name` (`acme:default`).
  It is read with your own login,
  so you see what your token may read, and cached per user. `org_defaults = false` in your
  config (MASON_ORG_DEFAULTS=0, or the operator's settings) turns it off.
"""

from __future__ import annotations

import contextvars
import fnmatch
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from mason import core
from mason.core import api, file_on

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

DEFAULTS_FILE = "mason.toml"
ORG_REPO = ".mason"  # an org's (or GitLab group's) own defaults: <org>/.mason/mason.toml


def read_defaults(source: Source) -> tuple[str, str | None]:
    """The defaults file's name and its text in `source` (None when it has none)."""
    return DEFAULTS_FILE, source.read(DEFAULTS_FILE)
REPO_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GITLAB_NAME = re.compile(r"^gitlab:[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)+$")
# The GitLab client of this context (the operator sets it): defaults repos named gitlab:group/project.
GITLAB: contextvars.ContextVar = contextvars.ContextVar("mason_gitlab", default=None)
# A user's settings in place of the config file (the operator's web console sets it).
OVERRIDE: contextvars.ContextVar = contextvars.ContextVar("mason_config_override", default=None)
GROUP_KEYS = {"name", "match", "from", "files", "require", "settings", "security", "immutable_releases",
              "vulnerability_reporting", "rulesets", "release_assets",
              "version", "changelog", "topics", "labels", "actions", "required_files", "branch",
              "visibility", "description", "skip", "workflows", "environments", "variables", "secrets", "pages",
              "homepage", "code_scanning", "autolinks", "inherit", "auto_fix", "auto_push", "auto_merge"}
# More keys, each {name: (kind, what it holds)}: kind "dict" merges key by key, "list" adds up, "scalar" is
# replaced. They live in Group.more; doctor (rules.py) and `mason auto` (auto.py) read them.
MORE: dict[str, tuple[str, str]] = {
    "protect": ("dict", "branch protection in a few keys: reviews, checks, signed_commits, linear_history, ..."),
    "skip_until": ("dict", "{check: date}: skip that check until the date, then check it again"),
    "owner": ("scalar", "who to ask about the repo (a login)"),
    "team": ("scalar", "the team that looks after it"),
    "notes": ("scalar", "a line shown with the repo"),
    "auto_release": ("scalar", "mason auto pushes the version tag once the version file is ahead"),
    "auto_update_branch": ("scalar", "mason auto brings open PRs that are behind up to date"),
    "auto_close_stale": ("scalar", "mason auto closes PRs and issues untouched for this many days"),
    "auto_rerun_failed": ("scalar", "mason auto reruns a failed run's jobs up to this many attempts"),
    "auto_delete_branches": ("scalar", "mason auto deletes branches of merged PRs older than this many days"),
    "dependabot": ("dict", "a generated .github/dependabot.yml: ecosystems, interval, auto_merge"),
    "renovate": ("scalar", "a generated renovate.json: true or {extends = [...]}"),
    "codeowners": ("dict", "a generated .github/CODEOWNERS: {pattern = [owners]}"),
    "templates": ("scalar", "issue and PR templates must exist"),
    "release_notes": ("dict", "a generated .github/release.yml: {categories = {title = [labels]}, exclude}"),
    "release_drafts": ("scalar", "releases mason creates are drafts"),
    "discussions": ("list", "discussion categories that must exist"),
    "social_preview": ("scalar", "a custom social preview image must be set"),
    "archive_after": ("scalar", "months without a push before the repo is archived (--fix archives it)"),
    "properties": ("dict", "custom property values {name: value}"),
    "webhooks": ("list", "webhook URLs that must exist (checked only)"),
    "deploy_keys": ("list", "deploy key titles that must exist (checked only)"),
    "alerts": ("scalar", "where mason auto reports new drift: a Slack, Discord or other https webhook"),
}
GROUP_KEYS |= set(MORE)
# What a repo's own .mason.toml may set for itself (besides [release]): it wins over every group.
REPO_KEYS = GROUP_KEYS - {"name", "match", "from", "files", "require", "rulesets", "version", "changelog", "inherit"}
# What doctor checks for a group; `skip = [...]` turns checks off.
CHECKS = ("settings", "security", "vulnerability_reporting", "immutable_releases", "rulesets", "own_rulesets",
          "files", "required_files", "topics", "labels", "actions", "branch", "visibility", "description", "workflows",
          "plugins", "version", "environments", "variables", "secrets", "pages", "homepage", "code_scanning",
          "autolinks", "protect", "dependabot", "renovate", "codeowners", "templates", "release_notes", "discussions",
          "social_preview", "archive", "properties", "webhooks", "deploy_keys")


def config_dir() -> Path:
    """~/.config/mason (or $XDG_CONFIG_HOME/mason)."""
    return Path(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")) / "mason"


def config_file() -> Path:
    return Path(os.environ.get("MASON_CONFIG") or config_dir() / "config.toml")


def user_config() -> dict:
    path = config_file()
    try:
        return tomllib.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as err:
        raise RuntimeError(f"{path}: {err}") from err


def save_user_config(values: dict) -> Path:
    """Write the user config (a flat table of strings and string lists)."""
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for key, value in values.items():
        if value is None or value == []:
            continue
        lines.append(f"{key} = {json.dumps(value)}")
    path.write_text("\n".join(lines) + "\n")
    return path


# ── the defaults repo ────────────────────────────────────────────────────────


class Source:
    """Read files from the defaults: a local folder, a GitHub repo or a GitLab project (gitlab:group/name) at a ref."""

    def __init__(self, where: str, ref: str | None = None, allow_local: bool = True):
        self.where = where
        self.ref = ref
        self.local = Path(os.path.expanduser(where)) if allow_local and _is_local(where) else None
        self.gitlab = where[len("gitlab:"):] if not self.local and GITLAB_NAME.match(where) else None
        if not self.local and not self.gitlab and not REPO_NAME.match(where):
            raise RuntimeError(f"Not a repo (owner/name) or a folder: {where}")

    def __str__(self) -> str:
        if self.local:
            return str(self.local)
        return f"{self.where}@{self.ref}" if self.ref else self.where

    def read(self, path: str) -> str | None:
        if self.local:
            f = self.local / path
            return f.read_text() if f.is_file() else None
        if self.gitlab:
            return self._gitlab().file(self.gitlab, path, self.ref)
        return file_on(self.where, path, self.ref)

    def _gitlab(self):
        gl = GITLAB.get()
        if gl is None:
            raise RuntimeError(f"{self.where}: GitLab defaults need a GitLab login (the operator)")
        return gl

    def tree(self, folder: str) -> list[str]:
        """Every file under `folder`, as paths relative to it."""
        folder = folder.strip("/")
        if self.local:
            root = self.local / folder
            if not root.is_dir():
                return []
            return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
        if self.gitlab:
            pre = folder + "/"
            return sorted(p[len(pre):] for p in self._gitlab().blobs(self.gitlab, self.ref) if p.startswith(pre))
        ref = self.ref or "HEAD"
        try:
            t = api("GET", f"/repos/{self.where}/git/trees/{ref}?recursive=1") or {}
        except RuntimeError:
            return []
        pre = folder + "/"
        return sorted(e["path"][len(pre):] for e in t.get("tree") or []
                      if e.get("type") == "blob" and e["path"].startswith(pre))


def _is_local(where: str) -> bool:
    return where.startswith((".", "/", "~")) or Path(where).is_dir()


@dataclass
class Group:
    name: str
    match: dict = field(default_factory=dict)
    reference: str | None = None  # `from`
    files: list[str] | str | None = None
    require: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)
    security: dict = field(default_factory=dict)
    immutable_releases: bool | None = None
    vulnerability_reporting: bool | None = None
    rulesets: str | None = None
    release_assets: list[str] = field(default_factory=list)  # globs every release must attach
    version: str | None = None  # the file that holds the version: plugin.yaml, pyproject.toml, VERSION ...
    changelog: list[str] = field(default_factory=list)  # changelogs that get a section per version
    topics: list[str] = field(default_factory=list)  # topics every repo has (doctor --fix adds them)
    labels: dict = field(default_factory=dict)  # {name: color or {color, description}} (--fix creates them)
    actions: dict = field(default_factory=dict)  # enabled, allowed_actions, default_workflow_permissions, ...
    required_files: list[str] = field(default_factory=list)  # each must exist; "A|B" takes either
    branch: str | None = None  # the default branch's name (checked only)
    visibility: str | None = None  # public, private or internal (checked only)
    description: bool | None = None  # every repo needs a description (checked only)
    skip: list[str] = field(default_factory=list)  # checks to leave out (CHECKS)
    workflows: bool | dict | None = None  # workflow hardening in doctor: true, or a table (see workflows.py)
    environments: dict = field(default_factory=dict)  # {name: {reviewers, wait, branches, secrets, variables, ...}}
    variables: dict = field(default_factory=dict)  # Actions variables {NAME: value} (--fix sets them)
    secrets: list[str] = field(default_factory=list)  # Actions secrets that must exist (names only, never values)
    pages: bool | dict | None = None  # GitHub Pages: false, true, or {build, branch, path, cname, https}
    homepage: bool | str | None = None  # the repo's website: a URL, or true for its Pages address
    code_scanning: bool | None = None  # CodeQL default setup on or off
    autolinks: dict = field(default_factory=dict)  # {"HUB-": "https://tracker/HUB-<num>"}
    auto_fix: bool | None = None  # plain `mason doctor` fixes the drift too, as with --fix
    auto_push: bool | None = None  # mason's file changes go straight onto the default branch, not a PR
    auto_merge: bool | None = None  # the PRs mason opens get auto-merge
    more: dict = field(default_factory=dict)  # the MORE keys a group sets
    extra: dict = field(default_factory=dict)
    source: Source | None = None  # where its rulesets and files folders live (None: the config's defaults)
    origin: str = ""  # "" for your defaults; "acme/.mason" for a group of an org's .mason repo
    layers: list = field(default_factory=list)  # a stacked group: the groups it was made of, least important first
    inherit: bool = True  # false: the less important groups that match don't stack under this one

    def matches(self, repo: str, topics: list[str] | None = None) -> bool:
        m = self.match
        if not m:
            return True
        provider = "gitlab" if repo.startswith("gitlab:") else "github"
        if m.get("provider") and m["provider"] != provider:
            return False
        repo = repo[len("gitlab:"):] if provider == "gitlab" else repo
        name = repo.rsplit("/", 1)[-1]  # GitLab: group/subgroup/project
        orgs = _list(m.get("org"))
        if orgs and not any(in_org(repo, o) for o in orgs):
            return False
        if m.get("prefix") and not name.startswith(m["prefix"]):
            return False
        if m.get("suffix") and not name.endswith(m["suffix"]):
            return False
        names = _list(m.get("repos"))
        if names and not any(_glob(repo, n) for n in names):
            return False
        if any(_glob(repo, n) for n in _list(m.get("exclude"))):
            return False
        wanted = _list(m.get("topics"))
        return not (wanted and not set(wanted) & set(topics or []))

    def alias(self, repo: str) -> str:
        """A short name for the repo inside its group: the prefix dropped (plugin-budgets -> budgets)."""
        name = repo.rsplit("/", 1)[-1] if repo.startswith("gitlab:") else repo.split("/", 1)[-1]
        prefix = self.match.get("prefix") or ""
        return name[len(prefix):] if prefix and name.startswith(prefix) and len(name) > len(prefix) else name


def in_org(repo: str, org: str) -> bool:
    """Is `repo` (owner/name, or a GitLab group/subgroup/project without `gitlab:`) under `org`?
    GitHub owners ignore case, like GitHub does; a GitLab group takes its subgroups' projects too."""
    org = org.strip("/").lower()
    return bool(org) and repo.lower().startswith(org + "/")


def org_filter(name: str | None) -> str | None:
    """A group filter that names an org instead of a group: `acme/` (GitHub) or `gitlab:grp/sub/`.
    Returns the repo prefix without the slash, or None for a plain group name."""
    return name[:-1] if name and name.endswith("/") and len(name) > 1 else None


def orgs_of(repo: str) -> list[str]:
    """The org filters a repo falls under: `acme/` for acme/x, `gitlab:a/` and `gitlab:a/b/` for gitlab:a/b/x."""
    parts = repo.split("/")[:-1]
    return [f"{'/'.join(parts[:i])}/" for i in range(1, len(parts) + 1)]


def group_label(group: Group | None, repo: str) -> str:
    """What a list shows as a repo's group: its group's name, else its org (`acme/`, `gitlab:grp/sub/`),
    the same value the group filter takes."""
    if group:
        return group.name
    orgs = orgs_of(repo)
    return orgs[-1] if orgs else "-"


def _list(value) -> list[str]:
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


def _glob(repo: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(repo, pattern) if "/" in pattern else fnmatch.fnmatchcase(repo.split("/")[-1], pattern)


# ── stacking groups ──────────────────────────────────────────────────────────

MERGE_DICT = ("require", "settings", "security", "labels", "actions", "variables", "autolinks", "extra")
MERGE_LIST = ("topics", "required_files", "release_assets", "skip", "secrets")
MERGE_SCALAR = ("reference", "files", "rulesets", "version", "immutable_releases", "vulnerability_reporting",
                "branch", "visibility", "description", "workflows", "homepage", "code_scanning", "auto_fix",
                "auto_push", "auto_merge")


def specificity(group: Group) -> int:
    m = group.match
    if not m:
        return 0
    if m.get("repos"):
        return 3
    if m.get("prefix") or m.get("suffix"):
        return 2
    return 1


def ranked(found: list[tuple[int, Group]]) -> list[Group]:
    """Least important first: less specific first, and on a tie the one written later first."""
    return [g for _, g in sorted(found, key=lambda x: (specificity(x[1]), -x[0]))]


def merged(key: str, low, high):
    """One key of two layers: `high` wins. Tables merge key by key (environments and pages one level
    deeper), lists add up, other values are replaced when `high` sets them."""
    if key in MERGE_DICT:
        return {**(low or {}), **(high or {})}
    if key in MERGE_LIST:
        return list(dict.fromkeys(list(low or []) + list(high or [])))
    if key == "environments":
        out = {n: dict(e) for n, e in (low or {}).items()}
        for n, e in (high or {}).items():
            out[n] = {**out.get(n, {}), **e}
        return out
    if key == "pages" and isinstance(low, dict) and isinstance(high, dict):
        return {**low, **high}
    if key == "changelog":
        return list(high) if high else list(low or [])
    return low if high is None else high


def stack(layers: list[Group]) -> Group | None:
    """Groups stacked into one, least important first. One layer: that group itself."""
    if not layers:
        return None
    if len(layers) == 1:
        return layers[0]
    top = next((g for g in reversed(layers) if g.name != REPO_LAYER), layers[-1])
    out = Group(name=top.name, match=top.match, source=top.source, origin=top.origin, layers=list(layers))
    for g in layers:
        for key in MERGE_DICT + MERGE_LIST + MERGE_SCALAR + ("environments", "pages", "changelog"):
            setattr(out, key, merged(key, getattr(out, key), getattr(g, key)))
        out.more = merged_more(out.more, g.more)
    with_ref = next((g for g in reversed(layers) if g.reference), None)
    if with_ref:  # a reference's file list belongs to that reference
        out.reference = with_ref.reference
        if isinstance(with_ref.files, list) or not out.files:
            out.files = with_ref.files
    return out


REPO_LAYER = ".mason.toml"
_repo_loaded = core.Scoped("repo_layer")


def repo_layer(repo: str) -> Group | None:
    """The settings a repo's own .mason.toml gives itself, as a group named ".mason.toml" (None without).
    Its [release] table is read by versions.py; group-only keys (match, from, files, rulesets ...) are
    left out: the repo's own rulesets are its .github/rulesets files."""
    if repo in _repo_loaded:
        return _repo_loaded[repo]
    text = file_on(repo, REPO_LAYER)
    found = None
    if text:
        raw = parse_defaults(text, f"{repo}/{REPO_LAYER}")
        own = {k: v for k, v in raw.items() if k in REPO_KEYS}
        if own:
            found = make_group({**own, "name": REPO_LAYER}, 0)
            found.origin = repo
    _repo_loaded[repo] = found
    return found


def _environments(raw) -> dict:
    """environments = { production = { reviewers = ["mike", "team:acme/ops"], wait = 5, branches = ["main"],
    secrets = ["DEPLOY_TOKEN"], variables = { REGION = "eu" } } }; a bare name list makes them empty."""
    if isinstance(raw, list):
        return {str(n): {} for n in raw}
    return {str(n): dict(e or {}) for n, e in (raw or {}).items()}


@dataclass
class Config:
    source: Source | None
    orgs: list[str]
    repos: list[str]
    exclude: list[str]
    groups: list[Group]
    raw: dict = field(default_factory=dict)
    org_defaults: bool = True  # look for each org's .mason repo

    def layers_of(self, repo: str, topics: list[str] | None = None) -> list[Group]:
        """Every group that matches the repo, least important first: your catch-all (only when no
        group of the org's .mason matches), the org's .mason groups (a parent GitLab group's before its
        subgroup's), then your groups that name the repo with `match`. Within one file a more specific
        match wins (full names over prefixes and suffixes over orgs and topics over none); on a tie the
        group written first wins."""
        mine = [(i, g) for i, g in enumerate(self.groups) if g.matches(repo, topics)]
        org: list[Group] = []
        if self.org_defaults:
            for found in reversed(org_defaults_of(repo)):  # farthest first
                if found.error:
                    raise RuntimeError(found.error)
                org += ranked([(i, g) for i, g in enumerate(found.groups) if g.matches(repo, topics)])
        rest = ranked([(i, g) for i, g in mine if not g.match]) if not org else []
        layers = rest + org + ranked([(i, g) for i, g in mine if g.match])
        cut = max((i for i, g in enumerate(layers) if not g.inherit), default=0)
        return layers[cut:]

    def group_of(self, repo: str, topics: list[str] | None = None) -> Group | None:
        """The repo's group: every group that matches it, stacked (see layers_of). It carries the name,
        `match` and origin of the most important one; settings come from all of them, the more
        important one winning key by key."""
        return stack(self.layers_of(repo, topics))

    def settings_of(self, repo: str, topics: list[str] | None = None) -> Group | None:
        """What doctor holds the repo to: its stacked group, then its own .mason.toml on top (the repo wins)."""
        group = self.group_of(repo, topics)
        own = repo_layer(repo) if not repo.startswith("gitlab:") else None
        if not own:
            return group
        merged = stack((group.layers or [group]) + [own] if group else [own])
        if group:
            merged.name, merged.match = group.name, group.match
            merged.origin, merged.source = group.origin, group.source
        return merged

    def in_group(self, repo: str, name: str, topics: list[str] | None = None) -> bool:
        """Does a group filter take `repo`? `name` is a group's name (any group the repo stacks, so
        `--group all` takes every repo an "all" group matches), or an org: `acme/` for every repo of
        the GitHub org acme, `gitlab:grp/` for every project under the GitLab group grp."""
        org = org_filter(name)
        if org is not None:
            if org.startswith("gitlab:") != repo.startswith("gitlab:"):
                return False
            return in_org(repo.removeprefix("gitlab:"), org.removeprefix("gitlab:"))
        return any(g.name == name for g in self.layers_of(repo, topics))

    def find_group(self, name: str, repo: str | None = None) -> Group | None:
        """A group by name: yours, or (`org:name`) one of `repo`'s org's .mason."""
        mine = next((g for g in self.groups if g.name == name), None)
        if mine or not (repo and self.org_defaults):
            return mine
        return next((g for org in org_defaults_of(repo) for g in org.groups if g.name == name), None)

    def groups_for(self, repos: list[str]) -> list[Group]:
        """Your groups plus the .mason groups of the orgs of `repos` (each once)."""
        out = list(self.groups)
        if self.org_defaults:
            seen: set[str] = set()
            for repo in repos:
                for org in org_defaults_of(repo):
                    if org.where not in seen:
                        seen.add(org.where)
                        out += org.groups
        return out

    def excluded(self, repo: str) -> bool:
        return any(_glob(repo, p) for p in self.exclude)

    def rulesets_of(self, group: Group) -> dict[str, dict]:
        """The ruleset JSON files of a group's `rulesets` folder in the defaults repo, by ruleset name.
        A stacked group: every layer's folder, the more important layer winning by name."""
        if group.layers:
            return {k: v for g in group.layers for k, v in self.rulesets_of(g).items()}
        source = group.source or self.source
        if not group.rulesets or not source:
            return {}
        out = {}
        for f in source.tree(group.rulesets):
            if not f.endswith(".json"):
                continue
            text = source.read(f"{group.rulesets.strip('/')}/{f}")
            try:
                rs = json.loads(text or "")
            except ValueError as err:
                raise RuntimeError(f"{source}: {group.rulesets}/{f} isn't valid JSON") from err
            out[rs.get("name") or f[:-5]] = rs
        return out

    def files_of(self, group: Group) -> dict[str, str]:
        """A group's `files` folder in the defaults repo: {path in the repo: text}. Stacked: every layer's."""
        if group.layers:
            return {k: v for g in group.layers for k, v in self.files_of(g).items()}
        source = group.source or self.source
        if not isinstance(group.files, str) or not source:
            return {}
        root = group.files.strip("/")
        return {f: source.read(f"{root}/{f}") or "" for f in source.tree(root)}


def parse_defaults(text: str, where: str = DEFAULTS_FILE) -> dict:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as err:
        raise RuntimeError(f"{where}: {err}") from err


def make_group(raw: dict, i: int) -> Group:
    return Group(
        name=raw.get("name") or f"group {i + 1}",
        match=raw.get("match") or {},
        reference=raw.get("from"),
        files=raw.get("files"),
        require=raw.get("require") or {},
        settings=raw.get("settings") or {},
        security=raw.get("security") or {},
        immutable_releases=raw.get("immutable_releases"),
        vulnerability_reporting=raw.get("vulnerability_reporting"),
        rulesets=raw.get("rulesets"),
        release_assets=_list(raw.get("release_assets")),
        version=raw.get("version"),
        changelog=_list(raw.get("changelog")),
        topics=_list(raw.get("topics")),
        labels=_labels(raw.get("labels")),
        actions=raw.get("actions") or {},
        required_files=_list(raw.get("required_files")),
        branch=raw.get("branch"),
        visibility=raw.get("visibility"),
        description=raw.get("description"),
        skip=_list(raw.get("skip")),
        workflows=raw.get("workflows"),
        environments=_environments(raw.get("environments")),
        variables={str(k): str(v) for k, v in (raw.get("variables") or {}).items()},
        secrets=_list(raw.get("secrets")),
        pages=raw.get("pages"),
        homepage=raw.get("homepage"),
        code_scanning=raw.get("code_scanning"),
        autolinks={str(k): v for k, v in (raw.get("autolinks") or {}).items()},
        auto_fix=_flag(raw, "auto_fix"),
        auto_push=_flag(raw, "auto_push"),
        auto_merge=_flag(raw, "auto_merge"),
        more=_more(raw),
        inherit=raw.get("inherit") is not False,
        extra={k: v for k, v in raw.items() if k not in GROUP_KEYS},
    )


def _flag(raw: dict, key: str) -> bool | None:
    value = raw.get(key)
    if value is not None and not isinstance(value, bool):
        raise RuntimeError(f"{key} must be true or false, not {value!r}")
    return value


AUTO = ("auto_fix", "auto_push", "auto_merge")


def _more(raw: dict) -> dict:
    out = {}
    for key, (kind, _) in MORE.items():
        if key not in raw:
            continue
        value = raw[key]
        if kind == "dict" and isinstance(value, bool):
            value = {"enabled": value}  # dependabot = true: the defaults
        elif kind == "dict" and not isinstance(value, dict):
            raise RuntimeError(f"{key} must be a table")
        if kind == "list":
            value = _list(value)
        out[key] = value
    return out


def merged_more(low: dict, high: dict) -> dict:
    """Two layers' MORE keys: `high` wins."""
    out = dict(low or {})
    for key, value in (high or {}).items():
        kind = MORE[key][0]
        if kind == "dict":
            out[key] = {**(out.get(key) or {}), **value}
        elif kind == "list":
            out[key] = list(dict.fromkeys(list(out.get(key) or []) + list(value)))
        else:
            out[key] = value
    return out


def more_of(cfg: Config, repo: str) -> dict:
    """The MORE keys for one repo: its stacked group, then its own .mason.toml."""
    from mason.repos import listing

    group = cfg.settings_of(repo, (listing(cfg).get(repo) or {}).get("topics"))
    return dict(group.more) if group else {}


def auto(cfg: Config, repo: str, key: str) -> bool:
    """`auto_fix`, `auto_push` or `auto_merge` for one repo: its own .mason.toml, else its stacked group."""
    from mason.repos import listing

    group = cfg.settings_of(repo, (listing(cfg).get(repo) or {}).get("topics"))
    return bool(group and getattr(group, key))


_loaded = core.Scoped("config")


def load(orgs: list[str] | None = None, mine: dict | None = None, env: bool = True) -> Config:
    """Your config plus the defaults repo's mason.toml. `orgs` (from --org) narrows the orgs.
    The operator passes each user's settings as `mine` (env=False: no MASON_* variables, no local folders)."""
    if mine is None and OVERRIDE.get() is not None:
        mine, env = OVERRIDE.get(), False
    server = mine is not None
    if mine is None:
        mine = user_config()
        if not mine.get("defaults") and not os.environ.get("MASON_DEFAULTS"):
            mine = {**operator_settings(), **mine}
    getenv = os.environ.get if env else (lambda _k, _d=None: None)
    where = getenv("MASON_DEFAULTS") or mine.get("defaults")
    ref = getenv("MASON_DEFAULTS_REF") or mine.get("ref")
    org_on = _on(getenv("MASON_ORG_DEFAULTS"), mine.get("org_defaults", True))
    key = (where, ref, tuple(orgs or ()), tuple(_list(mine.get("orgs"))), tuple(_list(mine.get("repos"))),
           tuple(_list(mine.get("exclude"))), org_on)
    if key in _loaded:
        return _loaded[key]
    raw: dict = {}
    source = None
    if where:
        source = Source(where, ref, allow_local=not server)
        name, text = read_defaults(source)
        if text is None:
            raise RuntimeError(f"No {DEFAULTS_FILE} in {source}. Start one with: mason init {where}")
        raw = parse_defaults(text, f"{source}/{name}")
    env_orgs = [o.strip() for o in (getenv("MASON_ORGS") or "").split(",") if o.strip()]
    all_orgs = env_orgs or _unique(_list(raw.get("orgs")) + _list(mine.get("orgs")))
    cfg = Config(
        source=source,
        orgs=_unique(orgs) if orgs else all_orgs,
        repos=_unique(_list(raw.get("repos")) + _list(mine.get("repos"))),
        exclude=_list(raw.get("exclude")) + _list(mine.get("exclude")),
        groups=[make_group(g, i) for i, g in enumerate(raw.get("group") or [])],
        raw=raw,
        org_defaults=org_on,
    )
    _loaded[key] = cfg
    return cfg


def _on(env: str | None, setting) -> bool:
    """MASON_ORG_DEFAULTS (0/off/false/no) wins over the setting (true unless false or "off")."""
    if env is not None and env.strip():
        return env.strip().lower() not in ("0", "off", "false", "no")
    if isinstance(setting, str):
        return setting.strip().lower() not in ("0", "off", "false", "no")
    return setting is not False


# ── an org's own defaults: <org>/.mason ─────────────────────────────────────


@dataclass
class OrgDefaults:
    where: str  # acme/.mason or gitlab:grp/.mason
    groups: list[Group]
    error: str = ""  # a broken mason.toml: doctor says so for that org's repos instead of guessing


_org_loaded = core.Scoped("org_defaults")  # per transport, so per user and token


def org_candidates(repo: str) -> list[str]:
    """Where an org's .mason may be for `repo`, nearest first: acme/.mason, gitlab:a/b/.mason, gitlab:a/.mason."""
    if repo.startswith("gitlab:"):
        parts = repo[len("gitlab:"):].split("/")[:-1]
        return [f"gitlab:{'/'.join(parts[:i])}/{ORG_REPO}" for i in range(len(parts), 0, -1)]
    owner, _, name = repo.partition("/")
    return [f"{owner}/{ORG_REPO}"] if owner and name else []


def org_defaults_of(repo: str) -> list[OrgDefaults]:
    """The .mason defaults that apply to `repo` (nearest first), read with the current user's login."""
    out = []
    for where in org_candidates(repo):
        if where == repo:  # the .mason repo itself is no org's member for this purpose
            continue
        got = org_defaults(where)
        if got:
            out.append(got)
    return out


def defaults_of_orgs(orgs: list[str]) -> list[OrgDefaults]:
    """The .mason defaults of these orgs (GitLab groups as gitlab:grp), the ones that have one."""
    found = (org_defaults(f"{o}/{ORG_REPO}") for o in _unique(orgs))
    return [o for o in found if o]


def org_defaults(where: str) -> OrgDefaults | None:
    """`where`'s mason.toml as an org's defaults, or None when there is none (or no way to read it).

    The answer is cached in the current transport's own caches (GitLab: the GitLab client's), so
    one user's lookup is never served to another, and a repo you can't read is simply absent."""
    gitlab = where.startswith("gitlab:")
    if gitlab:
        gl = GITLAB.get()
        if gl is None:
            return None
        cache = gl.caches.space("org_defaults") if hasattr(gl.caches, "space") else gl.caches.setdefault(
            "org_defaults", {})
    else:
        cache = _org_loaded
    if where in cache:
        return cache[where]
    source = Source(where, None, allow_local=False)
    try:
        if gitlab:
            text = source.read(DEFAULTS_FILE)  # None on a 404
        else:
            got = core.get_file(where, DEFAULTS_FILE)  # None on a 404 (no repo, no file, or no access)
            text = got[0] if got else None
    except (RuntimeError, KeyError, TypeError):
        return None  # a rate limit or an outage: try again next time, cache nothing
    found = None
    if text is not None:
        org = where.rsplit("/", 1)[0]
        org = org[len("gitlab:"):] if gitlab else org
        try:
            raw = parse_defaults(text, f"{where}/{DEFAULTS_FILE}")
            groups = []
            for i, g in enumerate(raw.get("group") or []):
                grp = make_group(g, i)
                grp.name = f"{org}:{grp.name}"
                grp.source = source
                grp.origin = where
                groups.append(grp)
            found = OrgDefaults(where, groups)
        except RuntimeError as err:
            found = OrgDefaults(where, [], str(err))
    cache[where] = found
    return found


def operator_settings() -> dict:
    """With `mason login <operator>`: the defaults repo and orgs saved on the operator (no local config)."""
    from mason.transport import OperatorTransport, current
    t = current()
    if not isinstance(t, OperatorTransport):
        return {}
    try:
        got = t.get_json("/settings") or {}
    except RuntimeError:
        return {}
    out = {k: got[k] for k in ("defaults", "ref", "orgs", "repos", "exclude") if got.get(k)}
    if got.get("org_defaults") is False:
        out["org_defaults"] = False
    return out


def _labels(raw) -> dict:
    """labels = ["bug", ...] or { bug = "d73a4a", docs = { color = "0075ca", description = "..." } }."""
    if isinstance(raw, list):
        return {str(n): {} for n in raw}
    out = {}
    for name, spec in (raw or {}).items():
        spec = {"color": spec} if isinstance(spec, str) else dict(spec or {})
        if spec.get("color"):
            spec["color"] = str(spec["color"]).lstrip("#").lower()
        out[name] = spec
    return out


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


STARTER = """\
# Mason defaults (mason.toml): what the repos of these orgs should look like.
# Check: mason doctor    Fix settings and rulesets: mason doctor --fix    Files: mason sync
orgs = [{orgs}]

# Every group that matches a repo applies; the more specific one wins (full names, then prefix, then the rest).
#
# [[group]]
# name = "plugins"
# match = {{ org = "your-org", prefix = "plugin-" }}
# from = "your-org/plugin-template"      # copy settings, rulesets and files from this repo
# files = [".gitignore", "LICENSE"]

[[group]]
name = "default"
settings = {{ delete_branch_on_merge = true, allow_auto_merge = true }}
security = {{ secret_scanning = "enabled", secret_scanning_push_protection = "enabled" }}
# security = {{ dependabot_alerts = "enabled", dependabot_security_updates = "enabled" }}
# vulnerability_reporting = true         # private vulnerability reporting
# immutable_releases = true
# topics = ["your-org"]                  # topics every repo has
# labels = {{ bug = "d73a4a", dependencies = {{ color = "0366d6", description = "Updates" }} }}
# actions = {{ allowed_actions = "selected", default_workflow_permissions = "read",
#             can_approve_pull_request_reviews = false }}
# required_files = ["README.md", "LICENSE", "SECURITY.md", "CODEOWNERS|.github/CODEOWNERS"]
# branch = "main"                        # checked only: the default branch's name
# visibility = "private"                 # checked only
# description = true                     # checked only: every repo has one
# workflows = true                       # flag unpinned actions, write-all tokens, script injection
# skip = ["labels"]                      # checks to leave out for this group
# rulesets = "rulesets/default"          # ruleset JSON files (export them from GitHub)
# files = "files/default"                # files every repo of the group gets
# variables = {{ NODE_VERSION = "22" }}    # Actions variables
# secrets = ["NPM_TOKEN"]                # Actions secrets that must exist (names only: mason secrets set)
# pages = {{ build = "workflow", cname = "docs.example.com", https = true }}
# homepage = true                        # the Pages address
# code_scanning = true                   # CodeQL default setup
# autolinks = {{ "JIRA-" = "https://jira.example.com/browse/JIRA-<num>" }}
# environments = {{ production = {{ reviewers = ["you"], wait = 5, branches = ["main"], secrets = ["DEPLOY_TOKEN"] }} }}
"""
