"""No names inside a checkout: its repo (read from the origin remote). And --json on any command."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from mason import here


def mason(env, *args, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "mason", *args], env=env, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=60, check=False, cwd=cwd)


@pytest.fixture
def checkout(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "remote", "add", "origin", "git@github.com:acme/web.git"], check=True)
    return tmp_path


@pytest.mark.parametrize("url,repo", [
    ("git@github.com:acme/web.git", "acme/web"),
    ("https://github.com/acme/web", "acme/web"),
    ("ssh://git@github.com/acme/web.git", "acme/web"),
    ("git@github.com-work:acme/web.git", "acme/web"),  # an ssh host alias
    ("https://gitlab.com/grp/sub/proj.git", "gitlab:grp/sub/proj"),
    ("git@gitlab.example.com:grp/proj.git", "gitlab:grp/proj"),
    ("https://example.com/a/b", None),
    ("https://github.com/only-owner", None),
])
def test_parse_remote(url, repo):
    assert here.parse_remote(url, {"gitlab.com"}) == repo


def test_no_names_in_a_checkout_is_its_repo(env, checkout):
    mine = {k: v for k, v in env.items() if k != "MASON_HERE"}
    out = mason(mine, "repos", cwd=checkout).stdout
    assert "acme/web" in out and "1 repos" in out
    out = mason(mine, "repos", "--all", cwd=checkout).stdout
    assert "6 repos" in out
    assert "5 repos" in mason(mine, "repos", "--org", "acme", cwd=checkout).stdout  # --org: every repo of it
    assert "acme/web" in mason(env, "repos", ".", cwd=checkout).stdout  # `.` works with MASON_HERE=0 too
    assert "6 repos" in mason(env, "repos", cwd=checkout).stdout
    assert "checkout     acme/web" in mason(mine, "config", cwd=checkout).stdout


def test_pr_number_of_this_checkout(env, checkout):
    out = mason(env, "pr", "#7", cwd=checkout).stdout
    assert "https://github.com/acme/web/pull/7" in out


def test_dot_outside_a_checkout(env, tmp_path):
    proc = mason(env, "repos", ".", cwd=tmp_path)
    assert "Not in a git checkout" in proc.stderr


def test_json_on_any_command(env):
    doc = json.loads(mason(env, "--json", "status").stdout)
    assert doc["command"] == "status" and doc["ok"] is True
    rows = doc["tables"][0]["rows"]
    assert any(r.get("repo") == "acme/api" for r in rows)
    doc = json.loads(mason(env, "repos", "--json").stdout)  # after the command works too
    assert len(doc["result"]) == 6 and {"repo": "acme/web", "group": "default", "alias": "web"} in doc["result"]


def test_json_carries_errors_and_exit_code(env):
    proc = mason(env, "--json", "repos", "nope")
    doc = json.loads(proc.stdout)
    assert proc.returncode == 1 and doc["ok"] is False and "Unknown repo: nope" in doc["error"]


def test_json_per_repo_lines(env):
    doc = json.loads(mason(env, "--json", "doctor", "--dry-run", "plugin-b").stdout)
    assert "acme/plugin-b" in doc["repos"] and doc["repos"]["acme/plugin-b"]
