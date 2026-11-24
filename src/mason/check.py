"""`mason check`: a checkout against its own rules, offline: no token, no API call, fast enough for a pre-push hook.

  .mason.toml        parses, its keys are known, [handbook] and skip_until make sense
  rulesets           .github/rulesets/*.json and .mason/rulesets/*.json are rulesets GitHub takes
  workflows          actions pinned to a commit, permissions set, no script injection (as `mason workflows`)
  required files     the .mason.toml's required_files and the handbook profile's files
  changelog          a branch adds a changelog fragment (when the repo keeps them in a folder)
  migrations         Alembic migrations have one head
  handbook           AGENTS.md links the handbook the repo follows
  skills             .claude/skills match their skills-lock.json (nobody edited a synced skill by hand)

The profile's rules come from the handbook; offline they come from ~/.cache/mason/handbook (`mason handbook`
fills it) or from a handbook folder (`--handbook ../handbook`, handy in CI). In the repo's .mason.toml:

  [check]
  fragments = "changelog.d"      # where changelog fragments go (found on its own: changelog.d, .changes, ...)
  migrations = "app/migrations/versions"   # Alembic versions folder(s); false: don't look
  skip = ["changelog"]           # checks to leave out
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from mason import config, core, handbook, here, workflows
from mason.defaults import RULESET_DIRS, has

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

CHECKS = ("mason_toml", "rulesets", "workflows", "required_files", "changelog", "migrations", "handbook", "skills")
FRAGMENT_DIRS = ("changelog.d", ".changes", "changes", "newsfragments", ".changeset", "changelog/unreleased")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".tox"}
REPO_FILE_KEYS = config.REPO_KEYS | {"release", "handbook", "check"}
RULESET_TARGETS = ("branch", "tag", "push", "repository")
ENFORCEMENT = ("active", "evaluate", "disabled")
HOOK = "#!/bin/sh\n# mason check: the repo's own rules, offline (remove this file to stop it)\nexec mason check\n"


@dataclass
class Finding:
    check: str
    level: str  # error | warning
    text: str
    path: str = ""
    line: int = 0

    def where(self) -> str:
        return f"{self.path}:{self.line}" if self.line else self.path


# ── the pieces ───────────────────────────────────────────────────────────────


def read_own(root: Path) -> tuple[str, dict, list[Finding]]:
    """(path, parsed .mason.toml or {}, findings)."""
    path, text = config.repo_file(lambda p: (root / p).read_text() if (root / p).is_file() else None, "")
    if text is None:
        return path, {}, []
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as err:
        return path, {}, [Finding("mason_toml", "error", f"isn't valid TOML: {err}", path)]
    return path, raw, mason_toml(path, raw)


def mason_toml(path: str, raw: dict) -> list[Finding]:
    found = []
    for key in sorted(set(raw) - REPO_FILE_KEYS):
        why = " (a group key: it goes in the defaults' mason.toml)" if key in config.GROUP_KEYS else ""
        found.append(Finding("mason_toml", "warning", f"unknown key {key}{why}", path))
    try:
        config.make_group({k: v for k, v in raw.items() if k in config.REPO_KEYS}, 0)
    except (RuntimeError, TypeError, ValueError, AttributeError) as err:
        found.append(Finding("mason_toml", "error", str(err), path))
    table = raw.get("handbook")
    if table is not None and not isinstance(table, (dict, str)):
        found.append(Finding("mason_toml", "error", "[handbook] must be a table", path))
    elif isinstance(table, dict):
        for key in sorted(set(table) - handbook.TABLE_KEYS):
            found.append(Finding("mason_toml", "warning", f"unknown key handbook.{key}", path))
        for key in handbook.TABLE_KEYS & set(table):
            if not isinstance(table[key], str):
                found.append(Finding("mason_toml", "error", f"handbook.{key} must be a string", path))
    found += skip_until(path, raw.get("skip_until"))
    for name in config._list(raw.get("skip")):
        if name not in config.CHECKS:
            found.append(Finding("mason_toml", "warning", f"skip names an unknown check: {name}", path))
    return found


def skip_until(path: str, table) -> list[Finding]:
    """skip_until = { check = 2027-01-01 } or { check = { until = 2027-01-01, reason = "..." } }."""
    if table is None:
        return []
    if not isinstance(table, dict):
        return [Finding("mason_toml", "error", "skip_until must be a table {check = date}", path)]
    found = []
    today = dt.date.today()
    for check, value in table.items():
        if check not in config.CHECKS:
            found.append(Finding("mason_toml", "warning", f"skip_until names an unknown check: {check}", path))
        until = value.get("until") if isinstance(value, dict) else value
        try:
            day = until if isinstance(until, dt.date) else dt.date.fromisoformat(str(until)[:10])
        except ValueError:
            found.append(Finding("mason_toml", "error", f"skip_until.{check}: not a date: {until!r}", path))
            continue
        if day < today:
            found.append(Finding("mason_toml", "warning", f"the exception for {check} ran out on {day}: it's "
                                                          "checked again (remove it, or give a new date)", path))
    return found


def ruleset_problems(rs) -> list[str]:
    """What GitHub would refuse in a ruleset file (or doctor couldn't compare)."""
    if not isinstance(rs, dict):
        return ["isn't a JSON object"]
    out = []
    if not rs.get("name"):
        out.append("has no name")
    if rs.get("target", "branch") not in RULESET_TARGETS:
        out.append(f"target {rs.get('target')!r} isn't one of {', '.join(RULESET_TARGETS)}")
    if rs.get("enforcement", "active") not in ENFORCEMENT:
        out.append(f"enforcement {rs.get('enforcement')!r} isn't one of {', '.join(ENFORCEMENT)}")
    rules = rs.get("rules")
    if not isinstance(rules, list):
        out.append("has no rules list")
    else:
        for i, rule in enumerate(rules):
            if not isinstance(rule, dict) or not rule.get("type"):
                out.append(f"rule {i + 1} has no type")
    conditions = rs.get("conditions")
    if conditions is not None and not isinstance(conditions, dict):
        out.append("conditions must be an object")
    return out


def ruleset_file(path: str, text: str, check: str = "rulesets") -> list[Finding]:
    try:
        rs = json.loads(text)
    except ValueError as err:
        return [Finding(check, "error", f"isn't valid JSON: {err}", path)]
    return [Finding(check, "error", p, path) for p in ruleset_problems(rs)]


def rulesets(root: Path) -> list[Finding]:
    found, names = [], {}
    for folder in RULESET_DIRS:
        for f in sorted((root / folder).glob("*.json")):
            rel = f"{folder}/{f.name}"
            text = f.read_text()
            found += ruleset_file(rel, text)
            try:
                name = json.loads(text).get("name")
            except (ValueError, AttributeError):
                continue
            if name and names.get(name, (None,))[0] == folder:
                found.append(Finding("rulesets", "error", f"two files name the ruleset {name!r}: "
                                                          f"{names[name][1]} and {rel}", rel))
            names[name] = (folder, rel)
    return found


def workflow_findings(root: Path, raw: dict) -> list[Finding]:
    want = workflows.settings(raw.get("workflows", True))
    if not want:
        return []
    found = []
    for f in sorted([*(root / ".github/workflows").glob("*.yml"), *(root / ".github/workflows").glob("*.yaml")]):
        rel = f".github/workflows/{f.name}"
        for w in workflows.scan(rel, f.read_text(), want):
            found.append(Finding("workflows", "error", w["text"], rel, w["line"]))
    return found


def paths(root: Path) -> set[str]:
    """Every file of the checkout (tracked or new, not ignored) and every folder above one."""
    listed = here.git("ls-files", "--cached", "--others", "--exclude-standard", cwd=root)
    if listed is None:
        files = []
        for dirpath, dirnames, names in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            files += [str((Path(dirpath) / n).relative_to(root)) for n in names]
    else:
        files = [f for f in listed.splitlines() if (root / f).exists()]  # deleted but not committed: gone
    out = set(files)
    for f in files:
        parts = f.split("/")[:-1]
        out |= {"/".join(parts[:i]) for i in range(1, len(parts) + 1)}
    return out


def required(root: Path, raw: dict, profile: dict | None) -> list[Finding]:
    needs = list(dict.fromkeys(config._list(raw.get("required_files")) + list((profile or {}).get("files") or [])))
    ours = paths(root)
    return [Finding("required_files", "error", f"missing (one of): {need}" if "|" in need else "missing", need)
            for need in needs if not has(ours, need)]


def base_ref(root: Path, base: str | None) -> str | None:
    if base:
        return base if here.git("rev-parse", "--verify", "-q", base, cwd=root) else None
    head = here.git("symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD", cwd=root)
    for ref in (head, "origin/main", "origin/master", "main", "master"):
        if ref and here.git("rev-parse", "--verify", "-q", ref, cwd=root):
            return ref
    return None


def changelog(root: Path, raw: dict, profile: dict | None, base: str | None) -> list[Finding]:
    """On a branch: at least one new file in the fragments folder since it left the base branch."""
    setting = (raw.get("check") or {}).get("fragments", ((profile or {}).get("check") or {}).get("fragments"))
    if setting is False:
        return []
    folder = setting if isinstance(setting, str) else next((d for d in FRAGMENT_DIRS if (root / d).is_dir()), None)
    if not folder:
        return []
    ref = base_ref(root, base)
    branch = here.git("rev-parse", "--abbrev-ref", "HEAD", cwd=root) or ""
    if not ref:
        return [Finding("changelog", "warning", "no base branch to compare with (fetch it, or pass --base)", folder)]
    if branch in ("HEAD", ref, ref.split("/", 1)[-1]):  # the base branch itself, or a detached release checkout
        return []
    changed = (here.git("diff", "--name-only", "--diff-filter=AM", f"{ref}...HEAD", cwd=root) or "").splitlines()
    if not changed:
        return []
    if any(p.startswith(folder.rstrip("/") + "/") and not p.endswith(("README.md", ".gitkeep")) for p in changed):
        return []
    return [Finding("changelog", "error", f"this branch adds no changelog fragment to {folder}/ "
                                          f"(changes since {ref}: {len(changed)} files)", folder)]


def _revision(tree: ast.Module, name: str):
    for node in tree.body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) \
            else []
        if any(isinstance(t, ast.Name) and t.id == name for t in targets) and node.value is not None:
            try:
                return ast.literal_eval(node.value)
            except ValueError:
                return None
    return None


