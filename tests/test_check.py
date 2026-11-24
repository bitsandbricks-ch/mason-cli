"""mason check (a checkout, offline), mason lint (a defaults repo or a handbook) and mason handbook."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PINNED = "actions/checkout@08eba0b27e820071cde6df949e0beb9ba4906955 # v4.3.0"


def mason(env, *args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "mason", *args], env=env, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=60, check=False, cwd=cwd)


def write(root: Path, files: dict[str, str]) -> None:
    for path, text in files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                   check=True, capture_output=True)


@pytest.fixture
def book(tmp_path) -> Path:
    root = tmp_path / "handbook"
    write(root, {
        "core/principles.md": "# Principles\n",
        "core/README.md": "# Core\n",
        "blocks/api.md": "# API\n",
        "profiles/web-app.toml": 'description = "A web app"\nchapters = ["blocks/api.md"]\n'
                                 'files = ["AGENTS.md", "LICENSE", "CHANGELOG.md|changelog.d"]\n'
                                 'labels = ["type:bug"]\nskills = ["release"]\n'
                                 '[check]\nfragments = "changelog.d"\n',
        "skills/release/SKILL.md": "---\nname: release\ndescription: Release it.\n---\nUse mason bump.\n",
        "templates/AGENTS.md": "# Rules for coding agents\n\n<app> follows the handbook, profile **<profile>**.\n",
    })
    return root


@pytest.fixture
def repo(tmp_path, book) -> Path:
    root = tmp_path / "web"
    write(root, {
        ".mason.toml": f'[handbook]\nrepo = "{book}"\nprofile = "web-app"\nversion = "v1"\n',
        "AGENTS.md": "Follows the handbook.\n",
        "LICENSE": "MIT\n",
        "changelog.d/README.md": "fragments\n",
        ".github/workflows/ci.yml": f"on: push\npermissions:\n  contents: read\njobs:\n  t:\n"
                                   f"    runs-on: ubuntu-latest\n    steps:\n      - uses: {PINNED}\n",
        ".github/rulesets/main.json": json.dumps({"name": "main", "target": "branch", "enforcement": "active",
                                                 "rules": [{"type": "deletion"}]}),
    })
    git(root, "init", "-q", "-b", "main")
    git(root, "remote", "add", "origin", "git@github.com:acme/web.git")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    return root


def findings(env, root, *args):
    proc = mason(env, "--json", "check", *args, cwd=root)
    doc = json.loads(proc.stdout)
    return proc.returncode, {(f["check"], f["text"].split(":")[0]) for f in doc["result"]["findings"]}, doc


def test_a_clean_checkout(env, repo):
    proc = mason(env, "check", cwd=repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "profile web-app" in proc.stdout and proc.stdout.rstrip().endswith(("ok", "warning(s)"))


def test_what_check_finds(env, repo):
    write(repo, {
        ".mason.toml": 'colour = "red"\nskip_until = { pages = 2001-01-01 }\n' + (repo / ".mason.toml").read_text(),
        ".github/workflows/ci.yml": "on: push\njobs:\n  t:\n    steps:\n      - uses: actions/checkout@v4\n"
                                    "      - run: echo ${{ github.event.pull_request.title }}\n",
        ".mason/rulesets/broken.json": "{",
        ".github/rulesets/odd.json": json.dumps({"name": "odd", "target": "branches", "rules": [{}]}),
    })
    (repo / "LICENSE").unlink()
    (repo / "AGENTS.md").write_text("No link here.\n")
    code, got, _ = findings(env, repo)
    assert code == 1
    assert ("mason_toml", "unknown key colour") in got
    assert ("mason_toml", "the exception for pages ran out on 2001-01-01") in got
    assert ("workflows", "actions/checkout@v4 isn't pinned to a commit") in got
    assert ("workflows", "no top-level permissions") in got
    assert ("rulesets", "isn't valid JSON") in got
    assert ("rulesets", "target 'branches' isn't one of branch, tag, push, repository") in got
    assert ("required_files", "missing") in got  # LICENSE, from the profile
    assert ("handbook", "doesn't link the handbook") not in got  # a folder handbook isn't a link


def test_changelog_fragment_on_a_branch(env, repo):
    git(repo, "checkout", "-q", "-b", "feat")
    write(repo, {"app.py": "print('hi')\n"})
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "feat")
    code, got, _ = findings(env, repo)
    assert code == 1 and ("changelog", "this branch adds no changelog fragment to changelog.d/ (changes since "
                                       "origin/main") in got
    write(repo, {"changelog.d/hi.md": "Say hi.\n"})
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "fragment")
    code, got, _ = findings(env, repo)
    assert not any(c == "changelog" for c, _ in got)


def test_two_migration_heads(env, repo):
    versions = "backend/migrations/versions"
    write(repo, {
        "backend/migrations/env.py": "",
        f"{versions}/a.py": 'revision = "a"\ndown_revision = None\n',
        f"{versions}/b.py": 'revision = "b"\ndown_revision = "a"\n',
        f"{versions}/c.py": 'revision: str = "c"\ndown_revision = "a"\n',
    })
    code, got, doc = findings(env, repo)
    assert code == 1 and ("migrations", "2 heads") in got
    write(repo, {f"{versions}/d.py": 'revision = "d"\ndown_revision = ("b", "c")\n'})
    code, got, _ = findings(env, repo)
    assert not any(c == "migrations" for c, _ in got)


def test_handbook_link_and_skills_lock(env, repo, book):
    from mason import handbook
    write(repo, {".mason.toml": '[handbook]\nrepo = "acme/handbook"\nprofile = "web-app"\n'})
    code, got, doc = findings(env, repo, "--handbook", str(book))
    assert ("handbook", "doesn't link the handbook acme/handbook (said by .mason.toml)") in got
    assert ("skills", "the profile's skills aren't synced (release)") in got
    skill = {"SKILL.md": (book / "skills/release/SKILL.md").read_text()}
    lock = {"version": 1, "skills": {"release": {"files": ["SKILL.md"], "computedHash": handbook.skill_hash(skill)}}}
    write(repo, {"AGENTS.md": "See https://github.com/acme/handbook.\n",
                 ".claude/skills/release/SKILL.md": skill["SKILL.md"], handbook.LOCK: json.dumps(lock)})
    code, got, _ = findings(env, repo, "--handbook", str(book))
    assert not any(c in ("handbook", "skills") for c, _ in got)
    write(repo, {".claude/skills/release/SKILL.md": "edited by hand\n"})
    code, got, _ = findings(env, repo, "--handbook", str(book))
    assert code == 1 and ("skills", "differs from the lock") in got


def test_profile_not_cached(env, repo):
    write(repo, {".mason.toml": '[handbook]\nrepo = "acme/handbook"\nprofile = "web-app"\n',
                 "AGENTS.md": "acme/handbook\n"})
    proc = mason(env, "check", cwd=repo)
    assert "isn't cached: run `mason handbook` once online" in proc.stdout


def test_install_hook(env, repo):
    proc = mason(env, "check", "--install-hook", cwd=repo)
    hook = repo / ".git/hooks/pre-push"
    assert proc.returncode == 0 and "exec mason check" in hook.read_text()


def test_lint_a_defaults_repo(env, tmp_path):
    root = tmp_path / "defaults"
    write(root, {
        "mason.toml": 'orgs = ["acme"]\nhandbook = "acme/handbook"\nfavourite = 1\n'
                      '[[group]]\nname = "a"\nmatch = { org = "acme", colour = "red" }\nrulesets = "rulesets/a"\n'
                      'skip = ["nope"]\nskip_until = { pages = "soon" }\nfrom = "not a repo"\n'
                      '[[group]]\nname = "a"\nfiles = "files/missing"\n',
        "rulesets/a/main.json": json.dumps({"name": "main", "enforcement": "on", "rules": []}),
    })
    proc = mason(env, "--json", "lint", str(root))
    doc = json.loads(proc.stdout)["result"]
    texts = [f["text"] for f in doc["findings"]]
    assert proc.returncode == 1 and doc["kinds"] == ["defaults repo"]
    assert "unknown top-level key favourite (kept for plugins)" in texts
    assert any(t.startswith("match.colour isn't a match key") for t in texts)
    assert "skip names an unknown check: nope" in texts
    assert "skip_until.pages: not a date: 'soon'" in texts
    assert "from = 'not a repo' isn't owner/name" in texts
    assert any("used twice" in t for t in texts)
    assert "files = 'files/missing': no such folder" in texts
    assert "enforcement 'on' isn't one of active, evaluate, disabled" in texts


def test_lint_a_handbook(env, book):
    assert mason(env, "lint", str(book)).returncode == 0
    write(book, {"profiles/api.toml": 'chapters = ["blocks/nope.md"]\nskills = ["ghost"]\nextra = 1\n',
                 "skills/bare/SKILL.md": "no front matter\n"})
    out = mason(env, "lint", str(book)).stdout
    assert "chapter blocks/nope.md doesn't exist" in out and "skill ghost has no skills/ghost/SKILL.md" in out
    assert "unknown key extra" in out and "SKILL.md needs front matter" in out


def test_handbook_command(env, repo, book, tmp_path):
    cache = {**env, "XDG_CACHE_HOME": str(tmp_path / "cache")}
    proc = mason(cache, "handbook", cwd=repo)
    assert "profile   web-app: A web app" in proc.stdout, proc.stdout + proc.stderr
    assert "Principles" in proc.stdout and "API" in proc.stdout and "Core" not in proc.stdout
    assert "LICENSE" in proc.stdout and "type:bug" in proc.stdout and "release" in proc.stdout
    doc = json.loads(mason(cache, "--json", "handbook", "--profiles", cwd=repo).stdout)["result"]
    assert doc["profiles"] == ["web-app"]
    # the profile is cached now: a repo naming a remote handbook checks offline
    assert list((tmp_path / "cache" / "mason" / "handbook").glob("*/web-app.json"))


def test_doctor_holds_a_repo_to_its_profile(book):
    from mason import rules
    want = rules.prepare({"more": {"handbook": {"repo": str(book), "profile": "web-app"}},
                          "labels": {"type:bug": {"color": "d73a4a"}}, "required_files": ["README.md"]})
    assert want["required_files"] == ["README.md", "AGENTS.md", "LICENSE", "CHANGELOG.md|changelog.d"]
    assert want["labels"] == {"type:bug": {"color": "d73a4a"}}  # the group's own spec wins
    want = rules.prepare({"more": {"handbook": {"repo": str(book), "profile": "nope"}}})
    assert any("has no profile 'nope'" in t for t in want["expired_skips"])
