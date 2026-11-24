# Changelog fragments

One Markdown file per user-facing change, named after the topic (`handbook-profile.md`), with one
line per entry. `mason bump` collects them into `CHANGELOG.md` and deletes them in the release PR,
so feature PRs never edit `CHANGELOG.md` and never conflict over it.
