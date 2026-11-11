"""The event logs of the detail pages for GitLab (GitHub's run against tests/fake_gh in test_server.py)."""

from __future__ import annotations

import pytest

from mason import events as E


@pytest.fixture()
def gl():
    from mason.server import gitlab as GL

    answers = {
        "/projects/grp%2Fapp/merge_requests/5": {
            "iid": 5, "title": "Add CI", "draft": True, "author": {"username": "ann"},
            "created_at": "2026-11-01T08:00:00Z", "web_url": "https://gitlab.com/grp/app/-/merge_requests/5",
            "merged_at": "2026-11-02T08:00:00Z", "merged_by": {"username": "mike"}},
        "/projects/grp%2Fapp/merge_requests/5/notes": [
            {"id": 1, "system": True, "body": "marked this merge request as **ready**", "author": {"username": "ann"},
             "created_at": "2026-11-01T09:00:00Z"},
            {"id": 2, "system": True, "body": "enabled an automatic merge when the pipeline for abc succeeds",
             "author": {"username": "mike"}, "created_at": "2026-11-01T10:00:00Z"},
            {"id": 3, "system": False, "body": "Looks good\nship it", "author": {"username": "bob"},
             "created_at": "2026-11-01T11:00:00Z"}],
        "/projects/grp%2Fapp/merge_requests/5/pipelines": [
            {"id": 77, "status": "success", "ref": "ci", "sha": "abcdef12", "created_at": "2026-11-01T09:30:00Z",
             "web_url": "https://gitlab.com/grp/app/-/pipelines/77"}],
        "/projects/grp%2Fapp/events": [
            {"action_name": "pushed to", "author": {"username": "ann"}, "created_at": "2026-11-03T08:00:00Z",
             "push_data": {"commit_count": 3, "ref": "main", "commit_title": "Fix", "commit_to": "f00"}},
            {"action_name": "accepted", "target_type": "MergeRequest", "target_iid": 5, "target_title": "Add CI",
             "author": {"username": "mike"}, "created_at": "2026-11-02T08:00:00Z"}],
        "/projects/grp%2Fapp/pipelines": [],
        "/projects/grp%2Fapp/pipelines/77": {
            "id": 77, "status": "failed", "source": "push", "ref": "main", "sha": "abcdef12",
            "created_at": "2026-11-01T09:00:00Z", "started_at": "2026-11-01T09:00:00Z",
            "finished_at": "2026-11-01T09:02:00Z", "web_url": "https://gitlab.com/grp/app/-/pipelines/77"},
        "/projects/grp%2Fapp/pipelines/77/jobs": [
            {"id": 1, "stage": "test", "name": "unit", "status": "failed", "started_at": "2026-11-01T09:00:00Z",
             "finished_at": "2026-11-01T09:01:10Z", "web_url": "https://gitlab.com/grp/app/-/jobs/1"}],
    }

    class Fake(GL.GitLab):
        def api(self, method, path, body=None):
            return answers.get(path.split("?", 1)[0])

    return Fake("token")


def test_merge_request_events(gl):
    from mason.server import gitlab as GL

    ev = GL.mr_events(gl, "gitlab:grp/app", 5)
    by = {e["what"]: e for e in ev}
    assert ev[0]["what"] == "merged" and ev[0]["who"] == "mike" and ev[0]["source"] == "gitlab"
    assert by["marked this merge request as ready"]["state"] == "ok"
    assert by["enabled an automatic merge when the pipeline for abc succeeds"]["state"] == "ok"
    assert by["commented"]["detail"] == "Looks good" and "ship it" in by["commented"]["more"]
    assert by["pipeline #77: success"]["state"] == "ok" and by["opened as a draft"]["who"] == "ann"


def test_project_and_pipeline_events(gl):
    from mason.server import gitlab as GL

    what = [e["what"] for e in GL.repo_events(gl, "gitlab:grp/app")]
    assert what == ["pushed 3 commits to main", "accepted MR !5"]
    run = {e["what"]: e for e in GL.pipeline_events(gl, "gitlab:grp/app", 77)}
    assert run["job test / unit: failed"]["detail"] == "took 1m 10s" and run["finished: failed"]["state"] == "bad"
    text = GL.pipeline_detail(gl, "gitlab:grp/app", 77)
    assert "pipeline #77" in text and "- failed    test / unit  (1m 10s)" in text


def test_event_helpers():
    assert E.duration("2026-11-01T09:00:00Z", "2026-11-01T09:00:42Z") == "took 42s"
    assert E.duration("", "x") == "" and E.state_of("FAILURE") == "bad" and E.state_of("in_progress") == "warn"
    long = "x" * 300
    assert len(E.event("", "w", detail=long)["detail"]) == 240 and E.event("", "w", detail=long)["more"] == long
    assert E.from_timeline({"event": "subscribed"}) is None
    assert E.from_timeline({"event": "some_new_kind", "actor": {"login": "a"}})["what"] == "some new kind"
