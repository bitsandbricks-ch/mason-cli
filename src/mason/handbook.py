"""The handbook a repo follows: a repo of written rules (chapters), profiles, templates and agent skills.

Nothing is built in. A repo follows a handbook only when one is named, first found wins:

  1. the repo's own .mason.toml:          [handbook] repo = "owner/handbook"
  2. your config (~/.config/mason):       handbook = "owner/handbook"   (or a local folder)
  3. the defaults repo's mason.toml:      handbook = "owner/handbook"

The repo's .mason.toml says which profile and version of it the repo follows:

  [handbook]
  repo = "owner/handbook"   # optional, see above; written by `mason adopt` so CI needs no config
  profile = "web-app"
  version = "v1"            # a tag or branch of the handbook; none: its default branch

A handbook is any repo (GitHub, GitLab or a folder) laid out like this; a `handbook.toml` at its root
may move the folders (`core = "rules"`, `profiles = "profiles"`, `skills = "skills"`, `templates = "templates"`):

  core/*.md               chapters every repo reads
  profiles/<name>.toml    what a profile needs:
      description = "A web app with an API and a database"
      chapters = ["blocks/api.md", "blocks/database.md"]   # read on top of core/
      files = ["AGENTS.md", "CLAUDE.md", "CHANGELOG.md|changelog.d"]   # a|b: either will do
      labels = ["bug", "feature"]           # or { bug = "d73a4a" }: mason doctor checks them
      skills = ["release", "pr-review"]     # synced into .claude/skills by mason sync
      [check]                               # what `mason check` looks at offline
      fragments = "changelog.d"             # every branch adds a changelog fragment here
      migrations = "backend/migrations/versions"   # one Alembic head (true: find the folders)
  skills/<name>/SKILL.md  agent skills (and the files next to them)
  templates/AGENTS.md     what `mason adopt` writes (<app> and <profile> filled in)

`mason handbook` reads it (and keeps the profile in ~/.cache/mason/handbook, so `mason check` works offline).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from mason import config, core

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

LAYOUT = {"core": "core", "profiles": "profiles", "skills": "skills", "templates": "templates"}
PROFILE_KEYS = {"description", "chapters", "files", "labels", "skills", "check", "status"}
CHECK_KEYS = {"fragments", "migrations", "skip"}
TABLE_KEYS = {"repo", "profile", "version"}
LOCK = ".claude/skills/skills-lock.json"
SKILLS_DIR = ".claude/skills"


@dataclass
class Spec:
    """Which handbook a repo follows, and where that was said."""
    where: str | None = None  # owner/repo, gitlab:group/repo or a folder; None: no handbook
    version: str | None = None
    profile: str | None = None
    said: str = ""  # ".mason.toml", "your config", "the defaults"

    def __bool__(self) -> bool:
        return bool(self.where)


def table_of(raw: dict) -> dict:
    """The [handbook] table of a parsed .mason.toml or mason.toml (a plain string names only the repo)."""
    value = raw.get("handbook")
    if isinstance(value, str):
        return {"repo": value}
    return dict(value) if isinstance(value, dict) else {}


def spec(own: dict | None = None, defaults_raw: dict | None = None, mine: dict | None = None) -> Spec:
    """The handbook for a repo whose .mason.toml says `own` (parsed), under these defaults and your config."""
    from mason import here
    table = table_of(own or {})
    local = here.local()  # in the web app: no config file, no environment and no folders of the server's
    if mine is None:
        mine = config.user_config() if local else (config.OVERRIDE.get() or {})
    found = Spec(version=table.get("version"), profile=table.get("profile"))
    for where, said in ((table.get("repo"), ".mason.toml"),
                        (os.environ.get("MASON_HANDBOOK") if local else None, "MASON_HANDBOOK"),
                        (table_of(mine).get("repo"), "your config"),
                        (table_of(defaults_raw or {}).get("repo"), "the defaults")):
        if where:
            found.where, found.said = str(where), said
            break
    if found.version is None and found.where:  # your config or the defaults may pin a version for everyone
        found.version = table_of(mine).get("version") or table_of(defaults_raw or {}).get("version")
    return found


def web_link(where: str) -> str | None:
    if config.REPO_NAME.match(where) and not config._is_local(where):
        return f"{core.WEB}/{where}"
    if where.startswith("gitlab:"):
        from mason import glab
        return f"{glab.web_url()}/{where[len('gitlab:'):]}"
    return None


# ── reading a handbook ───────────────────────────────────────────────────────


@dataclass
class Handbook:
    source: config.Source
    layout: dict = field(default_factory=lambda: dict(LAYOUT))
    note: str = ""  # e.g. the version isn't a tag yet, so the default branch was read

    def path(self, part: str, *rest: str) -> str:
        return "/".join([self.layout[part].strip("/"), *rest])

    def read(self, path: str) -> str | None:
        return self.source.read(path)

    def profiles(self) -> list[str]:
        return sorted(f[:-5] for f in self.source.tree(self.layout["profiles"]) if f.endswith(".toml") and "/" not in f)

    def profile(self, name: str) -> dict:
        text = self.read(self.path("profiles", f"{name}.toml"))
        if text is None:
            known = ", ".join(self.profiles()) or "none"
            raise RuntimeError(f"{self.source} has no profile {name!r} (profiles: {known})")
        return parse_profile(text, f"{self.source}/{self.path('profiles', name + '.toml')}")

    def core_chapters(self) -> list[str]:
        return [self.path("core", f) for f in self.source.tree(self.layout["core"])
                if f.endswith(".md") and f.lower() != "readme.md"]

    def title(self, path: str) -> str:
        for line in (self.read(path) or "").splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return path.rsplit("/", 1)[-1].removesuffix(".md")

    def link(self, path: str) -> str:
        base = web_link(self.source.where)
        if not base:
            return str(Path(self.source.where).expanduser() / path)
        ref = self.source.ref or "HEAD"
        return f"{base}/-/blob/{ref}/{path}" if self.source.gitlab else f"{base}/blob/{ref}/{path}"

    def skill_files(self, name: str) -> dict[str, str]:
        """{path inside the skill's folder: text} (SKILL.md and whatever is next to it)."""
        root = self.path("skills", name)
        files = {f: self.read(f"{root}/{f}") or "" for f in self.source.tree(root)}
        if "SKILL.md" not in files:
            raise RuntimeError(f"{self.source} has no skill {name!r} ({root}/SKILL.md)")
        return files

    def template(self, name: str) -> str | None:
        return self.read(self.path("templates", name))


def parse_profile(text: str, where: str) -> dict:
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as err:
        raise RuntimeError(f"{where}: {err}") from err
    return {"description": str(raw.get("description") or ""), "status": str(raw.get("status") or ""),
            "chapters": config._list(raw.get("chapters")), "files": config._list(raw.get("files")),
            "labels": config._labels(raw.get("labels")), "skills": config._list(raw.get("skills")),
            "check": dict(raw.get("check") or {}), "raw": raw}


def open_handbook(found: Spec) -> Handbook:
    """The handbook at its version; a version that isn't a tag or branch yet reads the default branch."""
    if not found:
        raise RuntimeError("No handbook: set handbook = \"owner/repo\" in your config or the defaults' mason.toml, "
                           "or [handbook] repo = \"owner/repo\" in the repo's .mason.toml")
    from mason import here
    source = config.Source(found.where, found.version, allow_local=here.local())
    book = Handbook(source)
    layout_text = source.read("handbook.toml")
    if layout_text is None and found.version and not source.local and not source.tree(LAYOUT["profiles"]):
        source = config.Source(found.where, None, allow_local=here.local())
        book = Handbook(source, note=f"{found.version} isn't a tag or branch of {found.where} yet: "
                                     "read its default branch")
        layout_text = source.read("handbook.toml")
    if layout_text:
        try:
            raw = tomllib.loads(layout_text)
        except tomllib.TOMLDecodeError as err:
            raise RuntimeError(f"{source}/handbook.toml: {err}") from err
        book.layout.update({k: str(v) for k, v in raw.items() if k in LAYOUT})
    return book


_doctor = core.Scoped("handbook_profiles")


def doctor_profile(table: dict, default) -> tuple[dict | None, str]:
    """The profile a repo's (stacked) [handbook] table names, for doctor and sync: (profile or None, a problem
    or ""). The profile carries `skill_files`: {path in the repo: text} of its skills and their lock."""
    found = spec({"handbook": table}, {"handbook": default} if default else {})
    if not found or not found.profile:
        return None, ""
    key = (found.where, found.version, found.profile)
    if key not in _doctor:
        try:
            book = open_handbook(found)
            prof = book.profile(found.profile)
            prof["skill_files"] = skill_repo_files(book, prof["skills"]) if prof["skills"] else {}
            _doctor[key] = (prof, "")
        except RuntimeError as err:
            _doctor[key] = (None, f"handbook: {err}")
    return _doctor[key]


# ── the offline copy `mason check` reads ─────────────────────────────────────


def cache_dir() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")) / "mason" / "handbook"


def cache_key(where: str, version: str | None) -> str:
    return re.sub(r"[^\w.-]+", "_", f"{where}@{version or 'default'}")


def remember(found: Spec, name: str, profile: dict) -> Path:
    """Keep a profile for `mason check` (offline): ~/.cache/mason/handbook/<repo@version>/<name>.json."""
    path = cache_dir() / cache_key(found.where or "", found.version) / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: v for k, v in profile.items() if k != "raw"}, indent=2, default=str))
    return path


