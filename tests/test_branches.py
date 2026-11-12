"""A repo's branches (mason/branches.py): the list, what protects a branch, and deleting, in the web app, the CLI
and on GitLab."""

from __future__ import annotations

import subprocess
import sys

import pytest
from test_server import H, op  # noqa: F401  (the signed-in web app fixture)

from mason import branches as B


def test_branch_names():
    assert B.valid_name(" feat/search ") == "feat/search"
    for bad in ("", "a b", "../x", "-x", "x/", "x.lock", "a..b", "a:b", "a~1", "x" * 300, None):
        with pytest.raises(ValueError):
            B.valid_name(bad)


def test_rulesets_guard_what_they_name():
    guards = [("main", ["~DEFAULT_BRANCH"], []), ("releases", ["refs/heads/release/*"], ["release/old"]),
              ("all", ["~ALL"], ["refs/heads/dependabot/**"])]
    assert B.guarded_by("trunk", "trunk", guards) == ["ruleset main", "ruleset all"]
    assert B.guarded_by("release/1.x", "main", guards) == ["ruleset releases", "ruleset all"]
    assert B.guarded_by("release/old", "main", guards) == ["ruleset all"]
    assert B.guarded_by("dependabot/pip/x", "main", guards) == []


def test_list_in_the_web_app(op):  # noqa: F811
    _, c = op
    v = c.get("/api/v1/repo/branches?repo=acme/web").json
    assert v["default"] == "main" and v["total"] == 6 and v["url"] == "https://github.com/acme/web/branches"
    rows = {r["name"]: r for r in v["branches"]}
    assert [r["name"] for r in v["branches"]] == ["main", "feat/search", "squashed", "spike", "release/1.x",
                                                  "old-feature"]  # default first, then newest
    assert rows["main"]["default"] and not rows["main"]["deletable"] and not rows["main"]["merged"]
    assert rows["feat/search"]["ahead"] == 2 and rows["feat/search"]["behind"] == 1
    assert rows["feat/search"]["pr"] == {"number": 23, "title": "Add search", "state": "open",
                                         "url": "https://github.com/acme/web/pull/23"}
    assert rows["old-feature"]["merged"] and rows["old-feature"]["ahead"] == 0
    assert rows["squashed"]["merged"] and rows["squashed"]["ahead"] == 3  # squash-merged: its PR says so
    assert not rows["spike"]["merged"] and rows["spike"]["deletable"] and rows["spike"]["author"] == "ann"
    assert rows["release/1.x"]["protected"] == ["branch protection"] and not rows["release/1.x"]["deletable"]
    assert rows["release/1.x"]["url"] == "https://github.com/acme/web/tree/release/1.x"
    # acme/api's ruleset "main" takes in the default branch
    api = c.get("/api/v1/repo/branches?repo=acme/api").json["branches"]
    assert api[0]["name"] == "main" and api[0]["protected"] == ["ruleset main"]
    assert c.get("/api/v1/repo/branches?repo=acme/nope").status_code == 502
    assert c.get("/api/v1/repo/branches?repo=gitlab:g/p").status_code == 409  # GitLab isn't connected


def test_delete_in_the_web_app(op, monkeypatch, tmp_path):  # noqa: F811
    _, c = op
    log = tmp_path / "gh.log"
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    post = lambda **kw: c.post("/api/v1/repo/branches/delete", json={"repo": "acme/web", **kw}, headers=H)  # noqa: E731
    assert post(branches=[]).status_code == 400
    assert post(branches=["a b"]).status_code == 400
    assert post(branches=["x"] * 101).status_code == 400
    r = post(branches=["spike", "main", "release/1.x", "gone", "feat/search"]).json
    assert r["ok"] is False
    assert r["text"].splitlines() == [
        "acme/web: deleted spike", "acme/web: skipped main: it's the default branch",
        "acme/web: skipped release/1.x: protected (branch protection)", "acme/web: skipped gone: no such branch",
        "acme/web: deleted feat/search (its open PR #23 closes)"]
    calls = log.read_text()
    assert "-X DELETE /repos/acme/web/git/refs/heads/spike" in calls
    assert "-X DELETE /repos/acme/web/git/refs/heads/feat/search" in calls
    assert "refs/heads/main" not in calls and "refs/heads/release" not in calls
    # every merged one that may go
    log.write_text("")
    r = post(merged=True).json
    assert r["ok"] and r["text"] == "acme/web: deleted squashed\nacme/web: deleted old-feature"
    # a dry run reads, but deletes nothing
    log.write_text("")
    r = post(branches=["spike"], dry_run=True).json
    assert r["text"] == "acme/web: [dry-run] delete spike" and "-X DELETE" not in log.read_text()
    audit = c.get("/api/v1/audit").json
    assert "branches.delete" in str(audit)


