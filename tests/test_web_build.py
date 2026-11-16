"""The built web UI: `mason serve` says how to build it when it's missing, and the build hook builds it."""

from __future__ import annotations

import sys

import pytest

pytest.importorskip("flask")
pytest.importorskip("sqlalchemy")
if sys.version_info < (3, 10):  # pragma: no cover
    pytest.skip("the operator needs Python 3.10+", allow_module_level=True)


@pytest.fixture()
def served(monkeypatch, tmp_path):
    """Run `mason serve` and `mason serve --check` with the UI in tmp_path/static, without starting a server."""
    from mason.server import app as A

    monkeypatch.delenv("MASON_URL", raising=False)
    monkeypatch.setenv("MASON_DATA", str(tmp_path))
    static = tmp_path / "static"
    static.mkdir()
    monkeypatch.setattr(A, "STATIC", static)

    class FakeApp:
        def run(self, **kw):
            pass

    monkeypatch.setattr(A, "create_app", lambda op: FakeApp())
    return static


def test_serve_says_how_to_build_a_missing_ui(served, capsys):
    from mason import cli

    cli.main(["serve"])
    err = capsys.readouterr().err
    assert "web UI isn't built" in err
    assert "cd web && npm ci && npm run build" in err
    with pytest.raises(SystemExit):
        cli.main(["serve", "--check"])
    assert "web ui       NOT BUILT: cd web && npm ci && npm run build" in capsys.readouterr().out


def test_serve_is_quiet_when_the_ui_is_built(served, capsys):
    from mason import cli

    (served / "index.html").write_text("<!doctype html>")
    cli.main(["serve"])
    assert "isn't built" not in capsys.readouterr().err
    with pytest.raises(SystemExit):
        cli.main(["serve", "--check"])
    assert "web ui       built" in capsys.readouterr().out


def test_browser_gets_the_build_hint(monkeypatch, tmp_path):
    from mason.server import app as A
    from mason.server import settings as S
    from mason.server import webui

    monkeypatch.setattr(A, "STATIC", tmp_path)
    settings = S.Settings(url="http://localhost:8080", data=tmp_path, database=f"sqlite:///{tmp_path / 'op.db'}",
                          secret_key="k" * 40,
                          github=S.Provider("github", "id", "", "https://github.com", "https://api.github.com", "repo"),
                          gitlab=S.Provider("gitlab", "", "", "https://gitlab.com", "https://gitlab.com/api/v4", "api"))
    resp = A.create_app(settings).test_client().get("/")
    assert resp.status_code == 503
    assert resp.get_data(as_text=True) == webui.BUILD_HINT


def test_a_file_of_an_older_build_is_gone_not_the_page(monkeypatch, tmp_path):
    # a tab open across an update asks for the old build's files: it must get a 404 (so it reloads), not
    # index.html as a script, and the 404 must not be cached for a year
    from mason.server import app as A
    from mason.server import settings as S

    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html>")
    (tmp_path / "assets" / "app-new.js").write_text("export {}")
    monkeypatch.setattr(A, "STATIC", tmp_path)
    settings = S.Settings(url="http://localhost:8080", data=tmp_path, database=f"sqlite:///{tmp_path / 'op.db'}",
                          secret_key="k" * 40,
                          github=S.Provider("github", "id", "", "https://github.com", "https://api.github.com", "repo"),
                          gitlab=S.Provider("gitlab", "", "", "https://gitlab.com", "https://gitlab.com/api/v4", "api"))
    client = A.create_app(settings).test_client()
    new = client.get("/assets/app-new.js")
    assert new.status_code == 200
    assert "immutable" in new.headers["Cache-Control"]
    old = client.get("/assets/app-old.js")
    assert old.status_code == 404
    assert "immutable" not in old.headers.get("Cache-Control", "")
    page = client.get("/prs")
    assert page.status_code == 200
    assert page.headers["Cache-Control"] == "no-cache"
