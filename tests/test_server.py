"""The operator (web app) against tests/fake_gh: sign-in state, CSRF, API keys, the device login,
every command endpoint, the console, the proxy's allowlist, the defaults editor and the marketplace."""

from __future__ import annotations

import json
import sys

import pytest

pytest.importorskip("flask")
pytest.importorskip("sqlalchemy")
if sys.version_info < (3, 10):  # pragma: no cover
    pytest.skip("the operator needs Python 3.10+", allow_module_level=True)


@pytest.fixture()
def op(env, monkeypatch, tmp_path):
    for key in ("PATH", "FAKE_GH_LOG", "XDG_CONFIG_HOME", "MASON_OPEN", "MASON_PLUGINS"):
        monkeypatch.setenv(key, env[key])
    monkeypatch.delenv("MASON_DEFAULTS", raising=False)
    from mason import config, transport
    from mason.server import oauth, security
    from mason.server import settings as S
    from mason.server.app import create_app
    from mason.server.models import Identity, Session, User, db

    settings = S.Settings(
        url="http://localhost:8080", data=tmp_path, database=f"sqlite:///{tmp_path / 'op.db'}", secret_key="k" * 40,
        github=S.Provider("github", "id", "secret", "https://github.com", "https://api.github.com", "repo"),
        gitlab=S.Provider("gitlab", "", "", "https://gitlab.com", "https://gitlab.com/api/v4", "api"),
        allow_users={("github", "mike")}, plugin_index=str(tmp_path / "index.json"))
    from mason.server import limits
    from mason.server.api import repos as repos_api
    limits.reset()
    repos_api._doctor.clear()  # kept doctor checks are per user id, and every test's database starts at 1
    app = create_app(settings)
    vault = app.config["VAULT"]
    # every GitHub call goes to the fake gh, with the user's token in GH_TOKEN
    monkeypatch.setattr(oauth, "github", lambda user: transport.GhTransport("ghtoken") if user.identity("github")
                        else None)
    with app.app_context():
        user = User(name="Mike")
        db.add(user)
        db.flush()
        db.add(Identity(user_id=user.id, provider="github", host="github.com", uid="1", login="mike",
                        access_enc=vault.encrypt("ghtoken")))
        user.settings = {"defaults": "acme/defaults"}
        raw = "cookie-value"
        db.add(Session(id=security.sha256(raw), user_id=user.id, csrf="csrf-token"))
        db.commit()
    client = app.test_client()
    client.set_cookie("mason_session", raw, domain="localhost")
    config._loaded.clear()
    yield app, client
    transport.set_default(None)
    db.remove()


H = {"X-CSRF-Token": "csrf-token"}


def test_signed_out_and_headers(op):
    app, _ = op
    anon = app.test_client()
    r = anon.get("/api/v1/me")
    assert r.json["user"] is None and r.json["providers"] == ["github"]
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert r.headers["Cache-Control"] == "no-store" and r.headers["X-Frame-Options"] == "DENY"
    assert anon.get("/api/v1/status").status_code == 401
    r = anon.get("/api/v1/auth/github/login")
    assert r.status_code == 302 and "code_challenge_method=S256" in r.headers["Location"]
    assert "state=" in r.headers["Location"] and "mason_oauth=" in r.headers["Set-Cookie"]
    assert anon.get("/api/v1/auth/github/callback?state=nope&code=x").headers["Location"].startswith("/login?error=")
    assert anon.get("/api/v1/auth/gitlab/login").status_code == 404  # not set up


def test_me_csrf_settings(op):
    _, c = op
    me = c.get("/api/v1/me").json
    assert me["user"]["name"] == "Mike" and me["csrf"] == "csrf-token" and me["identities"][0]["login"] == "mike"
    assert c.put("/api/v1/settings", json={"orgs": ["acme"]}).status_code == 403  # no CSRF token
    r = c.put("/api/v1/settings", json={"orgs": ["acme"]}, headers={**H, "Origin": "https://evil.example"})
    assert r.status_code == 403
    assert c.put("/api/v1/settings", json={"defaults": "/etc"}, headers=H).status_code == 400  # no server folders
    assert c.put("/api/v1/settings", json={"orgs": "acme, mike"}, headers=H).json["orgs"] == ["acme", "mike"]
    assert c.get("/api/v1/settings").json["org_defaults"] is True  # each org's .mason: on unless turned off
    assert c.put("/api/v1/settings", json={"org_defaults": "no"}, headers=H).status_code == 400
    assert c.put("/api/v1/settings", json={"org_defaults": False}, headers=H).json["org_defaults"] is False



def test_theme_is_a_per_user_setting(op):
    """The web app saves the theme to the account, so it follows the user to every browser."""
    _, c = op
    assert c.get("/api/v1/me").json["settings"]["theme"] == ""  # the default (bricks, or mortar on a light system)
    assert c.put("/api/v1/settings", json={"theme": "mortar"}, headers=H).json["theme"] == "mortar"
    assert c.get("/api/v1/me").json["settings"]["theme"] == "mortar"
    assert c.get("/api/v1/settings").json["orgs"] == []  # saving the theme leaves the other settings alone
    assert c.put("/api/v1/settings", json={"theme": "neon"}, headers=H).status_code == 400
    assert c.put("/api/v1/settings", json={"theme": "phosphor"}, headers=H).status_code == 400  # removed
    assert c.get("/api/v1/settings").json["theme"] == "mortar"


def test_web_themes_match_the_server():
    """web/src/themes.js, style.css and the server's THEMES list name the same themes."""
    import re
    from pathlib import Path

    from mason.server.context import THEMES

    web = Path(__file__).resolve().parents[1] / "web" / "src"
    js = re.findall(r"'([a-z]+)'", (web / "themes.js").read_text())
    css = re.findall(r'\[data-theme="([a-z]+)"\]', (web / "style.css").read_text())
    assert tuple(js) == THEMES and set(css) == set(THEMES)

def test_lists(op):
    _, c = op
    repos = c.get("/api/v1/repos").json
    assert "acme/plugin-a" in [r["repo"] for r in repos["repos"]] and repos["groups"] == ["plugins", "default"]
    assert repos["owners"] == ["acme/", "mike/"]
    assert [r["repo"] for r in c.get("/api/v1/repos?group=mike/").json["repos"]] == ["mike/dotfiles"]
    st = c.get("/api/v1/status").json
    api = next(r for r in st["rows"] if r["repo"] == "acme/api")
    assert st["head"][:4] == ["group", "released", "PRs ready/draft", "CI"] and api["cells"][1] == "v1.10.0"
    prs = c.get("/api/v1/prs").json["prs"]
    assert {p["number"] for p in prs if p["repo"] == "acme/web"} == {7, 8, 9}
    assert next(p for p in prs if p["number"] == 9)["conflicts"]
    assert "blocked: required checks" in c.get("/api/v1/pr?repo=acme/web&number=7").json["text"]
    assert any(r["repo"] == "acme/web" for r in c.get("/api/v1/runs?repo=web").json["runs"])
    waits = c.get("/api/v1/approvals").json["approvals"]
    assert {(w["repo"], w["id"]) for w in waits} == {("acme/api", 5), ("acme/web", 6), ("acme/plugin-a", 12)}
    assert next(w for w in waits if w["id"] == 12)["blocked"] and not next(w for w in waits if w["id"] == 5)["blocked"]
    rel = c.get("/api/v1/releases?problems=1").json["releases"]
    assert any("missing *.zip" in " ".join(r["problems"]) for r in rel)
    assert c.get("/api/v1/packages").json["packages"]
    sec = {s["repo"]: s for s in c.get("/api/v1/security").json["security"]}
    assert sec["acme/api"]["alerts"][0]["severity"] == "high"
    groups = c.get("/api/v1/config").json["groups"]
    assert groups[0]["from"] == "acme/plugin-tpl"


def test_doctor_per_repo(op):
    _, c = op
    assert c.get("/api/v1/doctor").json == {"repos": {}}  # nothing checked yet: nothing kept
    got = c.get("/api/v1/doctor?repo=acme/web").json  # a repo page: checked on the spot
    assert not got["ok"] and "delete_branch_on_merge is false, defaults has true" in got["problems"]
    assert "mason doctor --fix acme/web" in got["fixes"] and got["checked"] > 0
    assert c.get("/api/v1/doctor?repo=acme/web").json["checked"] == got["checked"]  # kept, not checked again
    st = c.get("/api/v1/status").json["doctor"]
    assert st["acme/web"]["issues"] == len(got["problems"]) and "acme/api" not in st
    found = c.post("/api/v1/doctor", json={}, headers=H).json["repos"]  # Checks: every repo
    ref = next(r for r in found if r["repo"] == "acme/plugin-tpl")
    assert ref["ok"] and ref["reference"]
    st = c.get("/api/v1/status").json["doctor"]
    assert {"acme/api", "acme/web", "acme/plugin-b", "mike/dotfiles"} <= set(st)
    assert st["acme/plugin-tpl"]["ok"] and not st["acme/plugin-b"]["ok"]
    # a dry-run fix says what it would fix, not what the repo has: the kept check stays
    before = c.get("/api/v1/doctor?repo=acme/plugin-b").json
    c.post("/api/v1/doctor", json={"repos": ["b"], "fix": True, "dry_run": True}, headers=H)
    assert c.get("/api/v1/doctor?repo=acme/plugin-b").json["problems"] == before["problems"]
    assert c.get("/api/v1/doctor?repo=nope").status_code == 400


