"""The settings catalog (mason/catalog.py): checking a change, writing it into a repo's .mason.toml, the CLI."""

from __future__ import annotations

import subprocess
import sys

import pytest

from mason import catalog, config


def test_keys_are_unique_and_keep_paths_are_doctor_keys():
    for provider in ("github", "gitlab"):
        keys = [s.key for a in catalog.catalog(provider) for s in a.settings]
        assert len(keys) == len(set(keys)), provider
        for a in catalog.catalog(provider):
            for s in a.settings:
                if s.keep:
                    top = s.keep.split(".")[0]
                    assert top in config.REPO_KEYS or top == "gitlab", s.key
                if s.keep.startswith("settings."):
                    from mason.defaults import REPO_SETTINGS
                    assert s.keep.split(".")[1] in REPO_SETTINGS, s.key  # doctor reads it back
    srcs = {s.src for a in catalog.GITHUB for s in a.settings}
    assert srcs <= set(catalog.SOURCES)


def test_clean_checks_kinds():
    got = catalog.clean("github", {"has_wiki": "off", "retention.days": "30", "topics": "a, b,", "homepage": " x "})
    assert got == {"has_wiki": False, "retention.days": 30, "topics": ["a", "b"], "homepage": "x"}
    for bad in ({"has_wiki": "maybe"}, {"retention.days": "-1"}, {"visibility": "secret"}, {"fork": True}, {}):
        with pytest.raises(ValueError):
            catalog.clean("github", bad)
    assert catalog.clean("gitlab", {"merge_method": "ff", "cleanup.keep_n": "10"}) == {"merge_method": "ff",
                                                                                       "cleanup.keep_n": "10"}


def test_keep_text_keeps_the_rest():
    text = ('# mine\nauto_fix = true\nsettings = { has_wiki = false }\n\n[release]\nversion = "x"\n\n'
            '[actions]\nenabled = true\n')
    values = catalog.kept("github", {"allow_squash_merge": False, "retention.days": 30, "homepage": "https://x",
                                     "sec.secret_scanning": True, "description": "not kept"})
    out = catalog.keep_text(text, values)
    assert out.startswith("# mine\nauto_fix = true\nhomepage = \"https://x\"\n\n[release]\nversion = \"x\"\n")
    assert config.parse_defaults(out) == {
        "auto_fix": True, "homepage": "https://x", "release": {"version": "x"},
        "settings": {"has_wiki": False, "allow_squash_merge": False},
        "actions": {"enabled": True, "retention_days": 30}, "security": {"secret_scanning": "enabled"}}
    gl = catalog.keep_text("[gitlab]\nprotected_branches = { main = { push_access_level = 0 } }\n",
                           catalog.kept("gitlab", {"merge_method": "ff", "approvals.reset_approvals_on_push": True}))
    assert config.parse_defaults(gl) == {"gitlab": {"protected_branches": {"main": {"push_access_level": 0}},
                                                    "settings": {"merge_method": "ff"}}}
    assert catalog.keep_text("", {("pages", "https"): True}) == "[pages]\nhttps = true\n"
    assert config.parse_defaults(catalog.keep_text("pages = true\n", {("pages", "cname"): "a.ch"})) == {
        "pages": {"cname": "a.ch"}}


class FakeGitLab:
    def __init__(self):
        self.calls = []

    def project(self, repo):
        return "/projects/g%2Fp"

    def api(self, method, path, body=None):
        if path == "/projects/g%2Fp?license=true":
            return {"web_url": "https://gitlab.com/g/p", "merge_method": "merge", "issues_access_level": "enabled",
                    "container_expiration_policy": {"enabled": False, "keep_n": 10, "cadence": "1d"}, "archived": False}
        if path.endswith("/push_rule"):
            from mason.transport import HttpError
            raise HttpError("404 Not Found", 404)
        if path.endswith("/approvals"):
            return {"reset_approvals_on_push": True}
        if path.endswith("/job_token_scope"):
            return {"inbound_enabled": True}
        return {}

    def pages(self, path, limit=2000):
        if path.endswith("/members"):
            return [{"username": "mike", "access_level": 50}]
        if path.endswith("/protected_branches"):
            return [{"name": "main", "push_access_levels": [{"access_level": 40}],
                     "merge_access_levels": [{"access_level": 30}]}]
        return []

    def write(self, method, path, body=None):
        self.calls.append((method, path, body))


def test_gitlab_read_and_write():
    gl = FakeGitLab()
    got = catalog.read_gitlab(gl, "gitlab:g/p")
    rows = {r["key"]: r for a in got["areas"] for r in a["rows"]}
    assert rows["merge_method"]["value"] == "merge" and rows["merge_method"]["edit"]
    assert rows["cleanup.keep_n"]["value"] == "10" and rows["jobtoken.inbound_enabled"]["value"] is True
    assert "Premium" in rows["push.prevent_secrets"]["why"] and not rows["push.prevent_secrets"]["edit"]
    assert "not offered" in rows["lfs_enabled"]["why"]  # this GitLab didn't answer it
    lists = {x["key"]: x for x in got["lists"]}
    assert lists["members"]["items"] == [{"name": "mike", "detail": "owner"}]
    assert lists["protected_branches"]["items"][0]["detail"] == "push: maintainer · merge: developer"
    said = catalog.write_gitlab(gl, "gitlab:g/p", catalog.clean("gitlab", {
        "merge_method": "ff", "cleanup.enabled": True, "cleanup.keep_n": "5", "archived": True,
        "approvals.reset_approvals_on_push": False, "jobtoken.inbound_enabled": False}))
    assert gl.calls == [
        ("PUT", "/projects/g%2Fp", {"merge_method": "ff",
                                   "container_expiration_policy_attributes": {"enabled": True, "keep_n": 5}}),
        ("POST", "/projects/g%2Fp/archive", None),
        ("POST", "/projects/g%2Fp/approvals", {"reset_approvals_on_push": False}),
        ("PATCH", "/projects/g%2Fp/job_token_scope", {"enabled": False})]
    assert said[1] == "archived it"


def test_cli_settings(env):
    def run(*a):
        return subprocess.run([sys.executable, "-m", "mason", *a], env=env, capture_output=True, text=True, check=False)

    shown = run("settings", "mike/dotfiles", "pull", "--keys")
    assert shown.returncode == 0, shown.stderr
    assert "pull requests" in shown.stdout and "[allow_squash_merge]" in shown.stdout
    assert "\nactions" not in shown.stdout
    changed = run("settings", "acme/web", "has_wiki=on", "pages.https_enforced=off", "--dry-run")
    assert "[dry-run] acme/web: set has_wiki" in changed.stdout, changed.stderr
    assert "failed: Pages: Pages is off: turn it on first" in changed.stdout and changed.returncode == 1
    bad = run("settings", "acme/web", "nope=1")
    assert bad.returncode != 0 and "isn't a github setting" in bad.stderr


def test_docs_list_every_setting():
    from pathlib import Path

    doc = (Path(__file__).parent.parent / "docs" / "settings.md").read_text()
    for provider in ("github", "gitlab"):
        for a in catalog.catalog(provider):
            for s in a.settings:
                assert f"`{s.key}`" in doc, s.key
