// ↑ ↓ PageUp PageDown Home End when nothing that takes them has focus (the page just opened, or a button was
// clicked): a view's list gets them, as if it had focus; a page without one (a repo's page, a PR's) scrolls the
// pane that holds what you look at. Without this the keys went to <body>, which never scrolls: the app's
// panes scroll inside a fixed screen. No imports, so node --test can run it (web/test/arrows.test.js).

export const MOVE = new Set(['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End'])
const LINE = 40

// focus that does its own thing with these keys
const OWNS = 'input, textarea, select, [contenteditable=""], [contenteditable="true"], table.table, [role="listbox"], [role="dialog"]'
export const ownsArrows = (el) => !!el?.closest?.(OWNS)

// where a pane scrolled to by key, kept between 0 and the end
export function nextTop(key, top, page, max) {
  const to = { ArrowDown: top + LINE, ArrowUp: top - LINE, PageDown: top + page * 0.9, PageUp: top - page * 0.9, Home: 0, End: max }[key]
  return Math.max(0, Math.min(max, to ?? top))
}

// the pane to scroll: the one the pointer was last in, else the one with the most to scroll (the page's
// content, not the event log band, which on a short screen can be the bigger box)
export function pickPane(panes, last) {
  const under = panes.filter((p) => last && p.contains(last))
  if (under.length) return under[under.length - 1] // the innermost: querySelectorAll lists outer ones first
  const hidden = (p) => p.scrollHeight - p.clientHeight
  return panes.reduce((best, p) => (!best || hidden(p) > hidden(best) ? p : best), null)
}

function panes(root, style) {
  return [...root.querySelectorAll('*')].filter((el) => {
    if (el.scrollHeight <= el.clientHeight + 1) return false
    const y = style(el).overflowY
    return y === 'auto' || y === 'scroll'
  })
}

// handles e if it is one of the keys above with nothing taking it; true when it did
export function arrowKey(e, doc, last = null) {
  if (!MOVE.has(e.key) || e.shiftKey) return false
  const at = doc.activeElement
  if (at && at !== doc.body && ownsArrows(at)) return false
  const root = doc.querySelector('main') || doc.body
  const list = root.querySelector('table.table[tabindex]')
  if (list) {
    list.focus({ preventScroll: true })
    list.dispatchEvent(new e.constructor('keydown', { key: e.key, bubbles: true, cancelable: true }))
    e.preventDefault()
    return true
  }
  const pane = pickPane(panes(root, (el) => doc.defaultView.getComputedStyle(el)), last)
  if (!pane) return false
  pane.scrollTop = nextTop(e.key, pane.scrollTop, pane.clientHeight, pane.scrollHeight - pane.clientHeight)
  e.preventDefault()
  return true
}