def test_follow_ups_read_only_the_named_repos(op):
    """The web app's follow-up after a change: fresh=1 with the repos named answers for just those, and says
    whether a release run is still going (busy), so it knows to keep asking."""
    _, c = op
    c.get("/api/v1/prs")
    prs = c.get("/api/v1/prs?repo=acme/web&fresh=1").json
    assert {p["repo"] for p in prs["prs"]} == {"acme/web"} and {p["number"] for p in prs["prs"]} == {7, 8, 9}
    rel = c.get("/api/v1/releases?repo=acme/api&fresh=1").json["releases"]
    assert [r["repo"] for r in rel] == ["acme/api"] and rel[0]["busy"] is False
    assert c.get("/api/v1/release?repo=acme/api&fresh=1").json["busy"] is False


def test_a_release_run_that_has_not_finished_is_busy():
    from mason import repos as R

    assert R.running([{"status": "in_progress", "conclusion": None}])
    assert R.running([{"status": "queued"}, {"status": "completed", "conclusion": "success"}])
    assert R.running([{"conclusion": "running"}])  # GitLab pipelines: their status in conclusion
    assert not R.running([{"status": "completed", "conclusion": "failure"}])
    assert not R.running([])


def test_changes_are_dry_runs_and_audited(op):
    _, c = op
    r = c.post("/api/v1/merge", json={"targets": ["web#8", "web#9"], "dry_run": True}, headers=H)
    assert "draft, left open" in r.json["text"] and "has conflicts" in r.json["text"]
    text = c.post("/api/v1/doctor", json={"repos": ["web"]}, headers=H).json["text"]
    assert "delete_branch_on_merge is false, defaults has true" in text
    text = c.post("/api/v1/doctor", json={"repos": ["b"], "fix": True, "dry_run": True}, headers=H).json["text"]
    assert "[dry-run] PATCH /repos/acme/plugin-b" in text
    text = c.post("/api/v1/sync", json={"repos": ["b"], "dry_run": True}, headers=H).json["text"]
    assert "update LICENSE" in text and "[dry-run] PR on mason/sync-" in text
    text = c.post("/api/v1/new", json={"repo": "acme/plugin-c", "dry_run": True}, headers=H).json["text"]
    assert "[dry-run] create private acme/plugin-c from the template acme/plugin-tpl" in text
    text = c.post("/api/v1/approve", json={"repo": "acme/api", "id": 5, "dry_run": True}, headers=H).json["text"]
    assert "[dry-run] approve production for acme/api main" in text
    got = c.get("/api/v1/issues?mine=1").json
    assert [(i["repo"], i["number"]) for i in got["issues"]] == [("acme/web", 3)] and got["labels"] == ["bug"]
    assert "I can reproduce it." in c.get("/api/v1/issue?repo=acme/web&number=3").json["text"]
    text = c.post("/api/v1/issues", json={"repo": "acme/web", "title": "Crash", "labels": ["bug"], "dry_run": True},
                  headers=H).json["text"]
    assert "[dry-run] POST /repos/acme/web/issues" in text
    text = c.post("/api/v1/issue", json={"repo": "acme/web", "number": 3, "action": "close", "dry_run": True},
                  headers=H).json["text"]
    assert "[dry-run] PATCH /repos/acme/web/issues/3" in text
    assert c.post("/api/v1/issues", json={"repo": "acme/web", "title": " "}, headers=H).status_code == 400
    wf = {w["repo"]: w for w in c.get("/api/v1/workflows").json["workflows"]}
    assert wf["acme/api"] == {"repo": "acme/api", "workflows": 0, "findings": []}
    assert {f["kind"] for f in wf["acme/web"]["findings"]} == {"pinned", "permissions", "pull_request_target",
                                                              "injection"}
    text = c.post("/api/v1/workflows/pin", json={"repos": ["web"], "dry_run": True}, headers=H).json["text"]
    assert "[dry-run] PUT /repos/acme/web/contents/.github/workflows/ci.yml" in text
    log = c.get("/api/v1/audit").json
    done = {a["action"] for a in log}
    assert {"merge", "doctor.fix", "sync", "new", "approve", "workflows.pin", "issue.create", "issue.close"} <= done
    assert all(a["dry_run"] for a in log if a["action"] in ("merge", "sync"))


def test_console(op):
    _, c = op
    out = c.post("/api/v1/console", json={"line": "mason status"}, headers=H).json["text"]
    assert "acme/api" in out and "v1.10.0" in out
    assert "draft, left open" in c.post("/api/v1/console", json={"line": "mason merge --dry-run web#8"},
                                        headers=H).json["text"]
    assert c.post("/api/v1/console", json={"line": "mason init /etc"}, headers=H).status_code == 400
    assert c.post("/api/v1/console", json={"line": "rm -rf /"}, headers=H).status_code == 400
    assert "usage" in c.post("/api/v1/console", json={"line": "mason status --nope"}, headers=H).json["text"]


def test_api_keys_and_device_login(op):
    app, c = op
    r = c.post("/api/v1/keys", json={"name": "laptop", "scope": "read"}, headers=H)
    key = r.json["key"]
    assert key.startswith("mason_") and r.status_code == 201
    k = app.test_client()
    auth = {"Authorization": f"Bearer {key}"}
    assert k.get("/api/v1/me", headers=auth).json["scope"] == "read"
    assert k.post("/api/v1/merge", json={"targets": ["web#7"]}, headers=auth).status_code == 403  # read key
    assert k.post("/api/v1/merge", json={"targets": ["web#7"], "dry_run": True}, headers=auth).status_code == 200
    assert k.post("/api/v1/keys", json={"name": "x"}, headers=auth).status_code == 403  # keys come from the browser
    assert k.get("/api/v1/me", headers={"Authorization": "Bearer mason_deadbeef_nope"}).status_code == 401
    c.delete(f"/api/v1/keys/{r.json['id']}", headers=H)
    assert k.get("/api/v1/status", headers=auth).status_code == 401  # revoked

    dev = app.test_client()
    code = dev.post("/api/v1/device/code", json={"scope": "write"}).json
    assert dev.post("/api/v1/device/token", json={"device_code": code["device_code"]}).json["error"] == \
        "authorization_pending"
    assert c.get(f"/api/v1/device/info?code={code['user_code']}").json["scope"] == "write"
    assert c.post("/api/v1/device/approve", json={"user_code": code["user_code"]}, headers=H).json["ok"]
    from mason.server.models import DeviceGrant, db
    with app.app_context():
        db.query(DeviceGrant).update({"last_poll": None})
        db.commit()
    got = dev.post("/api/v1/device/token", json={"device_code": code["device_code"]}).json
    assert got["key"].startswith("mason_") and got["scope"] == "write"
    assert dev.post("/api/v1/device/token", json={"device_code": code["device_code"]}).json["error"] == \
        "expired_token"  # handed out once


def test_proxy_allowlist():
    from mason.server.api.proxy import allowed
    assert allowed("GET", "/repos/acme/web/pulls")
    assert allowed("PATCH", "/repos/acme/web")
    assert allowed("POST", "/repos/acme/web/actions/runs/5/pending_deployments")
    assert not allowed("DELETE", "/repos/acme/web")  # never deletes a repo
    assert not allowed("PUT", "/repos/acme/web/collaborators/eve")
    assert allowed("GET", "/repos/acme/web/actions/secrets")  # names only: GitHub never gives values out
    assert allowed("PUT", "/repos/acme/web/actions/secrets/NPM_TOKEN")  # encrypted by the CLI
    assert not allowed("DELETE", "/repos/acme/web/actions/secrets/NPM_TOKEN")
    assert allowed("PUT", "/repos/acme/web/environments/production")
    assert allowed("POST", "/repos/acme/web/pages") and allowed("PATCH", "/repos/acme/web/code-scanning/default-setup")
    assert allowed("GET", "/orgs/acme/teams/ops") and not allowed("PUT", "/orgs/acme/teams/ops/members/eve")
    assert not allowed("POST", "/user/keys")
    assert not allowed("GET", "/admin/users")
    assert allowed("GET", "/repos/acme/web/hooks") and allowed("GET", "/repos/acme/web/keys")  # doctor reads the lists
    assert not allowed("GET", "/repos/acme/web/hooks/1") and not allowed("POST", "/repos/acme/web/hooks")
    assert not allowed("POST", "/repos/acme/web/keys") and allowed("PATCH", "/repos/acme/web/properties/values")


def test_defaults_editor(op):
    _, c = op
    d = c.get("/api/v1/defaults").json
    assert d["repo"] == "acme/defaults" and d["path"] == "mason.toml" in d["files"]
    assert d["problems"] == []
    bad = c.post("/api/v1/defaults/validate", json={"path": "mason.toml",
                                                    "text": '[[group]]\nname="a"\nmatch={nope=1}\n'}, headers=H).json
    assert "match doesn't know nope" in bad["problems"][0]
    bad = c.post("/api/v1/defaults/validate", headers=H, json={
        "path": "mason.toml", "text": '[[group]]\nname="a"\nskip=["nope"]\nvisibility="x"\nactions={y=1}\n'}).json
    assert [p.split(": ")[1][:14] for p in bad["problems"]] == ["skip doesn't k", "visibility is ", "actions knows "]
    rs = c.post("/api/v1/defaults/validate", json={"path": "rulesets/default/x.json", "text": '{"target": "x"}'},
               headers=H).json
    assert "a ruleset needs a name" in rs["problems"]
    assert c.put("/api/v1/defaults/file", json={"path": "../etc/passwd", "text": "x"}, headers=H).status_code == 400
    assert any(t["kind"] == "ruleset" for t in c.get("/api/v1/defaults/templates").json)
    got = c.post("/api/v1/defaults/ruleset-from", json={"repo": "acme/api"}, headers=H).json
    assert got[0]["path"] == "rulesets/default/main.json" and json.loads(got[0]["text"])["name"] == "main"