def migration_dirs(root: Path, setting) -> list[Path]:
    if setting is False:
        return []
    if isinstance(setting, (str, list)):
        return [root / p for p in config._list(setting)]
    out = []
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        p = Path(dirpath)
        if p.name == "versions" and (p.parent / "env.py").is_file():
            out.append(p)
    return out


def migrations(root: Path, raw: dict, profile: dict | None) -> list[Finding]:
    """Alembic: every revision but the newest is some other's down_revision; two heads mean two branches
    added migrations in parallel and need a merge migration (`alembic merge heads`)."""
    setting = (raw.get("check") or {}).get("migrations", ((profile or {}).get("check") or {}).get("migrations"))
    found = []
    for folder in migration_dirs(root, setting):
        rel = str(folder.relative_to(root))
        if not folder.is_dir():
            found.append(Finding("migrations", "error", "no such folder", rel))
            continue
        revs, downs = {}, set()
        for f in sorted(folder.glob("*.py")):
            try:
                tree = ast.parse(f.read_text())
            except SyntaxError as err:
                found.append(Finding("migrations", "error", f"doesn't parse: {err.msg}", f"{rel}/{f.name}", err.lineno))
                continue
            rev = _revision(tree, "revision")
            if not rev:
                continue
            revs[str(rev)] = f.name
            down = _revision(tree, "down_revision")
            downs |= {str(d) for d in (down if isinstance(down, (list, tuple)) else [down]) if d}
        heads = sorted(set(revs) - downs)
        if len(heads) > 1:
            found.append(Finding("migrations", "error", f"{len(heads)} heads: " + ", ".join(
                f"{h} ({revs[h]})" for h in heads) + ": add a merge migration (alembic merge heads)", rel))
        for missing in sorted(downs - set(revs)):
            found.append(Finding("migrations", "warning", f"down_revision {missing} isn't in the folder", rel))
    return found


