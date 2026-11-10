# The Mason logo

A prompt whose cursor is a course of bricks: Mason works from a terminal and holds your bricks together.

| File | Use |
| --- | --- |
| `mason-mark.svg` | the mark on a dark tile; the same file is the web app's favicon (`web/public/favicon.svg`) |
| `mason-dark.svg` | mark and word for dark backgrounds |
| `mason-light.svg` | mark and word for light backgrounds |
| `variants.png` | the three drafts (A wall, B block M, C prompt) on every theme, for choosing |

In the web app the logo is `web/src/components/Logo.vue`. It draws with the theme's colours: `--accent` for the
prompt, `--accent2` for the bricks and `--fg` for the word, so it fits every theme. The word is IBM Plex Mono
SemiBold (the app's own font, OFL) turned into outlines, so the SVG files need no font. The PNG icons in
`web/public` (`icon-192.png`, `icon-512.png`, `apple-touch-icon.png`) are the mark rendered on a square tile.

Colours on the files: bricks theme `#f27a4f` / `#5cb97c` on `#111111` (dark), mortar theme `#b23b14` / `#15803d` with
`#151515` text (light).