def test_market(op, tmp_path):
    app, c = op
    from mason import market
    pem, pub = market.keygen()
    doc = {"name": "test", "plugins": [{"name": "demo", "package": "demo-pkg", "version": "1.0",
                                        "source": "git+https://example.org/demo@v1"}]}
    (tmp_path / "index.json").write_text(json.dumps(doc))
    got = c.get("/api/v1/market").json
    assert got["status"] == "unverified" and got["plugins"][0]["name"] == "demo" and "can_install" not in got
    (tmp_path / "index.json").write_text(json.dumps(market.sign(doc, pem)))
    app.config["OP"].plugin_index_keys = [pub]
    assert c.get("/api/v1/market").json["status"] == "verified"
    tampered = market.sign(doc, pem)
    tampered["plugins"][0]["source"] = "git+https://evil.example/x"
    assert market.verify(tampered, market.trusted_keys([pub]))[0] == "unverified"
    assert c.post("/api/v1/market/demo/install", headers=H).status_code in (404, 405)  # never from the web


def test_stats(op):
    _, c = op
    m = c.get("/api/v1/metrics?days=30").json
    assert m["days"] == 30 and "merged_by_week" in m["totals"] and m["repos"]


# ── sign-in: settings, open sign-in, GitHub's device flow ───────────────────


def test_settings_defaults(monkeypatch, tmp_path):
    from mason.server import settings as S
    for k in ("MASON_URL", "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "GITHUB_URL", "GITLAB_CLIENT_ID",
              "GITLAB_CLIENT_SECRET", "MASON_ALLOW_USERS", "MASON_ALLOW_ORGS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MASON_DATA", str(tmp_path))
    op = S.load()
    assert op.url == "http://localhost:8080" and op.problems() == []  # no MASON_DEV, no allow lists needed
    assert op.github.client_id == S.GITHUB_CLIENT_ID == "Ov23liFJgLtIjB3ZtuOy"
    assert op.github.method == "device" and not op.gitlab.enabled and op.open_sign_in
    monkeypatch.setenv("GITHUB_CLIENT_ID", "mine")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "s")
    monkeypatch.setenv("GITLAB_CLIENT_ID", "gl")
    monkeypatch.setenv("GITLAB_CLIENT_SECRET", "gs")
    monkeypatch.setenv("MASON_ALLOW_ORGS", "acme")
    op = S.load()
    assert (op.github.client_id, op.github.method, op.gitlab.method) == ("mine", "redirect", "redirect")
    assert not op.open_sign_in
    monkeypatch.delenv("GITHUB_CLIENT_ID")
    monkeypatch.setenv("GITHUB_URL", "https://ghe.example.org")  # the public app means nothing there
    assert S.load().github.client_id == ""
    for url in ("http://localhost:8080", "http://127.0.0.1", "http://192.168.1.5:8080", "http://10.0.0.2",
                "http://[::1]:8080", "http://nas.local", "http://mason.lan", "http://box.home.arpa",
                "https://mason.example.org"):
        op.url = url
        assert op.problems() == [], url
    for url in ("http://mason.example.org", "http://8.8.8.8", "http://local.example.org", "mason.example.org"):
        op.url = url
        assert op.problems(), url


def test_serve_port_sets_default_url(monkeypatch, tmp_path, capsys):
    from mason.server import app as A
    from mason.server import settings as S
    monkeypatch.delenv("MASON_URL", raising=False)
    monkeypatch.setenv("MASON_DATA", str(tmp_path))
    assert S.load().url == "http://localhost:8080"
    assert S.load(9000).url == "http://localhost:9000"
    monkeypatch.setenv("MASON_URL", "https://mason.example.org/")  # an explicit MASON_URL wins
    assert S.load(9000).url == "https://mason.example.org"
    monkeypatch.delenv("MASON_URL")
    ran = {}

    class FakeApp:
        def run(self, **kw):
            ran.update(kw)

    monkeypatch.setattr(A, "create_app", lambda op: ran.update(url=op.url) or FakeApp())
    from mason import cli
    cli.main(["serve", "--port", "9000"])
    assert (ran["url"], ran["port"], ran["host"]) == ("http://localhost:9000", 9000, "127.0.0.1")
    with pytest.raises(SystemExit):
        cli.main(["serve", "--check", "--port", "9001"])
    assert "url          http://localhost:9001" in capsys.readouterr().out


class FakeGitHub:
    """GitHub's device flow and /user, answering in order."""

    def __init__(self, login="ann", uid="77"):
        self.answers = []
        self.calls = []
        self.login, self.uid = login, uid

    def __call__(self, method, url, data=None, token=None, headers=None):
        self.calls.append((method, url, dict(data or {})))
        if url.endswith("/login/device/code"):
            return 200, {"device_code": "dev-123", "user_code": "ABCD-1234", "interval": 5, "expires_in": 900,
                         "verification_uri": "https://github.com/login/device"}
        if url.endswith("/login/oauth/access_token"):
            return self.answers.pop(0)
        if url.endswith("/user"):
            return 200, {"id": int(self.uid), "login": self.login, "name": self.login.title(), "avatar_url": ""}
        return 404, {}


def _poll(app, client):
    from mason.server.models import DeviceSignIn, db
    with app.app_context():  # pretend the interval has passed
        db.query(DeviceSignIn).update({"last_poll": None})
        db.commit()
    return client.post("/api/v1/auth/github/device/poll", json={})


def test_device_sign_in_is_open_to_anyone(op, monkeypatch):
    app, mike = op
    from mason.server import oauth
    app.config["OP"].allow_users = set()  # no allow lists: anyone may sign in
    fake = FakeGitHub()
    monkeypatch.setattr(oauth, "_http", fake)
    ann = app.test_client()
    assert ann.get("/api/v1/me").json["sign_in"] == {"github": "redirect"}
    assert ann.post("/api/v1/auth/github/device", json={}, headers={"Origin": "https://evil.example"}).status_code \
        == 403
    assert ann.post("/api/v1/auth/github/device/poll", json={}).json["status"] == "expired"  # nothing started
    r = ann.post("/api/v1/auth/github/device", json={"next": "/prs"})
    assert r.json["user_code"] == "ABCD-1234" and r.json["verification_uri"] == "https://github.com/login/device"
    assert "mason_device=" in r.headers["Set-Cookie"] and "HttpOnly" in r.headers["Set-Cookie"]
    assert fake.calls[0][2] == {"client_id": "id", "scope": "repo"}
    assert "dev-123" not in r.get_data(as_text=True)  # GitHub's device code stays on the server
    fake.answers = [(200, {"error": "authorization_pending"}), (200, {"error": "slow_down", "interval": 10}),
                    (200, {"access_token": "ann-token", "scope": "repo"})]
    assert _poll(app, ann).json == {"status": "pending", "interval": 5}
    assert ann.post("/api/v1/auth/github/device/poll", json={}).json["status"] == "pending"  # too soon: no call
    assert len([c for c in fake.calls if c[1].endswith("access_token")]) == 1
    assert _poll(app, ann).json == {"status": "pending", "interval": 10}
    got = _poll(app, ann)
    assert got.json == {"status": "done", "next": "/prs"}
    assert any("mason_session=" in h for h in got.headers.getlist("Set-Cookie"))
    assert fake.calls[-2][2]["grant_type"] == oauth.DEVICE_GRANT and "client_secret" not in fake.calls[-2][2]
    me = ann.get("/api/v1/me").json
    assert me["user"]["name"] == "Ann" and "is_admin" not in me["user"] and me["identities"][0]["login"] == "ann"
    # each user sees only their own keys, sessions and audit log
    mike.post("/api/v1/keys", json={"name": "mike-key"}, headers=H)
    assert ann.get("/api/v1/keys").json == []
    assert len(ann.get("/api/v1/sessions").json) == 1
    assert {a["action"] for a in ann.get("/api/v1/audit").json} == {"login.github"}
    assert {a["action"] for a in ann.get("/api/v1/audit?all=1").json} == {"login.github"}  # no "everyone"
    assert mike.get("/api/v1/admin/users").status_code == 404  # no admins, so no list of users
    assert mike.get("/api/v1/me").json["scope"] == "write"
    # plugins are switched per user: Ann's choice never reaches Mike ("everyone" is for operators, elsewhere)
    from mason import plugins

    class Demo:
        name = "demo"
        def tui_tabs(self): return []  # noqa: E301,E704
        def tui_checks(self): return []  # noqa: E301,E704
        def status_columns(self): return []  # noqa: E301,E704
    monkeypatch.setattr(plugins, "load", lambda: [Demo()])
    ah = {"X-CSRF-Token": me["csrf"]}
    assert ann.put("/api/v1/plugins/demo", json={"on": False, "everyone": False}, headers=ah).status_code == 200
    assert not next(p for p in ann.get("/api/v1/plugins").json["plugins"] if p["name"] == "demo")["on"]
    mine = next(p for p in mike.get("/api/v1/plugins").json["plugins"] if p["name"] == "demo")
    assert mine["on"] and not mine["off_for_all"]
    assert _poll(app, ann).status_code == 403  # signed in now: writes need the CSRF token
    r = ann.post("/api/v1/auth/github/device/poll", json={}, headers={"X-CSRF-Token": me["csrf"]})
    assert r.json["status"] == "expired"  # the cookie was for one sign-in