class FakeGitLab:
    def __init__(self):
        self.deleted = []

    def project(self, repo):
        return "/projects/g%2Fp"

    def api(self, method, path, body=None):
        assert path == "/projects/g%2Fp"
        return {"id": 7, "default_branch": "main", "web_url": "https://gitlab.com/g/p"}

    def pages(self, path, limit=2000):
        if path.endswith("/repository/branches"):
            commit = {"id": "abc", "committed_date": "2026-11-01T09:00:00Z", "author_name": "Ann", "title": "Fix"}
            return [{"name": "main", "merged": False, "protected": True, "commit": commit},
                    {"name": "done", "merged": True, "protected": False, "commit": commit},
                    {"name": "wip", "merged": False, "protected": False,
                     "commit": dict(commit, committed_date="2026-11-02T09:00:00Z")},
                    {"name": "stable", "merged": False, "protected": True, "commit": commit}]
        assert "merge_requests?state=all" in path
        return [{"iid": 4, "title": "WIP", "state": "opened", "draft": True, "source_branch": "wip",
                 "source_project_id": 7, "web_url": "https://gitlab.com/g/p/-/merge_requests/4"},
                {"iid": 3, "title": "From a fork", "state": "merged", "source_branch": "stable",
                 "source_project_id": 99}]

    def write(self, method, path, body=None):
        self.deleted.append((method, path))


def test_gitlab_list_and_delete():
    gl = FakeGitLab()
    v = B.listing("gitlab:g/p", gl)
    assert v["url"] == "https://gitlab.com/g/p/-/branches"
    assert [r["name"] for r in v["branches"]] == ["main", "wip", "done", "stable"]
    rows = {r["name"]: r for r in v["branches"]}
    assert rows["done"]["merged"] and rows["done"]["deletable"] and rows["done"]["ahead"] is None
    assert rows["wip"]["pr"]["state"] == "draft" and rows["wip"]["pr"]["number"] == 4
    assert rows["stable"]["protected"] == ["protected branch"] and rows["stable"]["pr"] is None  # a fork's MR
    lines, ok = B.delete("gitlab:g/p", ["wip", "stable"], gl, merged=True, dry=False)
    assert lines == ["deleted wip (its open MR !4 closes)", "skipped stable: protected (protected branch)",
                     "deleted done"] and not ok
    assert gl.deleted == [("DELETE", "/projects/g%2Fp/repository/branches/wip"),
                          ("DELETE", "/projects/g%2Fp/repository/branches/done")]
    with pytest.raises(RuntimeError):
        B.listing("gitlab:g/p", None)


def test_cli(env, tmp_path):
    log = tmp_path / "calls.log"

    def run(*args):
        return subprocess.run([sys.executable, "-m", "mason", "branches", *args], env={**env, "FAKE_GH_LOG": str(log)},
                              capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60, check=False)

    shown = run("acme/web")
    assert shown.returncode == 0, shown.stderr
    lines = shown.stdout.splitlines()
    assert lines[0].split() == ["branch", "state", "commit", "by", "PR"]
    assert lines[2].split()[:2] == ["main", "default"]
    assert "feat/search" in shown.stdout and "+2 -1" in shown.stdout and "#23 open" in shown.stdout
    assert "protected" in shown.stdout
    asked = run("acme/web", "delete", "spike")  # no answer: nothing goes
    assert "left as they are" in asked.stdout and "-X DELETE" not in log.read_text()
    dry = run("acme/web", "delete", "--merged", "--dry-run")
    assert "acme/web: [dry-run] delete old-feature" in dry.stdout and "-X DELETE" not in log.read_text()
    gone = run("acme/web", "delete", "spike", "main", "--yes")
    assert "acme/web: deleted spike" in gone.stdout and "skipped main" in gone.stdout and gone.returncode == 1
    assert "-X DELETE /repos/acme/web/git/refs/heads/spike" in log.read_text()
    assert run("acme/web", "remove", "x").returncode != 0
