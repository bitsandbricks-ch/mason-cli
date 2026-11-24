"""Exceptions with an expiry, doctor over time (mason doctor --save, mason drift) and the access review."""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys

from mason import history


def mason(env, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "mason", *args], env=env, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, timeout=60, check=False)


def test_exceptions(env, tmp_path):
    defaults = tmp_path / "defaults"
    defaults.mkdir()
    soon = (dt.date.today() + dt.timedelta(days=5)).isoformat()
    (defaults / "mason.toml").write_text(
        'orgs = ["acme"]\n[[group]]\nname = "all"\n'
        f'skip_until = {{ pages = 2001-01-01, code_scanning = {{ until = {soon}, reason = "CodeQL can\'t build it" }},'
        ' labels = 2999-01-01 }\n')
    env = {**env, "MASON_DEFAULTS": str(defaults)}
    out = mason(env, "exceptions", "web").stdout
    assert "ran out: checked again" in out and "ends in 5d" in out and "CodeQL can't build it" in out
    assert "3 exception(s): 1 ending within 30 days, 1 ran out" in out
    doc = json.loads(mason(env, "--json", "exceptions", "web").stdout)["result"]
    assert [e["check"] for e in doc] == ["pages", "code_scanning", "labels"]  # soonest first


def test_doctor_save_and_drift(env, tmp_path):
    hist = tmp_path / "history"
    env = {**env, "MASON_HISTORY": str(hist)}
    proc = mason(env, "doctor", "--save", "web", "plugin-b")
    assert proc.returncode == 0 and "saved" in proc.stdout, proc.stdout + proc.stderr
    assert "one run so far" in mason(env, "drift", "web", "plugin-b").stdout
    # an older run in which plugin-b had one problem fewer and web one more
    (saved,) = history.runs(str(hist))
    old = json.loads((hist / saved["file"]).read_text())
    old["when"] = "2026-01-01T00:00:00+00:00"
    old["repos"]["acme/plugin-b"]["problems"] = old["repos"]["acme/plugin-b"]["problems"][1:]
    old["repos"]["acme/web"]["problems"].append("SECRET.md is missing")
    (hist / "2026-01-01T000000.json").write_text(json.dumps(old))
    doc = json.loads(mason(env, "--json", "drift", "web", "plugin-b").stdout)["result"]
    assert doc["since"] == "2026-01-01T00:00:00+00:00"
    by = {c["repo"]: c for c in doc["changes"]}
    assert by["acme/plugin-b"]["new"] and by["acme/web"]["fixed"] == ["SECRET.md is missing"]
    assert [t["repos"] for t in doc["trend"]] == [2, 2]
    out = mason(env, "drift", "--dry-run", "--notify", "https://hooks.slack.com/x", "web", "plugin-b").stdout
    assert "[dry-run] would send" in out and "- fixed: SECRET.md is missing" in out


def test_compare_and_pick():
    a = {"when": "2026-01-01T00:00:00+00:00", "repos": {"x": {"problems": ["p1", "p2"]}, "gone": {"problems": ["q"]}}}
    b = {"when": "2026-01-09T00:00:00+00:00", "repos": {"x": {"problems": ["p2", "p3"]}}}
    assert history.compare(a, b) == [{"repo": "x", "new": ["p3"], "fixed": ["p1"]}]  # a repo no longer checked: quiet
    assert history.pick([a, b], 0) == (a, b) and history.pick([a, b], 30) == (a, b)
    assert history.pick([b], 0) == (None, b)


def test_access(env, tmp_path):
    out = mason(env, "access", "web", "--stale", "10").stdout
    assert "contractor" in out and "outside" in out and "ops" in out and "maintain" in out
    assert "deploy bot" in out and "WRITE" in out and "stale" in out
    assert "ci.acme.example" in out and "example/hook" not in out  # the host only: an address may carry a secret
    doc = json.loads(mason(env, "--json", "access", "web").stdout)["result"]
    (tmp_path / "review.json").write_text(json.dumps({"result": [{**doc[0], "people": doc[0]["people"][:1]}]}))
    doc = json.loads(mason(env, "--json", "access", "web", "--since", str(tmp_path / "review.json")).stdout)["result"]
    assert {p["login"]: p["new"] for p in doc[0]["people"]} == {"mike": False, "contractor": True, "reader": True}
    assert [p["login"] for p in json.loads(mason(env, "--json", "access", "web", "--writers").stdout)["result"][0]
            ["people"]] == ["mike", "contractor"]