def test_device_sign_in_respects_allow_lists(op, monkeypatch):
    app, mike = op
    from mason.server import oauth
    fake = FakeGitHub(login="eve", uid="66")
    monkeypatch.setattr(oauth, "_http", fake)
    eve = app.test_client()  # MASON_ALLOW_USERS=github:mike
    eve.post("/api/v1/auth/github/device", json={})
    fake.answers = [(200, {"access_token": "eve-token"})]
    r = _poll(app, eve)
    assert r.status_code == 403 and "may not use this operator" in r.json["error"]
    assert eve.get("/api/v1/me").json["user"] is None
    eve.post("/api/v1/auth/github/device", json={})
    fake.answers = [(200, {"error": "access_denied"})]
    assert _poll(app, eve).json == {"status": "failed", "error": "you cancelled the sign-in at GitHub"}
    assert mike.get("/api/v1/me").json["user"]["name"] == "Mike"  # listed users still get in


def test_device_only_github(op, monkeypatch):
    app, _ = op
    gh = app.config["OP"].github
    gh.client_secret = ""  # only the public client ID: device flow, no redirect sign-in
    anon = app.test_client()
    assert anon.get("/api/v1/me").json["sign_in"] == {"github": "device"}
    assert anon.get("/api/v1/auth/github/login").status_code == 404
    assert anon.get("/api/v1/auth/github/callback?state=x&code=y").status_code == 404
    from mason.server import oauth
    monkeypatch.setattr(oauth, "_http", lambda *a, **k: (400, {"error": "device_flow_disabled"}))
    r = anon.post("/api/v1/auth/github/device", json={})
    assert r.status_code == 502 and "device flow switched on" in r.json["error"]
    assert anon.post("/api/v1/auth/gitlab/device", json={}).status_code == 404


def test_redirect_sign_in_github_and_gitlab(op, monkeypatch):
    app, _ = op
    from urllib.parse import parse_qs, urlsplit

    from mason.server import oauth
    op_ = app.config["OP"]
    op_.gitlab.client_id, op_.gitlab.client_secret = "gl-id", "gl-secret"
    op_.allow_users = set()
    anon = app.test_client()
    assert anon.get("/api/v1/me").json["sign_in"] == {"github": "redirect", "gitlab": "redirect"}
    for name, host in (("github", "https://github.com/login/oauth/authorize"),
                       ("gitlab", "https://gitlab.com/oauth/authorize")):
        r = anon.get(f"/api/v1/auth/{name}/login?next=/runs")
        loc = r.headers["Location"]
        q = parse_qs(urlsplit(loc).query)
        assert loc.startswith(host) and q["redirect_uri"] == [f"http://localhost:8080/api/v1/auth/{name}/callback"]
    state = q["state"][0]

    def fake(method, url, data=None, token=None, headers=None):
        if url == "https://gitlab.com/oauth/token":
            assert data["client_secret"] == "gl-secret" and data["grant_type"] == "authorization_code"
            return 200, {"access_token": "gl-token", "refresh_token": "r", "expires_in": 7200}
        if url == "https://gitlab.com/api/v4/user":
            return 200, {"id": 9, "username": "gil", "name": "Gil"}
        return 404, {}
    monkeypatch.setattr(oauth, "_http", fake)
    r = anon.get(f"/api/v1/auth/gitlab/callback?state={state}&code=abc")
    assert r.status_code == 302 and r.headers["Location"] == "/runs"
    me = anon.get("/api/v1/me").json
    assert me["identities"][0]["provider"] == "gitlab" and me["identities"][0]["login"] == "gil"
    assert "is_admin" not in me["user"]


def test_release_page_and_create(op):
    _, c = op
    page = c.get("/api/v1/release?repo=acme/api").json
    assert [r["tag"] for r in page["releases"]] == ["v1.10.0", "v1.2.0"] and page["selected"] == "v1.10.0"
    assert "- Faster startup" in page["text"] and page["suggest"] == "v1.10.1"
    page = c.get("/api/v1/release?repo=acme/api&tag=v1.2.0").json
    assert page["selected"] == "v1.2.0" and "prerelease" in page["text"]
    assert c.get("/api/v1/release?repo=acme/api&tag=v9.9.9").status_code == 404
    body = {"repo": "acme/api", "tag": "v1.11.0", "title": "Search", "notes": "- New", "draft": True, "dry_run": True}
    got = c.post("/api/v1/releases", json=body, headers=H).json
    assert "[dry-run] POST /repos/acme/api/releases" in got["text"] and "draft release v1.11.0" in got["text"]
    got = c.post("/api/v1/releases", json={**body, "dry_run": False}, headers=H).json
    assert got["ok"] and "created the draft release v1.11.0 of acme/api" in got["text"]
    got = c.post("/api/v1/releases", json={**body, "tag": "v1.10.0"}, headers=H).json
    assert not got["ok"] and "has a release v1.10.0 already" in got["text"]
    assert c.post("/api/v1/releases", json={**body, "tag": "no spaces"}, headers=H).status_code == 400
    assert any(a["action"] == "release.create" for a in c.get("/api/v1/audit").json)


def test_proxy_reads_through_the_users_cache_and_writes_make_it_stale(op, monkeypatch):
    from test_cache import Fake

    from mason.server import oauth
    from mason.transport import HttpTransport
    app, client = op
    api = Fake()
    try:
        t = HttpTransport("ghtoken", api_url=api.url, graphql_url=api.url + "/graphql", cache="60s")
        monkeypatch.setattr(oauth, "github", lambda user: t)
        r = client.get("/api/v1/github/rest/repos/acme/web/labels")
        assert r.status_code == 200 and r.headers.get("ETag")
        etag = r.headers["ETag"]
        r = client.get("/api/v1/github/rest/repos/acme/web/labels", headers={"If-None-Match": etag})
        assert r.status_code == 304
        assert len(api.hits("/repos/acme/web/labels")) == 1  # the second came from the cache
        r = client.post("/api/v1/github/rest/repos/acme/web/labels", json={"name": "bug"}, headers=H)
        assert r.status_code == 200
        client.get("/api/v1/github/rest/repos/acme/web/labels")
        got = api.hits("/repos/acme/web/labels")
        assert len(got) == 3 and got[-1][0] == "GET" and got[-1][2].get("If-None-Match") == etag
    finally:
        api.server.shutdown()
# ── revoking tokens when a login is disconnected or the account deleted ──────


def _add_gitlab(app, monkeypatch):
    from mason.server.models import Identity, User, db
    op = app.config["OP"]
    monkeypatch.setattr(op.gitlab, "client_id", "glid")
    monkeypatch.setattr(op.gitlab, "client_secret", "glsecret")
    with app.app_context():
        user = db.query(User).one()
        db.add(Identity(user_id=user.id, provider="gitlab", host="gitlab.com", uid="9", login="mike-gl",
                        access_enc=app.config["VAULT"].encrypt("gltoken")))
        db.commit()
        return [i.id for i in db.query(Identity).order_by(Identity.id)]


def test_unlink_revokes_with_a_client_secret(op, monkeypatch):
    app, c = op
    from mason.server import oauth
    calls = []
    monkeypatch.setattr(oauth, "_http", lambda method, url, data=None, **kw: calls.append((method, url, data, kw))
                        or (204 if method == "DELETE" else 200, {}))
    gh_id, gl_id = _add_gitlab(app, monkeypatch)
    r = c.delete(f"/api/v1/me/identities/{gl_id}", headers=H)
    assert r.json["revoked"] == [{"provider": "gitlab", "login": "mike-gl", "revoked": True, "manual": ""}]
    assert calls[-1][:2] == ("POST", "https://gitlab.com/oauth/revoke") and calls[-1][2]["token"] == "gltoken"
    # the last login goes with the account: GitHub's revoke API with the app's ID and secret
    r = c.delete("/api/v1/me", headers=H)
    assert r.json["revoked"][0]["revoked"] is True
    method, url, _, kw = calls[-1]
    assert (method, url) == ("DELETE", "https://api.github.com/applications/id/token")
    assert kw["json_body"] == {"access_token": "ghtoken"} and kw["headers"]["Authorization"].startswith("Basic ")


def test_device_flow_tokens_cant_be_revoked_and_say_so(op, monkeypatch):
    app, c = op
    from mason.server import oauth
    calls = []
    monkeypatch.setattr(oauth, "_http", lambda *a, **kw: calls.append(a) or (200, {}))
    monkeypatch.setattr(app.config["OP"].github, "client_secret", "")  # the built-in sign-in: no secret
    r = c.delete("/api/v1/me", headers=H)
    assert r.status_code == 200 and not calls
    assert r.json["revoked"] == [{"provider": "github", "login": "mike", "revoked": False,
                                  "manual": "https://github.com/settings/connections/applications/id"}]
    with app.app_context():
        from mason.server.models import Audit, Identity, db
        assert db.query(Identity).count() == 0  # Mason's copy is gone either way
        row = db.query(Audit).filter_by(action="account.delete").one()
        assert not row.ok and row.detail == "tokens not revoked by Mason: github" and row.user_id is None


def test_failed_revoke_gives_the_link(op, monkeypatch):
    app, c = op
    from mason.server import oauth
    monkeypatch.setattr(oauth, "_http", lambda *a, **kw: (500, {}))
    _, gl_id = _add_gitlab(app, monkeypatch)
    got = c.delete(f"/api/v1/me/identities/{gl_id}", headers=H).json["revoked"][0]
    assert got["revoked"] is False and got["manual"] == "https://gitlab.com/-/user_settings/applications"


# ── the audit log stays bounded ──────────────────────────────────────────────


