// node --test (npm test): every theme's text colours stay readable on each of its backgrounds (WCAG AA, 4.5:1).
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const css = readFileSync(new URL('../src/style.css', import.meta.url), 'utf8')

function theme(name) {
  const block = css.match(new RegExp(`\\[data-theme="${name}"\\]\\s*\\{([^}]*)\\}`))?.[1] || ''
  return Object.fromEntries([...block.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2]]))
}
function lum(hex) {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4))
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
}
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }

for (const name of ['bricks', 'mortar']) {
  test(`${name}: text colours read on every background`, () => {
    const t = theme(name)
    for (const fg of ['fg', 'dim', 'accent', 'ok', 'warn', 'bad', 'link']) {
      for (const bg of ['bg', 'bg2', 'bg3', 'sel']) {
        if (!t[fg] || !t[bg]) continue
        assert.ok(ratio(t[fg], t[bg]) >= 4.5, `${name} --${fg} ${t[fg]} on --${bg} ${t[bg]}: ${ratio(t[fg], t[bg]).toFixed(2)}`)
      }
    }
    assert.ok(t.fg && t.bg && t.dim, 'the theme block was found')
  })
}
