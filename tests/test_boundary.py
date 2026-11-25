"""Mason's core (the CLI and the TUI) and its web app add-on (mason.server and web/): the line between them.

The core never imports the add-on, and imports without Flask, SQLAlchemy or gunicorn installed; `mason serve`
is its only door to the add-on (cli.web_addon). The add-on uses the core through the modules that
docs/architecture.md lists. See issue #88.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC = ROOT / "src" / "mason"
ADDON = SRC / "server"
WEB_ONLY = ("flask", "werkzeug", "sqlalchemy", "gunicorn", "psycopg")

# Blocks the web add-on's libraries, as on a machine with only `pipx install mason-cli[tui]`.
BLOCK = f"""
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in {WEB_ONLY!r}:
            raise ImportError(f"No module named {{name!r}} (blocked by the test)")
        return None
sys.meta_path.insert(0, Block())
"""


def core_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if ADDON not in p.parents)


def imports(path: Path) -> list[tuple[str, str]]:
    """(module imported, the function it's imported in or '') for every import in a file."""
    found = []

    def visit(node, where):
        for child in ast.iter_child_nodes(node):
            inside = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else where
            if isinstance(child, ast.Import):
                found.extend((a.name, where) for a in child.names)
            elif isinstance(child, ast.ImportFrom) and child.module and not child.level:
                found.append((child.module, where))
                found.extend((f"{child.module}.{a.name}", where) for a in child.names)
            visit(child, inside)

    visit(ast.parse(path.read_text()), "")
    return found


def test_the_core_never_imports_the_web_addon():
    wrong = []
    for path in core_files():
        for module, where in imports(path):
            top = module.split(".")[0]
            addon = module == "mason.server" or module.startswith("mason.server.")
            if (addon and (path.name, where) != ("cli.py", "web_addon")) or top in WEB_ONLY:
                wrong.append(f"{path.relative_to(ROOT)}: {module} (in {where or 'the module'})")
    assert not wrong, "the core reaches into the web add-on:\n" + "\n".join(wrong)


def test_the_core_imports_without_the_web_addons_libraries():
    names = [p.stem for p in core_files() if p.stem not in ("__init__", "__main__", "tui")]  # tui needs textual
    code = BLOCK + "".join(f"import mason.{n}\n" for n in names) + "print('ok')"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False, timeout=60)
    assert proc.stdout.strip() == "ok", proc.stderr


def test_serve_without_the_addon_says_how_to_install_it(tmp_path):
    code = BLOCK + "from mason import cli\ncli.main(['serve', '--check'])"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False, timeout=60,
                          cwd=tmp_path)
    assert proc.returncode == 1
    assert "web app is an add-on" in proc.stderr and "mason-cli[tui,server]" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_the_core_modules_the_addon_uses_are_documented():
    used = set()
    for path in ADDON.rglob("*.py"):
        for module, _ in imports(path):
            parts = module.split(".")
            if parts[0] == "mason" and len(parts) > 1 and parts[1] != "server" and (SRC / f"{parts[1]}.py").is_file():
                used.add(parts[1])
    doc = (ROOT / "docs" / "architecture.md").read_text()
    missing = sorted(m for m in used if f"`mason.{m}`" not in doc)
    assert not missing, f"the web add-on uses core modules docs/architecture.md doesn't list: {missing}"