def test_audit_hashes_ips_and_cuts_output(op, monkeypatch):
    app, c = op
    from mason.server.models import Audit, db
    op_settings = app.config["OP"]
    monkeypatch.setattr(op_settings, "audit_output", 50)
    c.post("/api/v1/doctor", json={"repos": ["b"], "fix": True, "dry_run": True}, headers=H,
           environ_base={"REMOTE_ADDR": "203.0.113.7"})
    with app.app_context():
        row = db.query(Audit).order_by(Audit.id.desc()).first()
        assert row.ip.startswith("ip:") and "203.0.113" not in row.ip and len(row.ip) == 19
        assert len(row.detail) < 120 and row.detail.endswith("more characters not kept)")
    # the same address hashes the same way, so users still see "same place as before"
    c.put("/api/v1/settings", json={"orgs": ["acme"]}, headers=H, environ_base={"REMOTE_ADDR": "203.0.113.7"})
    with app.app_context():
        a, b = db.query(Audit).order_by(Audit.id.desc()).limit(2)
        assert a.ip == b.ip
    monkeypatch.setattr(op_settings, "audit_ips", "none")
    c.put("/api/v1/settings", json={"orgs": ["acme"]}, headers=H)
    with app.app_context():
        assert db.query(Audit).order_by(Audit.id.desc()).first().ip == ""


def test_audit_keeps_the_newest_rows_and_purges_old_ones(op, monkeypatch):
    app, c = op
    from datetime import timedelta

    from mason.server import retention
    from mason.server.models import ApiKey, Audit, Session, User, db, utcnow
    monkeypatch.setattr(app.config["OP"], "audit_rows", 3)
    for n in range(5):
        c.put("/api/v1/settings", json={"orgs": [f"org{n}"]}, headers=H)
    with app.app_context():
        rows = db.query(Audit).filter(Audit.user_id.isnot(None)).order_by(Audit.id).all()
        assert len(rows) == 3
        uid = db.query(User).one().id
        old = utcnow() - timedelta(days=400)
        db.add(Audit(user_id=uid, action="ancient", at=old))
        db.add(Session(id="s" * 64, user_id=uid, csrf="x", created_at=old, seen_at=old))
        db.add(ApiKey(user_id=uid, name="gone", prefix="deadbeef", hash="h", revoked_at=old))
        db.add(ApiKey(user_id=uid, name="live", prefix="cafecafe", hash="h"))
        db.commit()
        assert retention.housekeeping(force=True)
        assert not db.query(Audit).filter_by(action="ancient").count()
        assert db.get(Session, "s" * 64) is None
        assert [k.name for k in db.query(ApiKey)] == ["live"]
        assert db.query(Session).count() == 1  # the test's own session is fresh


def test_deleting_the_account_deletes_its_audit_rows(op, monkeypatch):
    app, c = op
    from mason.server import oauth
    from mason.server.models import Audit, db
    monkeypatch.setattr(oauth, "_http", lambda *a, **kw: (204, {}))
    c.put("/api/v1/settings", json={"orgs": ["acme"]}, headers=H)
    assert c.delete("/api/v1/me", headers=H).status_code == 200
    with app.app_context():
        rows = db.query(Audit).all()
        assert [(r.action, r.user_id, r.ip, r.ok) for r in rows] == [("account.delete", None, "", True)]
        assert "Mike" not in rows[0].detail + rows[0].target


# ── rate limits and storage caps ─────────────────────────────────────────────


def test_api_rate_limits(op, monkeypatch):
    app, c = op
    s = app.config["OP"]
    monkeypatch.setattr(s, "rate_writes", 2)
    assert [c.put("/api/v1/settings", json={"orgs": ["a"]}, headers=H).status_code for _ in range(3)] == [200, 200, 429]
    r = c.put("/api/v1/settings", json={"orgs": ["a"]}, headers=H)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1 and "wait" in r.json["error"]
    assert c.get("/api/v1/me").status_code == 200  # reads have their own, larger budget
    monkeypatch.setattr(s, "rate_anon", 2)
    anon = app.test_client()
    assert [anon.get("/api/v1/me").status_code for _ in range(3)] == [200, 200, 429]
    assert anon.get("/api/v1/health").status_code == 200  # health checks are never limited


def _sign_in_as(app, login, uid):
    from mason.server import oauth
    with app.test_request_context("/api/v1/auth/github/device/poll", environ_base={"REMOTE_ADDR": "198.51.100.1"}):
        oauth.profile = lambda name, token: {"uid": uid, "login": login, "name": login, "avatar_url": ""}
        return oauth.sign_in("github", {"access_token": f"t-{login}"}, None)


def test_new_accounts_are_limited(op, monkeypatch):
    app, _ = op
    from mason.server import oauth
    monkeypatch.setattr(oauth, "profile", oauth.profile)  # restored after the test
    s = app.config["OP"]
    monkeypatch.setattr(s, "allow_users", set())  # open sign-in
    monkeypatch.setattr(s, "max_users", 2)
    assert _sign_in_as(app, "ann", "2").name == "ann"
    with pytest.raises(PermissionError, match="as many accounts"):
        _sign_in_as(app, "bob", "3")
    assert _sign_in_as(app, "ann", "2").name == "ann"  # existing accounts still sign in
    with pytest.raises(PermissionError, match="as many accounts"):
        _sign_in_as(app, "root", "4")
    monkeypatch.setattr(s, "allow_users", {("github", "root"), ("github", "ann")})
    assert _sign_in_as(app, "root", "4").name == "root"  # MASON_ALLOW_USERS always get in
    monkeypatch.setattr(s, "allow_users", set())
    monkeypatch.setattr(s, "max_users", 0)
    monkeypatch.setattr(s, "signups_per_ip", 1)
    from mason.server import limits
    limits.reset()
    assert _sign_in_as(app, "cid", "5").name == "cid"
    with pytest.raises(PermissionError, match="from this address"):
        _sign_in_as(app, "dan", "6")


def test_key_and_session_caps(op, monkeypatch):
    app, c = op
    from mason.server import auth
    from mason.server.models import ApiKey, Session, User, db
    monkeypatch.setattr(app.config["OP"], "max_keys", 2)
    made = [c.post("/api/v1/keys", json={"name": f"k{n}"}, headers=H) for n in range(3)]
    assert [r.status_code for r in made] == [201, 201, 409] and "revoke one first" in made[2].json["error"]
    for _ in range(6):  # revoked keys don't count, and only a few of them are kept
        assert c.delete(f"/api/v1/keys/{made[0].json['id']}", headers=H).status_code == 200
        made[0] = c.post("/api/v1/keys", json={"name": "again"}, headers=H)
        assert made[0].status_code == 201
    with app.app_context():
        assert db.query(ApiKey).count() <= 4
    assert c.post("/api/v1/keys", json={"days": True}, headers=H).status_code == 400
    monkeypatch.setattr(app.config["OP"], "max_sessions", 2)
    with app.test_request_context("/"):
        user = db.query(User).one()
        for _ in range(3):
            auth.start_session(app.make_response("x"), user)
        assert db.query(Session).filter_by(user_id=user.id).count() == 2


def test_settings_size_and_device_lookups(op):
    app, c = op
    big = [f"org-{n:03d}-" + "x" * 180 for n in range(200)]
    r = c.put("/api/v1/settings", json={"orgs": big, "repos": big}, headers=H)
    assert r.status_code == 413 and "KB" in r.json["error"]
    codes = [c.get("/api/v1/device/info?code=BCDF-GHJK").status_code for _ in range(11)]
    assert codes[:10] == [404] * 10 and codes[10] == 429
    assert c.post("/api/v1/device/approve", json={"user_code": "X", "days": 99999}, headers=H).status_code == 429


def test_proxy_reads_dont_count(op, monkeypatch):
    app, c = op
    monkeypatch.setattr(app.config["OP"], "rate_api", 2)
    codes = [c.get("/api/v1/github/rest/repos/acme/web").status_code for _ in range(4)]
    assert 429 not in codes
    assert [c.get("/api/v1/me").status_code for _ in range(3)] == [200, 200, 429]


def test_old_databases_lose_is_admin(tmp_path):
    import sqlite3

    from mason.server import models
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR(200), avatar_url VARCHAR(500), "
                      "created_at DATETIME, last_login DATETIME, settings_json TEXT, is_admin BOOLEAN NOT NULL);"
                      "INSERT INTO users VALUES (1, 'Mike', '', NULL, NULL, '{}', 1);"
                      "CREATE TABLE instance_settings (key VARCHAR(100) PRIMARY KEY, value TEXT);")
    con.close()
    engine = models.init(f"sqlite:///{path}")
    from sqlalchemy import inspect
    have = inspect(engine)
    assert "is_admin" not in {c["name"] for c in have.get_columns("users")}
    assert have.has_table("operators")
    models.db.add(models.User(name="Ann"))  # would fail on the old NOT NULL is_admin
    models.db.commit()
    assert [u.name for u in models.db.query(models.User).order_by(models.User.id)] == ["Mike", "Ann"]
    models.db.remove()
    engine.dispose()


def test_plugins_off_for_everyone(monkeypatch):
    from importlib import metadata

    from mason import plugins

    class EP:
        def __init__(self, name):
            self.name = name
        def load(self):  # noqa: E301
            return type("P", (), {"name": self.name})

    class EPs:
        def select(self, group):
            return [EP("a"), EP("b")]
    monkeypatch.setattr(metadata, "entry_points", lambda: EPs())
    monkeypatch.setattr(plugins, "_plugins", None)
    monkeypatch.delenv("MASON_PLUGINS", raising=False)
    monkeypatch.setenv("MASON_PLUGINS_OFF", "b")
    assert [p.name for p in plugins.load()] == ["a"]  # b never loads, for anyone


