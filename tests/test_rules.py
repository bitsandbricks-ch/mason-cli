"""The shorter repo keys (config.MORE): what they generate, how they stack, and `mason auto`'s helpers."""

from __future__ import annotations

import datetime as dt

import pytest

from mason import auto, config, rules
from mason.config import Config, Group


def test_protect_becomes_a_ruleset():
    rs = rules.protect_ruleset({"reviews": 1, "checks": ["test"], "signed_commits": True, "merge_queue": True,
                                "branches": ["main", "release/*"]})
    assert rs["name"] == "protect" and rs["conditions"]["ref_name"]["include"] == ["refs/heads/main",
                                                                                 "refs/heads/release/*"]
    kinds = {r["type"]: r.get("parameters") for r in rs["rules"]}
    assert kinds["pull_request"]["required_approving_review_count"] == 1
    assert kinds["required_status_checks"]["required_status_checks"] == [{"context": "test"}]
    assert "required_signatures" in kinds and kinds["merge_queue"]["merge_method"] == "SQUASH"
    assert rules.protect_ruleset({})["conditions"]["ref_name"]["include"] == ["~DEFAULT_BRANCH"]


def test_generated_files():
    files = rules.generated_files({"dependabot": {"ecosystems": ["pip", "github-actions"], "interval": "daily"},
                                   "renovate": True, "codeowners": {"*": ["@mike"], "/docs/": "@acme/docs"},
                                   "release_notes": {"exclude": ["chore"]}})
    dep = files[".github/dependabot.yml"]
    assert 'package-ecosystem: "pip"' in dep and 'package-ecosystem: "github-actions"' in dep
    assert 'interval: "daily"' in dep
    assert '"config:recommended"' in files["renovate.json"]
    assert "* @mike\n/docs/ @acme/docs\n" in files[".github/CODEOWNERS"]
    assert '- "chore"' in files[".github/release.yml"] and 'title: "Features"' in files[".github/release.yml"]
    assert rules.generated_files({"dependabot": {"enabled": False}, "renovate": False}) == {}


def want(**more) -> dict:
    return {"more": more, "skip": set(), "rulesets": {}, "files": {}, "texts": {}, "required_files": []}


def test_prepare_skips_until_a_day_then_checks_again():
    soon = dt.date.today() + dt.timedelta(days=3)
    w = rules.prepare(want(skip_until={"code_scanning": soon, "pages": "2020-01-01"}, templates=True,
                           protect={"reviews": 2}, codeowners={"*": ["@mike"]}))
    assert "code_scanning" in w["skip"] and "pages" not in w["skip"]
    assert w["expired_skips"] == ["skip of pages ran out on 2020-01-01: it's checked again"]
    assert "protect" in w["rulesets"] and w["generated_rulesets"] == {"protect"}
    assert ".github/CODEOWNERS" in w["files"] and ".github/CODEOWNERS" in w["texts"]
    assert len(w["required_files"]) == 2


def test_more_keys_stack_and_the_repo_wins(monkeypatch):
    c = Config(source=None, orgs=["acme"], repos=[], exclude=[], org_defaults=False,
               groups=[Group("all", more={"owner": "ann", "discussions": ["Q&A"], "protect": {"reviews": 1}})])
    own = {"acme/site": 'owner = "mike"\ndiscussions = ["Ideas"]\nauto_close_stale = 30\n[protect]\nchecks = ["t"]\n'}
    monkeypatch.setattr(config, "file_on", lambda repo, path, ref=None: own.get(repo))
    monkeypatch.setattr(config, "_repo_loaded", {})
    monkeypatch.setattr("mason.repos.listing", lambda cfg: {})
    m = config.more_of(c, "acme/site")
    assert m["owner"] == "mike" and m["discussions"] == ["Q&A", "Ideas"] and m["auto_close_stale"] == 30
    assert m["protect"] == {"reviews": 1, "checks": ["t"]}
    assert config.more_of(c, "acme/api")["owner"] == "ann"
    with pytest.raises(RuntimeError, match="protect must be a table"):
        config.make_group({"name": "x", "protect": 3}, 0)


def test_bump_kind():
    assert auto.bump_kind("Bump requests from 2.31.0 to 2.31.1") == "patch"
    assert auto.bump_kind("chore(deps): bump x from 1.2 to 1.3") == "minor"
    assert auto.bump_kind("Bump django from 4.2.0 to 5.0.0") == "major"
    assert auto.bump_kind("Update the README") is None