def handbook_link(root: Path, found: handbook.Spec) -> list[Finding]:
    if not found or config._is_local(found.where or ""):
        return []
    agents = root / "AGENTS.md"
    if not agents.is_file():
        return [Finding("handbook", "error", f"missing: it links the handbook ({found.where})", "AGENTS.md")]
    text = agents.read_text()
    name = found.where.removeprefix("gitlab:")
    if name not in text:
        return [Finding("handbook", "error", f"doesn't link the handbook {found.where} "
                                             f"(said by {found.said})", "AGENTS.md")]
    return []


def skills(root: Path, profile: dict | None) -> list[Finding]:
    lock_path = root / handbook.LOCK
    wanted = list((profile or {}).get("skills") or [])
    if not lock_path.is_file():
        if wanted:
            return [Finding("skills", "warning", f"the profile's skills aren't synced ({', '.join(wanted)}): "
                                                 "mason sync", handbook.LOCK)]
        return []
    try:
        lock = json.loads(lock_path.read_text())
        entries = dict(lock.get("skills") or {})
    except (ValueError, AttributeError):
        return [Finding("skills", "error", "isn't valid JSON", handbook.LOCK)]
    found = []
    for name, entry in sorted(entries.items()):
        folder = root / handbook.SKILLS_DIR / name
        if not folder.is_dir():
            found.append(Finding("skills", "error", "missing (it is in the lock)", f"{handbook.SKILLS_DIR}/{name}"))
            continue
        if "files" not in entry:
            continue  # someone else's lock entry (npx skills and the like): their tool checks it
        files = {str(p.relative_to(folder)): p.read_text() for p in sorted(folder.rglob("*")) if p.is_file()}
        if handbook.skill_hash(files) != entry.get("computedHash"):
            found.append(Finding("skills", "error", "differs from the lock: change it in the handbook, not here "
                                                    "(mason sync brings it back)", f"{handbook.SKILLS_DIR}/{name}"))
    for name in wanted:
        if name not in entries:
            found.append(Finding("skills", "warning", f"the profile wants the skill {name}: mason sync",
                                 handbook.LOCK))
    return found


