// The keys sheet (?): the keys that work everywhere, and those of what is on screen, read from its buttons
// (a button shows its key as <span class="k">). No imports, so node --test can run it (web/test/help.test.js).

export const GLOBAL = [
  ['ctrl+k', 'jump to a repo, PR, issue or view'],
  ['1-9 I W S D P K L :', 'views (as the tabs show)'],
  ['← →', 'the next or previous view (on a list)'],
  ['↑ ↓  j k', 'move in the list'],
  ['⏎', 'open the selected row'],
  ['/', 'filter the list'],
  ['esc', 'close the panel or go back'],
  ['.', 'the actions of what is selected'],
  ['t', 'switch the theme'],
  ['`', 'the session log'],
  ['?', 'this sheet'],
]

// [{key, label, off}] from buttons -> the sheet's rows: one per key, the enabled button's label first, in the
// order they show; keys the sheet already lists everywhere are left out
export function keysOf(buttons, skip = new Set(['.', 'r', 'esc', '/'])) {
  const out = new Map()
  for (const b of buttons) {
    const key = String(b.key || '').trim()
    const label = String(b.label || '').replace(/\s+/g, ' ').trim()
    if (!key || !label || key.length > 3 || skip.has(key)) continue
    const had = out.get(key)
    if (!had || (had.off && !b.off)) out.set(key, { key, label, off: !!b.off })
  }
  return [...out.values()]
}
