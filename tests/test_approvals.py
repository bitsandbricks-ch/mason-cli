"""Approvals leave out runs nobody needs any more: closed PRs, newer commits, replaced runs."""
from mason import repos as R
from mason.server import gitlab as GL


def test_stale_runs(monkeypatch):
    pulls = [{"head": {"ref": "fix", "sha": "new", "repo": {"full_name": "eve/web"}}},
             {"head": {"ref": "docs", "sha": "d1", "repo": {"full_name": "eve/web"}}}]
    newer = {"workflow_runs": [{"id": 40, "workflow_id": 9, "head_branch": "main"}]}
    monkeypatch.setattr(R, "api_pages", lambda path: pulls if "/pulls?state=open" in path else [])
    monkeypatch.setattr(R, "api", lambda method, path, body=None: newer if "/workflows/9/runs" in path else {})
    def pr(i, branch, sha):
        return {"id": i, "event": "pull_request", "workflow_id": 3, "head_branch": branch, "head_sha": sha,
                "head_repository": {"full_name": "eve/web"}}
    runs = [
        pr(1, "fix", "old"), pr(2, "gone", "x"), pr(3, "docs", "d1"),
        {"id": 10, "event": "push", "workflow_id": 5, "head_branch": "main"},
        {"id": 11, "event": "push", "workflow_id": 5, "head_branch": "main"},
        {"id": 30, "event": "push", "workflow_id": 9, "head_branch": "main"},
    ]
    # 1: its PR has newer commits; 2: no open PR; 10: run 11 replaced it; 30: run 40 (since run) replaced it
    assert R.stale_runs("acme/web", runs) == {1, 2, 10, 30}


def test_stale_runs_keeps_all_when_prs_cant_be_read(monkeypatch):
    def fail(path):
        raise RuntimeError("gh: Forbidden (HTTP 403)")
    monkeypatch.setattr(R, "api_pages", fail)
    monkeypatch.setattr(R, "api", lambda method, path, body=None: {})
    run = {"id": 1, "event": "pull_request", "head_branch": "fix", "head_sha": "a"}
    assert R.stale_runs("acme/web", [run]) == set()


def test_gitlab_old_pipelines_and_deployments():
    jobs = [{"id": 1, "ref": "main", "pipeline": {"id": 7, "ref": "main"}},
            {"id": 2, "ref": "main", "pipeline": {"id": 9, "ref": "main"}},
            {"id": 3, "ref": "main", "pipeline": {"id": 9, "ref": "main"}},
            {"id": 4, "ref": "v1", "pipeline": {"id": 5, "ref": "v1"}}]
    assert [j["id"] for j in GL.current_jobs(jobs)] == [2, 3, 4]
    deps = [{"id": 1, "environment": {"name": "prod"}}, {"id": 2, "environment": {"name": "prod"}},
            {"id": 3, "environment": {"name": "staging"}}]
    assert [d["id"] for d in GL.current_deployments(deps)] == [2, 3]
