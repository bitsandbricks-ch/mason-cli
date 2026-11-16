"""Auto-merge when GitHub has nothing to wait for (no required checks on the base branch)."""

from __future__ import annotations

import pytest

from mason import core
from mason import repos as R


class Stub:
    """A transport whose enablePullRequestAutoMerge answers with a canned GitHub error."""

    def __init__(self, auto_error: str = "", allowed: bool = True, admin: bool = True, now_error: str = ""):
        self.auto_error, self.allowed, self.admin, self.now_error = auto_error, allowed, admin, now_error
        self.calls = []

    def pr_merge(self, repo, number, method="squash", auto=True):
        self.calls.append("auto" if auto else "now")
        if auto and not self.allowed:
            return "Auto merge is not allowed for this repository"
        return self.auto_error if auto else self.now_error

    def api(self, method, path, body=None):
        self.calls.append(f"{method} {path}")
        if method == "PATCH":
            if not self.admin:
                raise RuntimeError("HTTP 403: Must have admin rights to Repository.")
            self.allowed = True
        return {"allow_auto_merge": self.allowed}


@pytest.fixture
def stub(monkeypatch):
    def use(**kw):
        t = Stub(**kw)
        monkeypatch.setattr(core, "transport", lambda: t)
        return t
    return use


def test_auto_merge_on(stub):
    t = stub()
    assert R.auto_merge("acme/web", 7) == (False, "")
    assert t.calls == ["auto"]


def test_clean_pr_merges_now(stub):
    t = stub(auto_error="Pull request Pull request is in clean status")
    assert R.auto_merge("acme/web", 7) == (True, "")
    assert t.calls == ["auto", "now"]


def test_no_required_checks_merges_now(stub):
    t = stub(auto_error="Pull request Pull request is in unstable status")
    assert R.auto_merge("acme/web", 7) == (True, "")
    assert t.calls == ["auto", "now"]


def test_auto_merge_off_and_not_admin_merges_now(stub, capsys):
    t = stub(allowed=False, admin=False)
    assert R.auto_merge("acme/web", 7) == (True, "")
    assert t.calls == ["auto", "GET /repos/acme/web", "PATCH /repos/acme/web", "now"]
    assert "can't turn on auto-merge" in capsys.readouterr().out


def test_protected_branch_blocks_both(stub):
    stub(allowed=False, admin=False, now_error="Required status check \"test\" is expected.")
    merged, why = R.auto_merge("acme/web", 7)
    assert not merged and "not allowed" in why and "Required status check" in why


def test_merge_word():
    assert R.merge_word({"isDraft": False, "mergeStateStatus": "CLEAN"}) == "mergeable"
    assert R.merge_word({"isDraft": False, "mergeStateStatus": "BLOCKED"}) == "blocked"
    assert R.merge_word({"isDraft": False, "mergeable": "CONFLICTING", "mergeStateStatus": "DIRTY"}) == "conflicts"
    assert R.merge_word({"isDraft": True, "mergeStateStatus": "CLEAN"}) == "draft"
    assert R.merge_word({"isDraft": False}) == "checking"


def test_repo_setting_off_is_turned_on(stub):
    t = stub(allowed=False)
    assert R.auto_merge("acme/web", 7) == (False, "")
    assert t.calls == ["auto", "GET /repos/acme/web", "PATCH /repos/acme/web", "auto"]


def test_merge_one_reports_merged_now(stub, capsys):
    stub(auto_error="Pull request is in clean status")
    p = {"number": 7, "title": "Fix", "url": "https://github.com/acme/web/pull/7", "state": "OPEN",
         "isDraft": False, "mergeable": "MERGEABLE", "autoMergeRequest": None}
    R.merge_one("acme/web", p, {}, named=True)
    assert "merged right away" in capsys.readouterr().out


def test_merged_branch_with_hash_is_deleted_by_its_whole_name(monkeypatch):
    from mason import auto
    calls = []

    def api(method, path, body=None):
        calls.append((method, path))
        if path == "/repos/acme/web":
            return {"default_branch": "main"}
        if "/pulls?state=closed" in path:
            return [{"merged_at": "2020-01-01T00:00:00Z",
                     "head": {"ref": "fix#1", "repo": {"full_name": "acme/web"}}}]
        return []
    monkeypatch.setattr(auto, "api", api)
    monkeypatch.setattr(auto, "open_prs", lambda repo: [])
    auto.delete_branches(None, "acme/web", 14)
    assert ("DELETE", "/repos/acme/web/git/refs/heads/fix%231") in calls  # raw, "#1" would be a fragment: "fix"