def remembered(found: Spec, name: str) -> dict | None:
    path = cache_dir() / cache_key(found.where or "", found.version) / f"{name}.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def profile_offline(found: Spec, folder: str | None = None) -> tuple[dict | None, str]:
    """The repo's profile without the network: from a handbook folder (--handbook, or a handbook that is a
    folder), else from the cache. (profile or None, where it came from or why there is none)."""
    if not found.profile:
        return None, "no profile in .mason.toml"
    local = folder or (found.where if found.where and config._is_local(found.where) else None)
    if local:
        book = Handbook(config.Source(local))
        layout_text = book.read("handbook.toml")
        if layout_text:
            book.layout.update({k: str(v) for k, v in tomllib.loads(layout_text).items() if k in LAYOUT})
        return book.profile(found.profile), local
    got = remembered(found, found.profile)
    if got:
        return got, "the cache (mason handbook refreshes it)"
    return None, f"profile {found.profile} isn't cached: run `mason handbook` once online, or pass --handbook FOLDER"


# ── skills: copied into .claude/skills, pinned by hash ──────────────────────


def skill_hash(files: dict[str, str]) -> str:
    """sha256 over a skill's files, path by path in sorted order: the same files give the same hash."""
    h = hashlib.sha256()
    for path in sorted(files):
        h.update(path.encode() + b"\0" + files[path].encode() + b"\0")
    return h.hexdigest()