def test_serve_users(op, capsys):
    app, c = op
    from mason.server.app import print_users
    c.post("/api/v1/keys", json={"name": "k"}, headers=H)
    print_users(app.config["OP"])
    out = capsys.readouterr().out
    assert out.startswith("1 users, 1 sessions, 1 working API keys")
    assert "Mike" in out and "github:mike" in out and "1 keys" in out


def test_operator_panel(op, monkeypatch, capsys):
    app, mike = op
    from mason import plugins
    from mason.server import operators, security
    from mason.server.app import operator_command
    from mason.server.models import Identity, Session, User, db

    class Demo:
        name = "demo"
        def tui_tabs(self): return []  # noqa: E301,E704
        def tui_checks(self): return []  # noqa: E301,E704
        def status_columns(self): return []  # noqa: E301,E704
    monkeypatch.setattr(plugins, "load", lambda: [Demo()])
    with app.app_context():  # Ann, a second user with a browser session
        ann = User(name="Ann")
        db.add(ann)
        db.flush()
        db.add(Identity(user_id=ann.id, provider="github", host="github.com", uid="2", login="ann"))
        db.add(Session(id=security.sha256("ann-cookie"), user_id=ann.id, csrf="ann-csrf"))
        db.commit()
        ann_id = ann.id
    annc = app.test_client()
    annc.set_cookie("mason_session", "ann-cookie", domain="localhost")
    AH = {"X-CSRF-Token": "ann-csrf"}
    # nobody is an operator until `mason operator add`, and the web can't make one
    assert mike.get("/api/v1/operator").status_code == 403
    assert not mike.get("/api/v1/me").json["user"]["is_operator"]
    assert operator_command(app.config["OP"], "add", "github:nobody") == 1
    assert "no user signed in as github:nobody" in capsys.readouterr().err
    with app.app_context():
        assert "is an operator now" in operators.add("github:MIKE", note="runs it")
        assert "already" in operators.add("#1")
        assert operators.listing()[0].startswith("#1  Mike  github:mike")
    assert mike.get("/api/v1/me").json["user"]["is_operator"]
    got = mike.get("/api/v1/operator").json
    assert [u["name"] for u in got["users"]] == ["Mike", "Ann"] and got["users"][0]["operator"]
    assert got["stats"]["users"] == 2 and got["plugins"] == [{"name": "demo", "description": "", "off_for_all": False}]
    assert annc.get("/api/v1/operator").status_code == 403  # Ann isn't one
    key = mike.post("/api/v1/keys", json={"name": "k", "scope": "write"}, headers=H).json["key"]
    keyed = app.test_client()
    assert keyed.get("/api/v1/operator", headers={"Authorization": f"Bearer {key}"}).status_code == 403  # browser only
    # a plugin off for everyone is off for Ann too, and she can't switch it back on for herself
    assert mike.put("/api/v1/operator/plugins/demo", json={"on": False}, headers=H).json["plugins"][0]["off_for_all"]
    demo = annc.get("/api/v1/plugins").json["plugins"][0]
    assert not demo["on"] and demo["off_for_all"]
    annc.put("/api/v1/plugins/demo", json={"on": True}, headers=AH)
    assert not annc.get("/api/v1/plugins").json["plugins"][0]["on"]
    assert annc.put("/api/v1/operator/plugins/demo", json={"on": True}, headers=AH).status_code == 403
    mike.put("/api/v1/operator/plugins/demo", json={"on": True}, headers=H)
    assert annc.get("/api/v1/plugins").json["plugins"][0]["on"]
    # operators see accounts, never another user's settings, and can sign a user out everywhere
    assert "settings" not in got["users"][1] and "defaults" not in str(got["users"])
    assert mike.post(f"/api/v1/operator/users/{ann_id}/sign-out", headers=H).json == {"sessions": 1, "keys": 0}
    assert annc.get("/api/v1/me").json["user"] is None
    assert {a["action"] for a in mike.get("/api/v1/audit").json} >= {"operator.plugin", "operator.sign-out"}
    # removing takes effect at the next request
    assert operator_command(app.config["OP"], "remove", "mike") == 0
    assert mike.get("/api/v1/operator").status_code == 403


def test_tag_only(op):
    _, c = op
    assert c.get("/api/v1/release?repo=acme/plugin-b").json["publishes"] == ".github/workflows/release.yml"
    assert c.get("/api/v1/release?repo=acme/api").json["publishes"] == ""
    got = c.post("/api/v1/tags", json={"repo": "acme/plugin-b", "tag": "v0.4.0", "dry_run": True}, headers=H).json
    assert "[dry-run] push the tag v0.4.0 on main of acme/plugin-b; .github/workflows/release.yml" in got["text"]
    got = c.post("/api/v1/tags", json={"repo": "acme/plugin-a", "tag": "v1.0.0"}, headers=H).json
    assert not got["ok"] and "has a tag v1.0.0 already" in got["text"]
    assert c.post("/api/v1/tags", json={"repo": "acme/api", "tag": ""}, headers=H).status_code == 400
    assert any(a["action"] == "tag.create" for a in c.get("/api/v1/audit").json)
    got = c.post("/api/v1/tags", json={"repo": "acme/plugin-b", "tag": "v9.0.0", "dry_run": True}, headers=H).json
    assert "plugin.yaml says 0.4.0" in got["text"]
    page = c.get("/api/v1/release?repo=acme/plugin-b").json
    assert page["version"]["tag"] == "v0.4.0" and page["version"]["todo"]
    assert c.get("/api/v1/release?repo=acme/api").json["version"] is None


def test_bump_and_release_from_the_web(op):
    _, c = op
    got = c.post("/api/v1/bump", json={"repo": "acme/plugin-a", "level": "minor", "dry_run": True}, headers=H).json
    assert "1.0.0 -> 1.1.0" in got["text"] and "[dry-run] branch bump/v1.1.0" in got["text"]
    assert c.post("/api/v1/bump", json={"repo": "acme/plugin-a", "level": "huge"}, headers=H).status_code == 400
    got = c.post("/api/v1/release/version", json={"repo": "acme/plugin-b", "dry_run": True}, headers=H).json
    assert "[dry-run] push tag v0.4.0 on main" in got["text"]
    assert c.post("/api/v1/bump", json={"repo": "gitlab:g/p"}, headers=H).status_code == 400


def test_unreleased_versions_in_the_releases_list(op):
    _, c = op
    got = c.get("/api/v1/releases", headers=H).json
    rows = {r["repo"]: r for r in got["releases"]}
    b = rows["acme/plugin-b"]
    assert b["version"]["todo"] and b["pending"] == "0.4.0 unreleased"
    assert b["version"]["next"] == {"patch": "0.4.1", "minor": "0.5.0", "major": "1.0.0"}
    a = rows["acme/plugin-a"]
    assert not a["version"]["todo"] and a["version"]["pr"]["number"] == 12 and a["version"]["pr"]["version"] == "1.0.1"
    assert a["pending"] == "1.0.0 · bump #12 → 1.0.1"
    assert rows["mike/dotfiles"]["release"] == "-" and rows["mike/dotfiles"]["version"]["todo"]  # nothing released yet
    assert rows["acme/api"]["version"] is None  # no version file
    assert got["unreleased"] == 3
    only = {r["repo"] for r in c.get("/api/v1/releases?unreleased=1", headers=H).json["releases"]}
    assert only == {"acme/plugin-b", "acme/web", "mike/dotfiles"}


def test_secrets_names_and_set(op, monkeypatch, tmp_path):
    """A repo's wanted secrets by name; a value goes to GitHub encrypted and never into the audit log."""
    import base64
    import json

    from mason import sealedbox

    _, c = op
    log = tmp_path / "gh.log"
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    monkeypatch.setenv("FAKE_GH_OWN",
                       'secrets = ["NPM_TOKEN"]\n[environments.production]\nsecrets = ["DEPLOY_TOKEN"]\n')
    rows = c.get("/api/v1/repo/secrets?repo=mike/dotfiles").json["secrets"]
    assert {"env": None, "name": "NPM_TOKEN", "set": False, "wanted": True} in rows
    assert {"env": "production", "name": "DEPLOY_TOKEN", "set": True, "wanted": True} in rows
    r = c.post("/api/v1/repo/secrets", json={"repos": ["mike/dotfiles"], "name": "NPM_TOKEN", "value": "t0ken"},
               headers=H)
    assert r.json["ok"] and "set NPM_TOKEN in mike/dotfiles" in r.json["text"]
    body = json.loads(log.read_text().split("BODY ", 1)[1].splitlines()[0])
    assert sealedbox.open_box(base64.b64decode(body["encrypted_value"]), bytes(range(1, 33))) == b"t0ken"
    audit = c.get("/api/v1/audit").json
    assert "t0ken" not in json.dumps(audit) and "secret.set" in json.dumps(audit)
    assert c.post("/api/v1/repo/secrets", json={"repos": ["mike/dotfiles"], "name": "X", "value": ""},
                  headers=H).status_code == 400


