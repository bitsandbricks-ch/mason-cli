"""Who a pull or merge request asks for a review: the web app's "to review" filter reads it."""

import sys

import pytest

pytest.importorskip("flask")
if sys.version_info < (3, 10):  # pragma: no cover
    pytest.skip("the operator needs Python 3.10+", allow_module_level=True)

from mason.server import gitlab as GL  # noqa: E402
from mason.server.api.repos import requested  # noqa: E402


def test_github_people_only():
    pr = {"reviewRequests": {"nodes": [{"requestedReviewer": {"login": "mike"}}, {"requestedReviewer": {}},
                                       {"requestedReviewer": None}, None]}}
    assert requested(pr) == ["mike"]
    assert requested({}) == []


def test_gitlab_reviewers(monkeypatch):
    mr = {"iid": "3", "title": "t", "webUrl": "https://gitlab.example.com/g/p/-/merge_requests/3",
          "author": {"username": "ann"}, "reviewers": {"nodes": [{"username": "mike"}, {}, None]}}
    monkeypatch.setattr(GL, "nodes", lambda gl, repos: {"gitlab:g/p": {"mergeRequests": {"nodes": [mr]}}})
    rows = GL.mr_rows(None, ["gitlab:g/p"])
    assert rows[0]["requested"] == ["mike"] and rows[0]["author"] == "ann"
    mr.pop("reviewers")
    assert GL.mr_rows(None, ["gitlab:g/p"])[0]["requested"] == []