def skill_texts(book: Handbook, names: list[str]) -> dict[str, dict[str, str]]:
    return {n: book.skill_files(n) for n in names}


def lock_text(book: Handbook, skills: dict[str, dict[str, str]]) -> str:
    """skills-lock.json: where each skill came from and the hash of its files (`mason check` compares)."""
    entries = {}
    for name, files in sorted(skills.items()):
        entries[name] = {"source": book.source.where, "sourceType": "local" if book.source.local else
                         "gitlab" if book.source.gitlab else "github", "ref": book.source.ref or "",
                         "skillPath": book.path("skills", name, "SKILL.md"), "files": sorted(files),
                         "computedHash": skill_hash(files)}
    return json.dumps({"version": 1, "generatedBy": "mason sync", "skills": entries}, indent=2) + "\n"


def skill_repo_files(book: Handbook, names: list[str]) -> dict[str, str]:
    """{path in the repo: text}: each skill under .claude/skills/<name>/ and the lock next to them."""
    skills = skill_texts(book, names)
    out = {f"{SKILLS_DIR}/{n}/{p}": t for n, files in skills.items() for p, t in files.items()}
    out[LOCK] = lock_text(book, skills)
    return out


# ── mason handbook ───────────────────────────────────────────────────────────


def local_table() -> dict:
    """The [handbook] table of this checkout's .mason.toml, read from disk (it may not be pushed yet)."""
    from mason import here
    root = here.root() if here.local() else None
    if root is None:
        return {}
    _, text = config.repo_file(lambda p: (root / p).read_text() if (root / p).is_file() else None, "")
    return table_of(config.parse_defaults(text, config.REPO_LAYER)) if text else {}


def repo_table(cfg, repo: str) -> dict:
    """A repo's [handbook]: its group's (or org's .mason) table with the repo's own .mason.toml on top."""
    group = cfg.settings_of(repo)
    return dict((group.more if group else {}).get("handbook") or {})


