"""Which repos a group takes: `match.org` for GitHub orgs and GitLab groups, and org filters (`acme/`)."""

from __future__ import annotations

import sys

import pytest

from mason import config
from mason.config import Config, Group, group_label, orgs_of


def cfg(*groups: Group) -> Config:
    return Config(source=None, orgs=["acme"], repos=[], exclude=[], groups=list(groups), org_defaults=False)


def test_match_org_ignores_case_on_github():
    g = Group("acme", match={"org": "Acme"})
    assert g.matches("acme/web") and g.matches("ACME/api")
    assert not g.matches("acme-labs/web") and not g.matches("other/acme")


def test_match_org_takes_gitlab_subgroups():
    top, sub = Group("top", match={"org": "grp"}), Group("sub", match={"org": "grp/sub"})
    assert top.matches("gitlab:grp/x") and top.matches("gitlab:grp/sub/y")
    assert sub.matches("gitlab:grp/sub/y") and sub.matches("gitlab:grp/sub/deeper/z")
    assert not sub.matches("gitlab:grp/x") and not sub.matches("gitlab:grp/subway/x")


def test_org_filter_takes_every_repo_of_the_org_grouped_or_not():
    c = cfg(Group("plugins", match={"org": "acme", "prefix": "plugin-"}))  # no catch-all: acme/web has no group
    assert c.group_of("acme/web") is None
    assert c.in_group("acme/web", "acme/") and c.in_group("acme/plugin-a", "acme/")
    assert c.in_group("Acme/web", "acme/")
    assert not c.in_group("mike/dotfiles", "acme/") and not c.in_group("gitlab:acme/x", "acme/")
    assert c.in_group("acme/plugin-a", "plugins") and not c.in_group("acme/web", "plugins")
    assert c.in_group("gitlab:grp/sub/p", "gitlab:grp/") and c.in_group("gitlab:grp/sub/p", "gitlab:grp/sub/")
    assert not c.in_group("gitlab:grp/p", "gitlab:grp/sub/") and not c.in_group("grp/p", "gitlab:grp/")


def test_group_names_stay_groups():
    c = cfg(Group("acme:default"), Group("rest", match={"org": "other"}))
    assert c.in_group("acme/web", "acme:default") and not c.in_group("acme/web", "rest")
    assert config.org_filter("rest") is None and config.org_filter("/") is None


def test_groups_stack_all_then_prefix_then_full_name():
    """Every group that matches applies; the more specific one wins key by key, lists add up."""
    c = cfg(Group("one", match={"repos": ["acme/plugin-pay"]}, settings={"has_wiki": True}, pages={"cname": "pay.x"}),
            Group("plugins", match={"prefix": "plugin-"}, settings={"has_wiki": False, "has_issues": False},
                  topics=["plugin"], pages={"build": "workflow"}, secrets=["SIGN_KEY"]),
            Group("all", settings={"delete_branch_on_merge": True}, topics=["acme"], immutable_releases=True,
                  environments={"production": {"wait": 5}}))
    g = c.group_of("acme/plugin-pay")
    assert g.name == "one" and [x.name for x in g.layers] == ["all", "plugins", "one"]
    assert g.settings == {"delete_branch_on_merge": True, "has_wiki": True, "has_issues": False}
    assert g.topics == ["acme", "plugin"] and g.secrets == ["SIGN_KEY"] and g.immutable_releases is True
    assert g.pages == {"build": "workflow", "cname": "pay.x"} and g.environments == {"production": {"wait": 5}}
    assert c.group_of("acme/plugin-b").name == "plugins" and c.group_of("acme/web").name == "all"
    assert c.in_group("acme/plugin-pay", "all") and c.in_group("acme/plugin-pay", "plugins")
    assert c.group_of("acme/web").layers == []  # one group: itself
    c.groups[1].inherit = False  # plugins stand alone: "all" doesn't stack under them
    assert [x.name for x in c.group_of("acme/plugin-pay").layers] == ["plugins", "one"]


def test_a_repos_own_file_wins(monkeypatch):
    c = cfg(Group("all", settings={"has_wiki": False, "has_issues": True}, topics=["acme"]))
    own = {"acme/site": 'topics = ["web"]\nsecrets = ["CF_TOKEN"]\n[settings]\nhas_wiki = true\n'
                        '[pages]\ncname = "acme.ch"\n[release]\nversion = "VERSION"\n'}
    monkeypatch.setattr(config, "file_on", lambda repo, path, ref=None: own.get(repo))
    monkeypatch.setattr(config, "_repo_loaded", {})
    g = c.settings_of("acme/site")
    assert g.name == "all" and g.settings == {"has_wiki": True, "has_issues": True}
    assert g.topics == ["acme", "web"] and g.secrets == ["CF_TOKEN"] and g.pages == {"cname": "acme.ch"}
    assert c.settings_of("acme/api").settings == {"has_wiki": False, "has_issues": True}  # no own file
    assert cfg().settings_of("acme/site").name == ".mason.toml"  # no group: the file alone


def test_group_label_falls_back_to_the_org():
    assert group_label(Group("plugins"), "acme/plugin-a") == "plugins"
    assert group_label(None, "acme/web") == "acme/"
    assert group_label(None, "gitlab:grp/sub/p") == "gitlab:grp/sub/"
    assert group_label(None, "odd") == "-"


def test_orgs_of():
    assert orgs_of("acme/web") == ["acme/"]
    assert orgs_of("gitlab:a/b/p") == ["gitlab:a/", "gitlab:a/b/"]


@pytest.mark.skipif(sys.version_info < (3, 10), reason="the operator needs Python 3.10+")
def test_gitlab_group_filter_uses_topics(monkeypatch):
    pytest.importorskip("flask")
    pytest.importorskip("sqlalchemy")
    """A group that matches GitLab projects on topics keeps them when the list is filtered by it."""
    from flask import Flask

    from mason.server.api import repos as api

    c = cfg(Group("tagged", match={"provider": "gitlab", "topics": ["svc"]}))
    projects = {"gitlab:g/a": {"topics": ["svc"]}, "gitlab:g/b": {"topics": []}}
    monkeypatch.setattr(api, "gitlab_projects", lambda gl, cfg: projects)
    with Flask(__name__).test_request_context("/?provider=gitlab"):
        assert api.all_repos(c, None, object(), group="tagged")[1] == ["gitlab:g/a"]
        assert api.all_repos(c, None, object(), group="gitlab:g/")[1] == ["gitlab:g/a", "gitlab:g/b"]


def test_auto_keys_stack_and_the_repo_wins(monkeypatch):
    c = cfg(Group("all", auto_push=True, auto_merge=True))
    own = {"acme/site": "auto_push = false\nauto_fix = true\n"}
    monkeypatch.setattr(config, "file_on", lambda repo, path, ref=None: own.get(repo))
    monkeypatch.setattr(config, "_repo_loaded", {})
    monkeypatch.setattr("mason.repos.listing", lambda cfg: {})
    assert [config.auto(c, "acme/site", k) for k in config.AUTO] == [True, False, True]
    assert [config.auto(c, "acme/api", k) for k in config.AUTO] == [False, True, True]
    assert not config.auto(cfg(), "acme/api", "auto_push")
