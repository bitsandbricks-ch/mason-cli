"""The checkout you're in: which GitHub repo or GitLab project its `origin` remote points at.

With no repo names, commands run on this checkout's repo (`--all`: every repo, as before). `.` names it
anywhere a repo name goes, `#12` is its PR 12. MASON_HERE=0 turns the guess off (`.` still works).
Works offline: it reads the remote's URL with git, nothing is asked of GitHub or GitLab.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

# git@host:owner/name.git, ssh://git@host[:port]/owner/name, https://host/owner/name(.git)
SCP = re.compile(r"^(?:[^@/]+@)?(?P<host>[^:/]+):(?P<path>[^/].*)$")


def local() -> bool:
    """On your own machine: never in the web app, whose working folder is nobody's checkout."""
    from mason import config, core
    return not core.SERVING and config.OVERRIDE.get() is None


def enabled() -> bool:
    return local() and (os.environ.get("MASON_HERE") or "1").strip().lower() not in ("0", "off", "false", "no")


def git(*args: str, cwd: Path | str | None = None) -> str | None:
    """git's answer, or None when git is missing or says no (not a checkout, no such remote ...)."""
    try:
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def root(cwd: Path | str | None = None) -> Path | None:
    """The top folder of the checkout `cwd` is in (None outside one)."""
    top = git("rev-parse", "--show-toplevel", cwd=cwd)
    return Path(top) if top else None


def remote_url(cwd: Path | str | None = None) -> str | None:
    """origin's URL, else the first remote's."""
    url = git("remote", "get-url", "origin", cwd=cwd)
    if url:
        return url
    first = (git("remote", cwd=cwd) or "").split()
    return git("remote", "get-url", first[0], cwd=cwd) if first else None


def gitlab_hosts() -> set[str]:
    hosts = {"gitlab.com"}
    for url in (os.environ.get("GITLAB_URL"), os.environ.get("GITLAB_HOST")):
        if url:
            hosts.add(urlparse(url if "://" in url else f"https://{url}").hostname or url)
    try:
        from mason import config
        if config.user_config().get("gitlab_url"):
            hosts.add(urlparse(config.user_config()["gitlab_url"]).hostname or "")
    except RuntimeError:  # a broken config file: say so where it's read for real
        pass
    return {h.lower() for h in hosts if h}


def parse_remote(url: str, gitlab: set[str] | None = None) -> str | None:
    """owner/name for a GitHub remote, gitlab:group/sub/name for a GitLab one, None for anything else."""
    url = url.strip()
    if "://" in url:
        u = urlparse(url)
        host, path = (u.hostname or "").lower(), u.path
    else:
        m = SCP.match(url)
        if not m:
            return None
        host, path = m.group("host").lower(), m.group("path")
    path = path.strip("/").removesuffix(".git").strip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return None
    gitlab = gitlab_hosts() if gitlab is None else gitlab
    # ssh host aliases (github.com-work) keep the real host in front
    if host == "github.com" or host.startswith("github.com-") or host == (os.environ.get("GH_HOST") or "").lower():
        return "/".join(parts[:2]) if len(parts) == 2 else None
    if host in gitlab or "gitlab" in host:
        return "gitlab:" + "/".join(parts)
    return None


def repo(cwd: Path | str | None = None) -> str | None:
    """This checkout's repo (owner/name or gitlab:group/name), None outside a checkout or for other hosts."""
    url = remote_url(cwd)
    return parse_remote(url) if url else None


def need(cwd: Path | str | None = None) -> str:
    found = repo(cwd)
    if found:
        return found
    if root(cwd) is None:
        raise RuntimeError("Not in a git checkout: name the repo, or cd into one")
    url = remote_url(cwd) or "no remote"
    raise RuntimeError(f"This checkout's remote isn't a GitHub repo or GitLab project: {url}")


def default_names(names: list[str], every: bool) -> list[str]:
    """The repo names a command runs on: `.` becomes this checkout's repo; no names (and not --all) in a
    checkout means only its repo."""
    if not local():
        return list(names)
    out = []
    for n in names:
        if n == "." or n.startswith(".#"):
            out.append(need() + n[1:])
        elif n.startswith("#") and n[1:].isdigit():
            out.append(need() + n)
        else:
            out.append(n)
    if out or every or not enabled():
        return out
    found = repo()
    return [found] if found else []