# ── the command ──────────────────────────────────────────────────────────────


def run(root: Path, handbook_folder: str | None = None, base: str | None = None,
        only: list[str] | None = None) -> tuple[list[Finding], list[str]]:
    """(findings, notes) for the checkout at `root`."""
    notes: list[str] = []
    path, raw, found = read_own(root)
    skipped = set(config._list((raw.get("check") or {}).get("skip")))
    spec = handbook.spec(raw)
    profile = None
    if spec:
        notes.append(f"handbook {spec.where}" + (f" {spec.version}" if spec.version else "")
                     + (f", profile {spec.profile}" if spec.profile else "") + f" (from {spec.said})")
        try:
            profile, whence = handbook.profile_offline(spec, handbook_folder)
            notes.append(f"profile rules from {whence}" if profile else whence)
        except RuntimeError as err:
            found.append(Finding("handbook", "error", str(err), path))
        skipped |= set(config._list(((profile or {}).get("check") or {}).get("skip")))
    else:
        notes.append("no handbook (set one in .mason.toml [handbook] repo, or handbook = in your config)")
    found += rulesets(root)
    found += workflow_findings(root, raw)
    found += required(root, raw, profile)
    found += changelog(root, raw, profile, base)
    found += migrations(root, raw, profile)
    found += handbook_link(root, spec)
    found += skills(root, profile)
    keep = [f for f in found if f.check not in skipped and (not only or f.check in only)]
    return keep, notes


def install_hook(root: Path) -> str:
    hooks = here.git("rev-parse", "--git-path", "hooks", cwd=root)
    path = (root / hooks if hooks and not os.path.isabs(hooks) else Path(hooks or root / ".git/hooks")) / "pre-push"
    if path.exists() and "mason check" not in path.read_text():
        raise RuntimeError(f"{path} exists and isn't mason's: add `mason check` to it yourself")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HOOK)
    path.chmod(0o755)
    return str(path)


def command(args) -> None:
    root = here.root(args.path) if args.path else here.root()
    if root is None:
        root = Path(args.path or ".").resolve()
        if not (root / config.REPO_LAYER).is_file() and not (root / ".github").is_dir():
            sys.exit("Not in a git checkout: cd into one, or name its folder: mason check PATH")
    if args.install_hook:
        path = install_hook(root)
        core.emit({"hook": path})
        if not core.json_mode():
            print(f"wrote {path}: git push runs mason check first (git push --no-verify skips it)")
        return
    for name in args.only or []:
        if name not in CHECKS:
            sys.exit(f"Unknown check {name}. Checks: {', '.join(CHECKS)}")
    found, notes = run(root, args.handbook, args.base, args.only)
    errors = [f for f in found if f.level == "error"]
    core.emit({"root": str(root), "notes": notes, "errors": len(errors),
               "warnings": len(found) - len(errors), "findings": [asdict(f) for f in found]})
    if not core.json_mode():
        for n in notes:
            print(f"  {n}")
        for f in found:
            print(f"{f.level:<8} {f.check:<15} " + (f"{f.where()}: {f.text}" if f.path else f.text))
        print("ok" if not found else f"{len(errors)} error(s), {len(found) - len(errors)} warning(s)")
    if errors:
        sys.exit(1)
