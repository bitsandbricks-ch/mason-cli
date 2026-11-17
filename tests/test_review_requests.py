"""Who a GitLab merge request asks for a review: the web app's "to review" filter reads it, like GitHub's."""

from mason import gitlab as GL


def test_gitlab_reviewers(monkeypatch):
    mr = {"iid": "3", "title": "t", "webUrl": "https://gitlab.example.com/g/p/-/merge_requests/3",
          "author": {"username": "ann"}, "reviewers": {"nodes": [{"username": "mike"}, {}, None]}}
    monkeypatch.setattr(GL, "nodes", lambda gl, repos: {"gitlab:g/p": {"mergeRequests": {"nodes": [mr]}}})
    rows = GL.mr_rows(None, ["gitlab:g/p"])
    assert rows[0]["reviewers"] == ["mike"] and rows[0]["author"] == "ann"
    mr.pop("reviewers")
    assert GL.mr_rows(None, ["gitlab:g/p"])[0]["reviewers"] == []
