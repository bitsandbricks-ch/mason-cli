// When a change finishes while the tab is in the background, its result leads the title (✓ or ✗) until you
// come back, and a desktop notification can say so (settings › this browser). The title itself is panel.js'
// titleFor. Pure functions, for node --test.

// the mark a finished change puts in front while the tab is hidden: an error wins over a success
export function markFor(kinds) {
  if (kinds.includes('error')) return '✗'
  if (kinds.includes('ok')) return '✓'
  return ''
}

// A desktop notification for a log line, when you asked for them in this browser (settings) and the tab is in
// the background: only finished changes (ok, error), not every note.
export function shouldNotify(entry, { on, hidden, permission }) {
  return !!(entry && on && hidden && permission === 'granted' && (entry.kind === 'ok' || entry.kind === 'error'))
}
export function notifyText(entry) {
  const body = String(entry?.text || '').replace(/^\[dry-run\] /, 'dry run: ').slice(0, 200)
  return { title: entry?.kind === 'error' ? '✗ Mason: something failed' : '✓ Mason: done', body }
}
