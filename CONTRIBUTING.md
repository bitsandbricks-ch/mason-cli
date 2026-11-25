# Contributing to Mason

Thanks for helping. Mason follows the [BitsAndBricks handbook](https://github.com/bitsandbricks-ch/handbook)
(profile `multi-tool`); [AGENTS.md](AGENTS.md) lists what is specific to this repo, for people and coding
agents alike.

## Set up

```sh
pip install -e ".[dev,docs]"
cd web && npm ci
```

Python 3.12 or newer, and Node.js for the web UI.

## Before you open a pull request

Run what CI runs:

```sh
ruff check .
pytest -q                          # against tests/fake_gh and tests/fake_glab, never the real APIs
mkdocs build --strict              # the docs/ site
cd web && npm run build && npm test
```

## Pull requests

- Start from an issue, and link it from the pull request (`Fixes #12`).
- One topic per branch and pull request, opened as a draft with the template filled in. The PR title
  follows [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) (`fix(web): ...`),
  because it becomes the squash commit on `main`.
- A user-facing change adds a fragment to [changelog.d/](changelog.d/) instead of editing `CHANGELOG.md`.
- Don't change the version: releases are made with `mason bump` and `mason release`.
- A change to sign-in, keys, tokens, the GitHub proxy or plugins says so in the description and updates
  [docs/threat-model.md](docs/threat-model.md) when it adds a way in.

## Security problems

Please don't open an issue; see [SECURITY.md](SECURITY.md).
