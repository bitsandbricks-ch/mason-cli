"""`mason lint [folder]`: a defaults repo (or a handbook) checked before anyone's repos are held to it. Offline.

A defaults repo (mason.toml at its root, like your-org/.mason):
  mason.toml parses; top-level and group keys are known (unknown ones are kept for plugins: a warning);
  every group builds, has a unique name, a known `match` and a `from` that names a repo;
  `skip` and `skip_until` name real checks, with dates; the `rulesets` and `files` folders exist and
  every ruleset file is JSON GitHub takes.
A handbook (a profiles folder, see handbook.py):
  every profile parses, its keys are known, and the chapters, skills and templates it names exist.

Meant for CI on the defaults repo: `mason lint` exits 1 on errors.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

from mason import config, core, handbook
from mason.check import Finding, ruleset_file, skip_until

TOP_KEYS = {"orgs", "repos", "exclude", "group", "builtin", "handbook", "gitlab_groups", "gitlab_projects"}
MATCH_KEYS = {"org", "prefix", "suffix", "repos", "exclude", "topics", "provider"}


def defaults(root: Path) -> list[Finding]:
    path = root / config.DEFAULTS_FILE
    name = config.DEFAULTS_FILE
    try:
        raw = config.parse_defaults(path.read_text(), name)
    except RuntimeError as err:
        return [Finding("mason_toml", "error", str(err).removeprefix(f"{name}: "), name)]
    found = [Finding("mason_toml", "warning", f"unknown top-level key {k} (kept for plugins)", name)
             for k in sorted(set(raw) - TOP_KEYS)]
    groups = raw.get("group") or []
    if not isinstance(groups, list):
        return [*found, Finding("mason_toml", "error", "group must be [[group]] tables", name)]
    seen: dict[str, int] = {}
    for i, g in enumerate(groups):
        where = f"{name} [[group]] {i + 1}" + (f" ({g.get('name')})" if isinstance(g, dict) and g.get("name") else "")
        if not isinstance(g, dict):
            found.append(Finding("group", "error", "isn't a table", where))
            continue
        found += group(root, g, i, where, seen)
    return found


def group(root: Path, g: dict, i: int, where: str, seen: dict[str, int]) -> list[Finding]:
    found = []
    label = g.get("name") or f"group {i + 1}"
    if label in seen:
        found.append(Finding("group", "error", f"the name {label!r} is used twice (groups {seen[label] + 1} "
                                               f"and {i + 1}): --group and the web app can't tell them apart", where))
    seen[label] = i
    for key in sorted(set(g) - config.GROUP_KEYS):
        found.append(Finding("group", "warning", f"unknown key {key} (kept for plugins)", where))
    try:
        config.make_group(g, i)
    except (RuntimeError, TypeError, ValueError, AttributeError) as err:
        found.append(Finding("group", "error", str(err), where))
    match = g.get("match")
    if match is not None:
        if not isinstance(match, dict):
            found.append(Finding("group", "error", "match must be a table", where))
        else:
            for key in sorted(set(match) - MATCH_KEYS):
                found.append(Finding("group", "error", f"match.{key} isn't a match key "
                                                       f"({', '.join(sorted(MATCH_KEYS))})", where))
    ref = g.get("from")
    if ref is not None and not (config.REPO_NAME.match(str(ref)) or config.GITLAB_NAME.match(str(ref))):
        found.append(Finding("group", "error", f"from = {ref!r} isn't owner/name", where))
    for check in config._list(g.get("skip")):
        if check not in config.CHECKS:
            found.append(Finding("group", "warning", f"skip names an unknown check: {check}", where))
    found += [Finding("group", f.level, f.text, where) for f in skip_until(where, g.get("skip_until"))]
    found += folder(root, g.get("rulesets"), "rulesets", where)
    if isinstance(g.get("files"), str):
        found += folder(root, g["files"], "files", where)
    return found


def folder(root: Path, rel, kind: str, where: str) -> list[Finding]:
    if not rel:
        return []
    path = root / str(rel).strip("/")
    if not path.is_dir():
        return [Finding(kind, "error", f"{kind} = {rel!r}: no such folder", where)]
    if kind != "rulesets":
        return []
    found = []
    for f in sorted(path.glob("*.json")):
        found += ruleset_file(str(f.relative_to(root)), f.read_text())
    if not found and not any(path.glob("*.json")):
        found.append(Finding(kind, "warning", f"{rel}/ has no .json files", where))
    return found


def profiles(root: Path) -> list[Finding]:
    book = handbook.Handbook(config.Source(str(root)))
    found = []
    layout = root / "handbook.toml"
    if layout.is_file():
        try:
            raw = config.parse_defaults(layout.read_text(), "handbook.toml")
        except RuntimeError as err:
            return [Finding("handbook", "error", str(err), "handbook.toml")]
        for key in sorted(set(raw) - set(handbook.LAYOUT)):
            found.append(Finding("handbook", "warning", f"unknown key {key}", "handbook.toml"))
        book.layout.update({k: str(v) for k, v in raw.items() if k in handbook.LAYOUT})
    for name in book.profiles():
        rel = book.path("profiles", f"{name}.toml")
        try:
            p = handbook.parse_profile((root / rel).read_text(), rel)
        except RuntimeError as err:
            found.append(Finding("profile", "error", str(err).removeprefix(f"{rel}: "), rel))
            continue
        for key in sorted(set(p["raw"]) - handbook.PROFILE_KEYS):
            found.append(Finding("profile", "warning", f"unknown key {key}", rel))
        for key in sorted(set(p["check"]) - handbook.CHECK_KEYS):
            found.append(Finding("profile", "warning", f"unknown key check.{key}", rel))
        for chapter in p["chapters"]:
            if not (root / chapter).is_file():
                found.append(Finding("profile", "error", f"chapter {chapter} doesn't exist", rel))
        for skill in p["skills"]:
            if not (root / book.path("skills", skill, "SKILL.md")).is_file():
                found.append(Finding("profile", "error", f"skill {skill} has no {book.path('skills', skill)}/SKILL.md",
                                     rel))
    for skill in sorted((root / book.layout["skills"]).glob("*/SKILL.md")):
        head = skill.read_text().split("---")
        if len(head) < 3 or "name:" not in head[1] or "description:" not in head[1]:
            found.append(Finding("skills", "error", "SKILL.md needs front matter with name and description",
                                 str(skill.relative_to(root))))
    if not book.profiles():
        found.append(Finding("handbook", "warning", f"no profiles: {book.layout['profiles']}/<name>.toml "
                                                    "says what a profile needs (see mason's handbook.py)", ""))
    return found


def run(root: Path) -> tuple[list[Finding], list[str]]:
    kinds = []
    found: list[Finding] = []
    if (root / config.DEFAULTS_FILE).is_file():
        kinds.append("defaults repo")
        found += defaults(root)
    if (root / "handbook.toml").is_file() or (root / handbook.LAYOUT["profiles"]).is_dir():
        kinds.append("handbook")
        found += profiles(root)
    return found, kinds


def command(args) -> None:
    root = Path(args.path or ".").resolve()
    found, kinds = run(root)
    if not kinds:
        sys.exit(f"{root} is neither a defaults repo ({config.DEFAULTS_FILE}) nor a handbook (profiles/)")
    errors = [f for f in found if f.level == "error"]
    core.emit({"root": str(root), "kinds": kinds, "errors": len(errors), "warnings": len(found) - len(errors),
               "findings": [asdict(f) for f in found]})
    if not core.json_mode():
        print(f"  {root}: {' and '.join(kinds)}")
        for f in found:
            print(f"{f.level:<8} " + (f"{f.where()}: {f.text}" if f.path else f.text))
        print("ok" if not found else f"{len(errors)} error(s), {len(found) - len(errors)} warning(s)")
    if errors:
        sys.exit(1)
