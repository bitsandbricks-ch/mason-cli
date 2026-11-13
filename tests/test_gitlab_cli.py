"""GitLab in the CLI: commands over gitlab: projects through tests/fake_glab (a made-up group acme-gl)."""

from __future__ import annotations

import subprocess
import sys

import pytest

from mason import glab
from mason.core import RateLimited
from mason.transport import HttpError


def mason(env, *args) -> str:
    proc = subprocess.run([sys.executable, "-m", "mason", *args], env=env, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL, timeout=60, check=False)
    return proc.stdout + proc.stderr


@pytest.fixture
def gl_env(env, tmp_path):
    return {**env, "MASON_GITLAB_GROUPS": "acme-gl", "FAKE_GH_LOG": str(tmp_path / "calls.log")}


def calls(env) -> list[str]:
    with open(env["FAKE_GH_LOG"]) as f:
        return [line for line in f.read().splitlines() if line.startswith("glab ")]


def test_parse_include_output():
    out = b"HTTP/2.0 200 OK\r\nEtag: W/\"1\"\r\nRatelimit-Remaining: 9\r\n\r\n{\"a\": 1}"
    assert glab.parse(out) == (200, {"etag": 'W/"1"', "ratelimit-remaining": "9"}, b'{"a": 1}')
    assert glab.parse(b"HTTP/2.0 204 No Content\r\n\r\n") == (204, {}, b"")
    assert glab.parse(b"") == (None, {}, b"")  # glab failed before asking GitLab
    assert glab.parse(b'{"not": "headers"}') == (None, {}, b"")


class Canned(glab.Glab):
    def __init__(self, out: bytes, code: int = 0, err: bytes = b""):
        super().__init__()
        self.answer = (out, code, err)
        self.seen: list[list[str]] = []

    def run(self, args, stdin=None):
        self.seen.append(args)
        out, code, err = self.answer
        return subprocess.CompletedProcess(args, code, out, err)


def test_glab_transport_maps_answers():
    gl = Canned(b"HTTP/2.0 200 OK\r\nRatelimit-Limit: 2000\r\nRatelimit-Remaining: 5\r\nRatelimit-Reset: 1\r\n\r\n[]")
    assert gl.api("GET", "/projects/a%2Fb/pipelines?per_page=3") == []
    assert gl.seen[0] == ["api", "--include", "--method", "GET", "--hostname", "gitlab.com",
                          "projects/a%2Fb/pipelines?per_page=3"]
    assert gl.last_rate["remaining"] == 5  # GitLab's RateLimit-* headers are read as with a token
    with pytest.raises(HttpError) as err:
        Canned(b'HTTP/2.0 404 Not Found\r\n\r\n{"message": "404 Project Not Found"}', 1).api("GET", "/projects/x%2Fy")
    assert err.value.status == 404 and "404 Project Not Found" in str(err.value)
    with pytest.raises(RateLimited):
        Canned(b"HTTP/2.0 429 Too Many Requests\r\nRetry-After: 30\r\n\r\n{}", 1).api("GET", "/projects/x%2Fy")
    with pytest.raises(RuntimeError, match="none of your business"):
        Canned(b"", 1, b"none of your business").api("GET", "/user")


def test_graphql_goes_to_glab_graphql():
    gl = Canned(b'HTTP/2.0 200 OK\r\n\r\n{"data": {"x": 1}}')
    assert gl.graphql("query { x }", {}) == {"x": 1}
    assert gl.seen[0][:7] == ["api", "--include", "--method", "POST", "--hostname", "gitlab.com", "graphql"]
    assert gl.seen[0][-2:] == ["--input", "-"]


def test_no_gitlab_set_up_means_no_glab(env, tmp_path):
    quiet = {**env, "FAKE_GH_LOG": str(tmp_path / "calls.log")}
    mason(quiet, "status")
    assert calls(quiet) == []


def test_repos_and_status_take_gitlab_groups(gl_env):
    out = mason(gl_env, "repos")
    assert "gitlab:acme-gl/web" in out and "gitlab:acme-gl/tools/cli" in out and "8 repos" in out
    out = mason(gl_env, "repos", "--group", "gitlab:acme-gl/tools/")
    assert "gitlab:acme-gl/tools/cli" in out and "1 repos" in out
    assert "gitlab:acme-gl/tools/cli" in mason(gl_env, "repos", "cli")  # a project by its last part
    out = mason(gl_env, "status")
    assert "acme/api" in out  # GitHub as before
    assert "gitlab:acme-gl/tools/cli  default  v2.0.0    0/0              success" in out
    assert "gitlab:acme-gl/web        default  -         1/1              failure" in out
    assert sum("graphql" in c for c in calls(gl_env)) == 1  # one query for both projects


def test_prs_runs_issues(gl_env):
    out = mason(gl_env, "prs", "--group", "gitlab:acme-gl/")
    assert "!4 Add dark mode  (ann, feat-4)" in out and "ready · pipeline success · approved · mergeable" in out
    assert "2 open merge requests" in out
    out = mason(gl_env, "runs", "web", "gitlab:acme-gl/web")
    assert "actions/runs/9" in out and "https://gitlab.com/acme-gl/web/-/pipelines/77" in out
    out = mason(gl_env, "issues", "gitlab:acme-gl/web")
    assert "#3     Login is slow  [bug]" in out


def test_merge_doctor_summary(gl_env):
    out = mason(gl_env, "merge", "--dry-run", "gitlab:acme-gl/web")
    assert "[dry-run] auto-merge !4 Add dark mode" in out and "!5 Draft: new logo: draft, left open" in out
    out = mason(gl_env, "merge", "gitlab:acme-gl/web#4")
    assert "auto-merge on (merges when the pipeline passes)" in out
    assert any("--method PUT" in c and "merge_requests/4/merge" in c for c in calls(gl_env))
    out = mason(gl_env, "doctor", "--summary", "--group", "gitlab:acme-gl/")
    assert "gitlab:acme-gl/web" in out and "2 issues" in out and "of 2 repos off their defaults" in out


def test_pr_open_whoami_config(gl_env):
    assert "!4 Add dark mode" in mason(gl_env, "pr", "gitlab:acme-gl/web#4")
    assert "https://gitlab.com/acme-gl/web/-/merge_requests/4" in mason(gl_env, "open", "gitlab:acme-gl/web#4")
    assert "GitLab: mike-gl on gitlab.com, through glab" in mason(gl_env, "whoami")
    assert "GitLab       acme-gl/ on https://gitlab.com (through glab)" in mason(gl_env, "config")


def test_github_only_commands_say_so(gl_env):
    out = mason(gl_env, "auto", "gitlab:acme-gl/web")
    assert "`mason auto` doesn't know GitLab projects yet" in out


def test_signed_out_glab(gl_env):
    out = mason({**gl_env, "FAKE_GLAB_SIGNED_OUT": "1"}, "status", "gitlab:acme-gl/web")
    assert "Sign in to GitLab first: glab auth login --hostname gitlab.com" in out


def test_init_keeps_gitlab_groups(env, tmp_path):
    mine = {**env, "XDG_CONFIG_HOME": str(tmp_path / "config")}
    mason(mine, "init", "acme/defaults", "--gitlab-group", "acme-gl")
    text = (tmp_path / "config" / "mason" / "config.toml").read_text()
    assert 'gitlab_groups = ["acme-gl"]' in text
    assert "gitlab:acme-gl/web" in mason({**mine, "FAKE_GH_LOG": str(tmp_path / "log")}, "repos")
