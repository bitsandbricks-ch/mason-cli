"""The handbook against GitHub (tests/fake_gh): doctor and sync with a profile's skills, mason adopt."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from mason import handbook


def mason(env, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "mason", *args], env=env, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=60, check=False)


@pytest.fixture
def setup(env, tmp_path):
    book = tmp_path / "handbook"
    for path, text in {
        "core/principles.md": "# Principles\n",
        "profiles/web-app.toml": 'description = "A web app"\nfiles = ["AGENTS.md", "LICENSE"]\n'
                                 'labels = ["type:bug"]\nskills = ["release"]\n',
        "skills/release/SKILL.md": "---\nname: release\ndescription: Release it.\n---\nUse mason bump.\n",
        "templates/AGENTS.md": "# Rules for coding agents\n\n<app> follows the handbook, profile **<profile>**.\n",
    }.items():
        (book / path).parent.mkdir(parents=True, exist_ok=True)
        (book / path).write_text(text)
    defaults = tmp_path / "defaults"
    defaults.mkdir()
    (defaults / "mason.toml").write_text(f'orgs = ["acme"]\nhandbook = "{book}"\n'
                                         '[[group]]\nname = "apps"\nhandbook = { profile = "web-app" }\n')
    return {**env, "MASON_DEFAULTS": str(defaults), "FAKE_GH_LOG": str(tmp_path / "calls.log")}, book


def test_doctor_and_sync_follow_the_profile(setup):
    env, _ = setup
    out = mason(env, "doctor", "web").stdout
    assert "(group apps)" in out and "label type:bug is missing" in out and "LICENSE is missing" in out
    assert ".claude/skills/release/SKILL.md is missing" in out and ".claude/skills/skills-lock.json is missing" in out
    out = mason(env, "sync", "--dry-run", "web").stdout
    assert "add .claude/skills/release/SKILL.md" in out and "add .claude/skills/skills-lock.json" in out


def test_handbook_of_a_repo(setup):
    env, book = setup
    doc = json.loads(mason(env, "--json", "handbook", "web").stdout)["result"]
    assert doc["handbook"] == str(book) and doc["said"] == "the defaults" and doc["profile"] == "web-app"
    assert [c["title"] for c in doc["chapters"]] == ["Principles"]


def test_adopt(setup):
    env, book = setup
    proc = mason(env, "--json", "adopt", "--dry-run", "web", "--version", "v1")
    doc = json.loads(proc.stdout)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    got = doc["result"][0]
    assert got["files"] == [".claude/skills/release/SKILL.md", ".claude/skills/skills-lock.json", ".mason.toml",
                            "AGENTS.md", "CLAUDE.md"]
    assert got["missing"] == ["LICENSE"] and got["profile"] == "web-app" and got["version"] == "v1"
    proc = mason(env, "adopt", "--dry-run", "web", "--profile", "nope")
    assert proc.returncode == 1 and "has no profile 'nope' (profiles: web-app)" in proc.stdout


def test_with_table():
    table = handbook.handbook_table("acme/handbook", "web-app", "v1")
    assert handbook.with_table(None, table).endswith('[handbook]\nrepo = "acme/handbook"\nprofile = "web-app"\n'
                                                     'version = "v1"\n')
    old = ('handbook = "old/one"\ncode_scanning = false\n\n[handbook]\nprofile = "api-only"\n\n'
           '[release]\nversion = "x"\n')
    new = handbook.with_table(old, table)
    assert new == ('code_scanning = false\n\n[release]\nversion = "x"\n\n' + table)


def test_agents_text(tmp_path):
    book = handbook.Handbook(handbook.config.Source(str(tmp_path)))
    found = handbook.Spec("acme/handbook", None, "web-app")
    text = handbook.agents_text(book, found, "acme/web", "# Rules\n\nBe nice.\n")
    assert text == ("# Rules\n\nThis repo follows the handbook https://github.com/acme/handbook, profile **web-app** "
                    "(see `.mason.toml`).\n\nBe nice.\n")
    assert handbook.agents_text(book, found, "acme/web", "see acme/handbook") is None
    assert "TODO" in handbook.agents_text(book, found, "acme/web", None)  # no template: a short starter


def test_skill_lock_is_stable(tmp_path):
    book = handbook.Handbook(handbook.config.Source(str(tmp_path)))
    (tmp_path / "skills/a").mkdir(parents=True)
    (tmp_path / "skills/a/SKILL.md").write_text("x")
    one = handbook.skill_repo_files(book, ["a"])
    assert one == handbook.skill_repo_files(book, ["a"])
    lock = json.loads(one[handbook.LOCK])
    assert lock["skills"]["a"]["computedHash"] == handbook.skill_hash({"SKILL.md": "x"})
    assert lock["skills"]["a"]["sourceType"] == "local"