class StubGitLab:
    """Just enough of server.gitlab.GitLab for doctor and sync."""

    def __init__(self, own: str):
        self.own, self.calls = own, []

    def project(self, repo):
        return "/projects/acme%2Fsite"

    def file(self, repo, path, ref=None):
        return self.own if path == ".mason.toml" else None

    def api(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path.endswith("/protected_branches"):
            return []
        return {"default_branch": "main", "squash_option": "never"}

    def blobs(self, repo, ref=None):
        return {}

    def write(self, method, path, body=None):
        self.calls.append((method, path, body))


def test_a_gitlab_projects_own_mason_toml(capsys):
    from mason.server import gitlab as GL

    c = Config(source=None, orgs=[], repos=[], exclude=[], org_defaults=False, groups=[])
    gl = StubGitLab('auto_fix = true\n[gitlab.settings]\nsquash_option = "always"\n')
    GL.doctor(gl, c, "gitlab:acme/site")
    out = capsys.readouterr().out
    assert "squash_option is never, .mason.toml has always" in out and "(its .mason.toml)" in out
    GL.doctor(gl, c, "gitlab:acme/site", auto=True)
    assert "auto_fix: fixing what drifted" in capsys.readouterr().out
    assert ("PUT", "/projects/acme%2Fsite", {"squash_option": "always"}) in gl.calls
    assert GL.auto_of(StubGitLab("auto_push = true\n"), c, "gitlab:acme/site", "auto_push")
    assert not GL.auto_of(StubGitLab(""), c, "gitlab:acme/site", "auto_push")


def test_alerts_send_only_whats_new(monkeypatch, tmp_path, capsys):
    sent = []

    class Answer:
        def close(self):
            pass

    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    monkeypatch.setattr(auto.urllib.request, "urlopen", lambda req, timeout: sent.append(req) or Answer())
    auto.alert("acme/web", "https://discord.com/api/webhooks/1/x", ["a is off", "b is missing"])
    auto.alert("acme/web", "https://discord.com/api/webhooks/1/x", ["a is off", "b is missing", "c drifted"])
    auto.alert("acme/web", "https://discord.com/api/webhooks/1/x", ["c drifted"])
    assert len(sent) == 2 and b"c drifted" in sent[1].data and b"a is off" not in sent[1].data
    assert b'"content"' in sent[0].data  # Discord's shape
    auto.alert("acme/web", "http://example.com/hook", ["d"])
    assert "must start with https://" in capsys.readouterr().out and len(sent) == 2


def test_targets_the_default_branch():
    rs = rules.protect_ruleset({})
    assert rules.targets(rs, "main")
    assert rules.targets(rules.protect_ruleset({"branches": ["main"]}), "main")
    assert not rules.targets(rules.protect_ruleset({"branches": ["release/*"]}), "main")
    assert rules.targets(rules.protect_ruleset({"branches": ["release/*"]}), "release/1")
    assert not rules.targets({**rs, "enforcement": "disabled"}, "main")
    assert not rules.targets({"target": "tag", "conditions": {"ref_name": {"include": ["~ALL"]}}}, "main")
    assert rules.targets({"name": "main", "rules": []}, "main")  # a defaults ruleset without conditions
    assert not rules.targets({"conditions": {"ref_name": {"include": ["~ALL"], "exclude": ["refs/heads/main"]}}},
                             "main")


def test_a_repo_can_turn_the_groups_protect_off():
    from mason import defaults

    group = rules.prepare(want(protect={"reviews": 1}))
    assert "protect" in group["rulesets"]
    group["label"], group["group"] = "defaults", "default"
    for own in (Group(".mason.toml", more={"protect": {"enabled": False}}), Group(".mason.toml", skip=["protect"])):
        assert "protect" not in defaults.overlay(group, own)["rulesets"]
    mine = defaults.overlay(group, Group(".mason.toml", more={"protect": {"checks": ["test"]}}))["rulesets"]["protect"]
    kinds = {r["type"] for r in mine["rules"]}
    assert {"pull_request", "required_status_checks"} <= kinds  # the group's reviews and the repo's checks


def test_default_branch_protection_check(monkeypatch):
    answers = {}
    monkeypatch.setattr(rules, "_get", lambda path: answers.get(path))
    state = {"default_branch": "main"}
    w = {**want(), "label": "defaults"}
    found = rules._default_protected("acme/web", state, w)
    assert found and "the default branch main isn't protected" in found[0].text and not found[0].area
    answers["/repos/acme/web/branches/main"] = {"protected": True}  # classic branch protection counts
    assert rules._default_protected("acme/web", state, w) == []
    assert rules.protection_of("acme/web", "main") == ["branch protection"]
    answers["/repos/acme/web/rules/branches/main"] = [
        {"type": "deletion", "ruleset_source_type": "Organization", "ruleset_source": "acme", "ruleset_id": 7}]
    assert rules.protection_of("acme/web", "main") == ["ruleset 7 of acme"]  # an org ruleset counts too
    answers.clear()
    w["rulesets"] = {"protect": rules.protect_ruleset({})}  # wanted: the ruleset check reports and fixes it
    assert rules._default_protected("acme/web", state, w) == []


def test_gitlab_protect_protects_the_default_branch(capsys):
    from mason.server import gitlab as GL

    c = Config(source=None, orgs=[], repos=[], exclude=[], org_defaults=False,
               groups=[Group("all", more={"protect": {"reviews": 1}})])
    gl = StubGitLab("")
    GL.doctor(gl, c, "gitlab:acme/site", fix=True)
    assert "1 protected branches" in capsys.readouterr().out
    assert ("POST", "/projects/acme%2Fsite/protected_branches",
            {"name": "main", "push_access_level": 0, "merge_access_level": 30}) in gl.calls
    bare = Config(source=None, orgs=[], repos=[], exclude=[], org_defaults=False, groups=[Group("all")])
    GL.doctor(StubGitLab(""), bare, "gitlab:acme/site")
    assert "the default branch main isn't protected" in capsys.readouterr().out
    GL.doctor(StubGitLab('skip = ["protect"]'), bare, "gitlab:acme/site")
    assert "isn't protected" not in capsys.readouterr().out