def test_detail_pages_event_logs(op):
    _, c = op
    c.post("/api/v1/ready", json={"repo": "acme/web", "number": 7, "dry_run": True}, headers=H)
    c.post("/api/v1/ready", json={"repo": "acme/web", "number": 70, "dry_run": True}, headers=H)  # not #7's
    ev = c.get("/api/v1/events?repo=acme/web&kind=pr&number=7").json["events"]
    what = [e["what"] for e in ev]
    assert what[0] == "dry run: ready" and ev[0]["source"] == "mason" and ev[0]["who"] == "you via web"
    assert sum(e["source"] == "mason" for e in ev) == 1
    assert "subscribed" not in " ".join(what)  # noise is left out
    assert {"auto-merge on (squash)", "commented", "review: changes requested", "+label feature", "commit abc1234",
            "opened", "check test: failure"} <= set(what)
    by = {e["what"]: e for e in ev}
    assert by["review: changes requested"]["state"] == "bad" and by["check test: failure"]["detail"] == "took 1m 30s"
    assert by["commented"]["detail"] == "Added one." and "second commit" in by["commented"]["more"]
    assert [e["at"] for e in ev if e["source"] == "github"] == sorted(
        [e["at"] for e in ev if e["source"] == "github"], reverse=True)

    issue = [e["what"] for e in c.get("/api/v1/events?repo=acme/web&kind=issue&number=3").json["events"]]
    assert "opened" in issue and "check test: failure" not in issue

    repo = c.get("/api/v1/events?repo=acme/web&kind=repo").json["events"]
    what = [e["what"] for e in repo]
    assert {"pushed 2 commits to main", "merged PR #4", "created tag v1.0.0", "Sponsorship",
            "run CI: success"} <= set(what)
    assert next(e for e in repo if e["what"] == "pushed 2 commits to main")["detail"] == "Bump deps"
    assert any(e["source"] == "mason" for e in repo)  # the ready above is about acme/web too

    rel = c.get("/api/v1/events?repo=acme/plugin-a&kind=release&tag=v1.0.0").json["events"]
    assert {"published the release v1.0.0", "run Release: queued"} <= {e["what"] for e in rel}

    run = c.get("/api/v1/events?repo=acme/web&kind=run&id=9").json["events"]
    assert {"started by push", "job sign: failure", "step cosign: failure",
            "finished: failure"} <= {e["what"] for e in run}
    text = c.get("/api/v1/run?repo=acme/web&id=9").json["text"]
    assert "CI #41" in text and "took" not in text.split("\n")[0] and "- failure    cosign" in text
    assert "started" in text and "3m 5s" in text

    assert c.get("/api/v1/events?repo=acme/web&kind=pr").status_code == 400
    assert c.get("/api/v1/events?repo=acme/web&kind=nope").status_code == 400
    assert c.get("/api/v1/events?repo=acme/web&kind=release").status_code == 400
    text = c.post("/api/v1/run/rerun", json={"repo": "acme/web", "id": 9, "dry_run": True}, headers=H).json["text"]
    assert "[dry-run] POST /repos/acme/web/actions/runs/9/rerun-failed-jobs" in text
    run = c.get("/api/v1/events?repo=acme/web&kind=run&id=9").json["events"]
    assert run[0]["what"] == "dry run: rerun" and run[0]["source"] == "mason"


def test_repo_detail_has_info_for_the_status_header(op):
    """A repo page's header reads /repo's info (the text stays what the CLI prints)."""
    _, c = op
    got = c.get("/api/v1/repo?repo=acme/web").json
    assert got["text"].startswith("acme/web\n")
    info = got["info"]
    assert info["repo"] == "acme/web" and info["url"].endswith("/acme/web") and info["ci"] == "success"
    assert info["released"] == "" and info["group"] == "default"
    prs = {p["number"]: p for p in info["prs"]}
    assert set(prs) == {7, 8, 9}
    assert prs[8]["draft"] and prs[8]["merge"] == "draft" and prs[9]["merge"] == "conflicts"
    assert c.get("/api/v1/repo?repo=acme/api").json["info"]["released"] == "v1.10.0"


def test_mason_files_view(op, monkeypatch):
    """A repo's rules layer by layer: the defaults, the org's .mason, its own file; its files and live rulesets."""
    _, c = op
    monkeypatch.setenv("FAKE_GH_OWN", "[protect]\nchecks = [\"test\"]\n")
    v = c.get("/api/v1/mason?repo=mike/dotfiles").json
    assert v["kind"] == "repo" and v["settings_file"] == ".mason.toml" and v["own"]["protect"] == {"checks": ["test"]}
    assert v["protect"] == {"checks": ["test"]} and v["protect_from"] == "the repo"
    assert v["live_rulesets"] == ["main"] and v["protected_by"] == ["ruleset main"]
    assert [f["path"] for f in v["files"]] == [".mason.toml"] and v["files"][0]["editable"]
    assert v["layers"][0]["source"] == "acme/defaults" and v["layers"][-1]["source"] == "the repo"
    api = c.get("/api/v1/mason?repo=acme/api").json
    assert [f["path"] for f in api["files"]] == [".github/rulesets/release.json"]
    assert api["files"][0]["editable"] and api["protect"] is None  # .github/rulesets can be edited too
    assert "main" in api["layers"][0]["rulesets"]  # the defaults' rulesets folder


def test_mason_files_write(op, monkeypatch, tmp_path):
    _, c = op
    log = tmp_path / "gh.log"
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    r = c.post("/api/v1/mason/protect", json={"repo": "acme/web", "protect": {"reviews": "2", "checks": "test, lint",
                                                                              "signed_commits": True,
                                                                              "linear_history": False}}, headers=H)
    assert r.status_code == 200 and r.json["mode"] == "pr" and r.json["url"].endswith("/pull/99")
    calls = log.read_text()
    assert "-X PUT /repos/acme/web/contents/.mason/mason.toml" in calls and "pr create" in calls
    assert c.post("/api/v1/mason/protect", json={"repo": "acme/web", "protect": {"reviews": 99}},
                  headers=H).status_code == 400
    # paths a repo may hold, validated before writing
    assert c.put("/api/v1/mason/file", json={"repo": "acme/web", "path": "src/app.py", "text": "x"},
                 headers=H).status_code == 400
    bad = c.put("/api/v1/mason/file", json={"repo": "acme/web", "path": ".mason/rulesets/x.json", "text": "{"},
                headers=H)
    assert bad.status_code == 422 and "not valid JSON" in bad.json["problems"][0]
    bad = c.post("/api/v1/mason/validate", json={"repo": "acme/web", "path": ".mason.toml",
                                                 "text": 'match = { org = "x" }\nskip = ["nope"]\n'}, headers=H).json
    assert "doesn't take match" in bad["problems"][0] and "skip doesn't know nope" in bad["problems"][1]
    ok = c.put("/api/v1/mason/file", json={"repo": "acme/web", "path": ".mason.toml", "text": "auto_fix = true\n",
                                           "mode": "commit"}, headers=H).json
    assert ok["mode"] == "commit" and "pushed to the default branch" in ok["text"]
    saved = c.post("/api/v1/mason/save-live", json={"repo": "acme/api"}, headers=H).json
    assert saved["mode"] == "pr" and "-X PUT /repos/acme/api/contents/.mason/rulesets/main.json" in log.read_text()
    audit = json.dumps(c.get("/api/v1/audit").json)
    assert "mason.protect" in audit and "mason.save_live" in audit


def test_mason_files_auto_push_and_org_repo(op, monkeypatch, tmp_path):
    _, c = op
    log = tmp_path / "gh.log"
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    monkeypatch.setenv("FAKE_GH_OWN", "auto_push = true")
    r = c.post("/api/v1/mason/protect", json={"repo": "mike/dotfiles", "protect": False}, headers=H).json
    assert r["mode"] == "commit" and "pr create" not in log.read_text()  # auto_push: straight on main
    monkeypatch.setenv("FAKE_GH_PROTECTED", "1")  # main refuses pushes: a PR after all
    r = c.post("/api/v1/mason/protect", json={"repo": "mike/dotfiles", "protect": {"reviews": 1}}, headers=H).json
    assert r["mode"] == "pr"
    monkeypatch.setenv("FAKE_GH_MASON", "1")
    org = c.get("/api/v1/mason?repo=mike/.mason").json
    assert org["kind"] == "org" and [f["path"] for f in org["files"]] == ["mason.toml"]
    assert c.put("/api/v1/mason/file", json={"repo": "mike/.mason", "path": ".mason.toml", "text": ""},
                 headers=H).status_code == 400
    warn = c.post("/api/v1/mason/validate", json={"repo": "mike/.mason", "path": "mason.toml",
                                                  "text": 'orgs = ["x"]\n[[group]]\nname = "a"\n'}, headers=H).json
    assert "only [[group]] tables count" in warn["problems"][0]


def test_mason_files_dry_run(op, monkeypatch, tmp_path):
    _, c = op
    log = tmp_path / "gh.log"
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    r = c.post("/api/v1/mason/protect", json={"repo": "acme/web", "protect": {"reviews": 1}, "dry_run": True},
               headers=H).json
    assert r["dry"] and "[dry-run] write .mason/mason.toml in a pull request" in r["text"]
    assert "reviews = 1" in r["text"]
    assert "-X PUT" not in log.read_text() and "pr create" not in log.read_text()


def test_protect_written_into_a_repos_file():
    from mason import config
    from mason.server.api.masonfiles import with_protect

    text = ('# mine\nauto_fix = true\nprotect = { reviews = 1 }\n\n[release]\nversion = "x"\n\n'
            '[protect]\nchecks = ["a"]\n')
    out = with_protect(text, {"reviews": 2, "checks": ["test"], "signed_commits": True})
    assert out == ('# mine\nauto_fix = true\n\n[release]\nversion = "x"\n\n[protect]\nreviews = 2\n'
                   'checks = ["test"]\nsigned_commits = true\n')
    off = with_protect(out, False)
    assert config.parse_defaults(off) == {"auto_fix": True, "protect": False, "release": {"version": "x"}}
    assert "protect" not in config.parse_defaults(with_protect(off, None))
    assert with_protect("", {"reviews": 1}) == "[protect]\nreviews = 1\n"


