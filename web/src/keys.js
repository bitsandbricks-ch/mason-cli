// Keys like the TUI's: a view registers its own with useKeys while it is shown.
import { inject, onBeforeUnmount, onMounted } from 'vue'
import { prompt } from './ui.js'
import { SIDE, sideOpen } from './side.js'
import { listens } from './panel.js'

export function typing(e) {
  const t = e.target
  return t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)
}

export function useKeys(map) {
  const inSide = !!inject(SIDE, null)
  function on(e) {
    if (prompt.open || typing(e) || e.ctrlKey || e.metaKey || e.altKey) return
    // a list's own keys (↑↓, j/k, g, Enter) already did their thing; and with a panel open, its page has the keys
    if (e.defaultPrevented || !listens({ sideOpen: sideOpen.value, inSide })) return
    const fn = map[e.key]
    if (fn) { e.preventDefault(); fn(e) }
  }
  onMounted(() => window.addEventListener('keydown', on))
  onBeforeUnmount(() => window.removeEventListener('keydown', on))
}