def wanted(cfg, repo: str | None) -> Spec:
    """The handbook spec for a named repo (from GitHub), or for this checkout (from disk) when none is named."""
    table = repo_table(cfg, repo) if repo else local_table()
    return spec({"handbook": table}, cfg.raw)


def describe(cfg, repo: str | None, profile: str | None = None, list_profiles: bool = False) -> dict:
    found = wanted(cfg, repo)
    if profile:
        found.profile = profile
    book = open_handbook(found)
    out: dict = {"handbook": found.where, "version": found.version, "said": found.said, "ref": book.source.ref,
                 "note": book.note, "profiles": book.profiles()}
    if list_profiles or not found.profile:
        out["profile_details"] = {n: book.profile(n).get("description", "") for n in out["profiles"]}
        return out
    prof = book.profile(found.profile)
    remember(found, found.profile, prof)
    chapters = [("core", p) for p in book.core_chapters()] + [("profile", p) for p in prof["chapters"]]
    out.update(profile=found.profile, description=prof["description"], status=prof["status"],
               chapters=[{"part": part, "path": p, "title": book.title(p), "link": book.link(p)}
                         for part, p in chapters],
               files=prof["files"], labels=prof["labels"], skills=prof["skills"], check=prof["check"])
    return out


def show(cfg, repo: str | None, profile: str | None = None, list_profiles: bool = False) -> None:
    d = describe(cfg, repo, profile, list_profiles)
    core.emit(d)
    if core.json_mode():
        return
    print(f"handbook  {d['handbook']}" + (f" {d['version']}" if d["version"] else "") + f"  (from {d['said']})")
    if d["note"]:
        print(f"          {d['note']}")
    if "profile_details" in d:
        if not list_profiles:
            print("no profile: set [handbook] profile in .mason.toml (mason adopt does), or pass --profile")
        print("profiles:")
        for name, about in d["profile_details"].items():
            print(f"  {name:<14} {about}")
        return
    print(f"profile   {d['profile']}" + (f" ({d['status']})" if d["status"] else "")
          + (f": {d['description']}" if d["description"] else ""))
    print("\nRead these chapters:")
    width = max((len(c["title"]) for c in d["chapters"]), default=0)
    for c in d["chapters"]:
        print(f"  {c['part']:<8} {c['title']:<{width}}  {c['link']}")
    if d["files"]:
        print(f"\nFiles the profile needs (mason check):  {', '.join(d['files'])}")
    if d["labels"]:
        print(f"Labels (mason doctor):                   {', '.join(d['labels'])}")
    if d["skills"]:
        print(f"Agent skills (mason sync):               {', '.join(d['skills'])}")


# ── mason adopt ──────────────────────────────────────────────────────────────

ADOPT_BRANCH = "mason/adopt-handbook"


def handbook_table(where: str, profile: str, version: str | None) -> str:
    lines = ["[handbook]", f"repo = {json.dumps(where)}", f"profile = {json.dumps(profile)}"]
    if version:
        lines.append(f"version = {json.dumps(version)}")
    return "\n".join(lines) + "\n"


def with_table(text: str | None, table: str) -> str:
    """A .mason.toml with its [handbook] table (and any `handbook = ...` line) replaced by `table`."""
    if not text:
        return f"# Mason's settings for this repo (see mason's README)\n\n{table}"
    out, skipping = [], False
    for line in text.splitlines():
        header = re.match(r"^\s*\[([^\]]+)\]\s*(#.*)?$", line)
        if header:
            skipping = header.group(1).strip() == "handbook"
            if skipping:
                continue
        if skipping or re.match(r"^\s*handbook\s*=", line):
            continue
        out.append(line)
    body = "\n".join(out).rstrip()
    return (body + "\n\n" if body else "") + table