def test_repo_settings_view(op, monkeypatch):
    """Every setting of a GitHub repo by area, read-only ones saying why, the lists, and what its file keeps."""
    _, c = op
    monkeypatch.setenv("FAKE_GH_OWN", "settings = { has_wiki = true }")
    v = c.get("/api/v1/repo/settings?repo=mike/dotfiles").json
    rows = {r["key"]: r for a in v["areas"] for r in a["rows"]}
    assert [a["name"] for a in v["areas"]][:3] == ["general", "features", "pull requests"]
    wiki = rows["has_wiki"]
    assert wiki["value"] is False and wiki["edit"] and wiki["keep"] == "settings.has_wiki"
    assert rows["sec.secret_scanning"]["value"] is True and rows["autofix.enabled"]["value"] is True
    assert rows["retention.days"]["value"] == 90 and rows["pvr.enabled"]["value"] is True
    assert rows["pages.on"]["value"] is False and rows["pages.cname"]["why"] == "Pages is off"
    assert rows["name"]["edit"] is False and "renaming" in rows["name"]["why"]
    assert rows["limits.limit"]["value"] == "none"
    lists = {x["key"]: x for x in v["lists"]}
    assert lists["environments"]["items"] == [{"name": "production", "detail": "wait timer"}]
    assert lists["collaborators"]["items"][1] == {"name": "ann", "detail": "write"}
    assert lists["hooks"]["error"] and lists["hooks"]["manage"].endswith("/mike/dotfiles/settings/hooks")
    assert v["file"] == ".mason.toml" and v["kept"] == {"settings.has_wiki": True}


def test_repo_settings_change_and_keep(op, monkeypatch, tmp_path):
    _, c = op
    log = tmp_path / "gh.log"
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    monkeypatch.setenv("FAKE_GH_BODIES", "1")
    bad = c.post("/api/v1/repo/settings", json={"repo": "acme/web", "changes": {"nope": 1}}, headers=H)
    assert bad.status_code == 400 and "isn't a github setting" in bad.json["error"]
    assert c.post("/api/v1/repo/settings", json={"repo": "acme/web", "changes": {"name": "x"}},
                  headers=H).status_code == 400  # read only
    assert c.post("/api/v1/repo/settings", json={"repo": "acme/web", "changes": {"merge_commit_title": "x"}},
                  headers=H).status_code == 400  # not one of the choices
    r = c.post("/api/v1/repo/settings", json={"repo": "acme/web", "changes": {
        "has_wiki": True, "sec.secret_scanning": True, "actions.allowed_actions": "local_only", "retention.days": "30",
        "alerts.enabled": False, "pages.on": True, "limits.limit": "contributors_only"}}, headers=H).json
    calls = log.read_text()
    assert '-X PATCH /repos/acme/web' in calls
    assert '"has_wiki": true' in calls and '"secret_scanning": {"status": "enabled"}' in calls
    assert '"allowed_actions": "local_only"' in calls and '"days": 30' in calls
    assert "-X DELETE /repos/acme/web/vulnerability-alerts" in calls and "-X POST /repos/acme/web/pages" in calls
    assert '"limit": "contributors_only", "expiry": "one_week"' in calls
    assert "contents/.mason" not in calls and "turned Pages on" in r["text"]
    # keep: the ones doctor knows go into the repo's own file, the rest is said
    log.write_text("")
    r = c.post("/api/v1/repo/settings", json={"repo": "mike/dotfiles", "keep": True, "changes": {
        "has_wiki": True, "sec.secret_scanning_push_protection": True, "description": "dots"}}, headers=H).json
    calls = log.read_text()
    assert "-X PUT /repos/mike/dotfiles/contents/.mason.toml" in calls and "pr create" in calls
    assert "not kept (doctor has no key for them): description" in r["text"]
    import base64
    put = next(json.loads(x[5:]) for x in calls.splitlines() if x.startswith("BODY ") and '"content"' in x)
    text = base64.b64decode(put["content"]).decode()
    from mason import config
    assert config.parse_defaults(text)["settings"] == {"has_wiki": True}
    assert config.parse_defaults(text)["security"] == {"secret_scanning_push_protection": "enabled"}
    assert config.parse_defaults(text)["release"]["version"] == "dots/__init__.py"
    assert "repo.settings" in json.dumps(c.get("/api/v1/audit").json)


def test_repo_settings_dry_run(op, monkeypatch, tmp_path):
    _, c = op
    log = tmp_path / "gh.log"
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    r = c.post("/api/v1/repo/settings", json={"repo": "acme/web", "dry_run": True, "keep": True,
                                              "changes": {"allow_squash_merge": False}}, headers=H).json
    assert "[dry-run] acme/web: set allow_squash_merge" in r["text"]
    assert "[dry-run] write .mason/mason.toml" in r["text"]
    assert "-X PATCH" not in log.read_text() and "-X PUT" not in log.read_text()


def test_merge_bypassing_the_rules(op, monkeypatch, tmp_path):
    """Bypass shows rule by rule whether you may; the merge passes --admin and is audited as a bypass."""
    _, c = op
    log = tmp_path / "gh.log"
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    b = c.get("/api/v1/pr/bypass?repo=acme/api&number=7").json
    assert b["base"] == "main" and not b["can"] and b["rules"] == [
        {"name": "main", "source": "acme/api", "can": False, "why": "you may not bypass it"}]
    monkeypatch.setenv("FAKE_GH_BYPASS", "always")
    assert c.get("/api/v1/pr/bypass?repo=acme/api&number=7").json["can"]
    assert not c.get("/api/v1/pr/bypass?repo=acme/web&number=7").json["can"]  # no rules: nothing to bypass
    monkeypatch.setenv("FAKE_GH_CLASSIC", "acme/web")  # classic protection, admins not included: an admin may
    b = c.get("/api/v1/pr/bypass?repo=acme/web&number=7").json
    assert b["can"] and b["rules"][0]["why"] == "you're an admin"
    r = c.post("/api/v1/merge", json={"targets": ["acme/web#7"], "bypass": True}, headers=H).json
    assert "merged, bypassing the branch rules" in r["text"]
    assert "pr merge 7 --repo acme/web --squash --delete-branch --admin" in log.read_text()
    assert "merge-bypass" in json.dumps(c.get("/api/v1/audit").json)
    assert c.post("/api/v1/merge", json={"bypass": True, "all": True}, headers=H).status_code == 400


def test_ignore_github_rulesets_and_edit_them(op, monkeypatch, tmp_path):
    _, c = op
    log = tmp_path / "gh.log"
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    v = c.get("/api/v1/mason?repo=acme/api").json
    assert v["files"][0]["editable"] and not v["github_rulesets_ignored"] and not v["files"][0]["ignored"]
    r = c.post("/api/v1/mason/skip", json={"repo": "acme/api", "check": "github_rulesets", "dry_run": True},
               headers=H).json
    assert 'skip = ["github_rulesets"]' in r["text"] and ".mason/mason.toml" in r["text"]
    assert c.post("/api/v1/mason/skip", json={"repo": "acme/api", "check": "nope"}, headers=H).status_code == 400
    ok = c.put("/api/v1/mason/file", json={"repo": "acme/api", "path": ".github/rulesets/release.json",
                                           "text": '{"name": "release", "target": "tag", "rules": []}\n'},
               headers=H).json
    assert ok["mode"] == "pr" and "-X PUT /repos/acme/api/contents/.github/rulesets/release.json" in log.read_text()
    monkeypatch.setenv("FAKE_GH_OWN", 'skip = ["github_rulesets"]')
    v = c.get("/api/v1/mason?repo=mike/dotfiles").json
    assert v["github_rulesets_ignored"]


def test_with_skip_keeps_the_rest():
    from mason import config
    from mason.server.api.masonfiles import with_skip

    text = '# mine\nauto_fix = true\n\n[protect]\nreviews = 1\n'
    on = with_skip(text, "github_rulesets", True)
    assert config.parse_defaults(on) == {"auto_fix": True, "skip": ["github_rulesets"], "protect": {"reviews": 1}}
    assert on.startswith("# mine\n")
    both = with_skip(with_skip(on, "protect", True), "github_rulesets", False)
    assert config.parse_defaults(both)["skip"] == ["protect"]
    assert with_skip('skip = ["protect"]\n', "protect", False) == ""


def test_move_or_remove_github_rulesets(op, monkeypatch, tmp_path):
    _, c = op
    log = tmp_path / "gh.log"
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    paths = [".github/rulesets/release.json"]
    r = c.post("/api/v1/mason/move", json={"repo": "acme/api", "paths": paths}, headers=H).json
    calls = log.read_text()
    assert r["mode"] == "pr" and "-X PUT /repos/acme/api/contents/.mason/rulesets/release.json" in calls
    assert "-X DELETE /repos/acme/api/contents/.github/rulesets/release.json" in calls
    log.write_text("")
    r = c.post("/api/v1/mason/move", json={"repo": "acme/api", "paths": paths, "remove": True}, headers=H).json
    calls = log.read_text()
    assert "-X DELETE /repos/acme/api/contents/.github/rulesets/release.json" in calls and "-X PUT" not in calls
    assert c.post("/api/v1/mason/move", json={"repo": "acme/api", "paths": [".mason.toml"]},
                  headers=H).status_code == 400