def agents_text(book: Handbook, found: Spec, repo: str, current: str | None) -> str | None:
    """AGENTS.md: the handbook's template for a repo without one; a link added to one that lacks it; None: as is."""
    name = found.where.removeprefix("gitlab:")
    link = web_link(found.where) or found.where
    if current is None:
        template = book.template("AGENTS.md")
        if template:
            text = template.replace("<app>", core.short(repo).rsplit("/", 1)[-1]).replace("<profile>", found.profile)
            return text if name in text else text.rstrip() + f"\n\nHandbook: {link}\n"
        return (f"# Rules for coding agents\n\nThis repo follows the handbook {link}, profile **{found.profile}** "
                "(see `.mason.toml`). Read its core chapters and the ones the profile lists "
                "(`mason handbook` prints them).\n\n## Repo-specific rules\n\n- TODO\n")
    if name in current:
        return None
    note = f"This repo follows the handbook {link}, profile **{found.profile}** (see `.mason.toml`).\n"
    lines = current.splitlines(keepends=True)
    at = next((i + 1 for i, line in enumerate(lines) if line.startswith("# ")), 0)
    rest = "".join(lines[at:]).lstrip("\n")
    return "".join(lines[:at]) + ("\n" if at else "") + note + ("\n" + rest if rest else "")


def adopt(cfg, repo: str, profile: str | None, version: str | None) -> dict:
    """One PR that makes `repo` follow the handbook: .mason.toml with [handbook], AGENTS.md (and CLAUDE.md
    importing it), and the profile's skills with their lock. Returns what it did."""
    found = spec({"handbook": repo_table(cfg, repo)}, cfg.raw)
    found.profile = profile or found.profile
    found.version = version or found.version
    if not found.profile:
        book = open_handbook(found)
        raise RuntimeError(f"Name the profile: mason adopt {repo} --profile P (profiles: "
                           f"{', '.join(book.profiles()) or 'none'})")
    book = open_handbook(found)
    prof = book.profile(found.profile)
    info = core.api("GET", f"/repos/{repo}") or {}
    base = info.get("default_branch") or "main"
    path, _ = config.repo_file(lambda p: core.file_on(repo, p, base), repo)
    got = core.get_file(repo, path, base)
    files: dict[str, tuple[str, str | None]] = {}
    new = with_table(got[0] if got else None, handbook_table(found.where, found.profile, found.version))
    if not got or new != got[0]:
        files[path] = (new, got[1] if got else None)
    agents = core.get_file(repo, "AGENTS.md", base)
    text = agents_text(book, found, repo, agents[0] if agents else None)
    if text is not None:
        files["AGENTS.md"] = (text, agents[1] if agents else None)
    if core.get_file(repo, "CLAUDE.md", base) is None:
        files["CLAUDE.md"] = ("@AGENTS.md\n", None)
    ours = set()
    if prof["skills"]:
        from mason.defaults import blob_shas
        ours = blob_shas(repo, base)
        for p, t in skill_repo_files(book, prof["skills"]).items():
            if ours.get(p) != core.git_blob_sha(t):
                files[p] = (t, ours.get(p))
    out = {"repo": repo, "handbook": found.where, "profile": found.profile, "version": found.version,
           "files": sorted(files), "note": book.note}
    if not files:
        out["url"] = None
        return out
    from mason.defaults import blob_shas, has
    ours = ours or blob_shas(repo, base)
    todo = [n for n in prof["files"] if not has(set(ours) | set(files) | {p.rsplit("/", 1)[0] for p in ours}, n)]
    chapters = "\n".join(f"- [{book.title(p)}]({book.link(p)})" for p in book.core_chapters() + prof["chapters"])
    body = (f"Makes this repo follow the handbook {web_link(found.where) or found.where}, profile "
            f"**{found.profile}**" + (f" ({found.version})" if found.version else "") + ".\n\n"
            + "\n".join(f"- `{p}`" for p in sorted(files) if not p.startswith(SKILLS_DIR + "/") or p == LOCK)
            + (f"\n- the profile's agent skills in `{SKILLS_DIR}/`: {', '.join(prof['skills'])}" if prof["skills"]
               else "")
            + ("\n\nFill in the repo-specific parts of AGENTS.md (its `<...>` placeholders) before merging."
               if "AGENTS.md" in files and not agents else "")
            + ("\n\nStill missing for the profile (add them in follow-up PRs; `mason check` lists them):\n\n"
               + "\n".join(f"- `{n}`" for n in todo) if todo else "")
            + (f"\n\nChapters to read:\n\n{chapters}" if chapters else "")
            + "\n\nOpened by `mason adopt`.")
    out["url"] = core.open_pr(repo, base, ADOPT_BRANCH, files, f"chore: follow the handbook ({found.profile})",
                              f"Follow the handbook: profile {found.profile}", body)
    out["missing"] = todo
    return out
