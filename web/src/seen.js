// "New since your last visit": a list remembers (in this browser) which rows you have had in front of you, and
// marks the ones it hasn't shown you before. The first visit marks nothing. The rules are pure, for node --test;
// useSeen wires them to a view.
import { computed, onBeforeUnmount, onMounted } from 'vue'

const MAX = 3000 // keys kept per list, newest first: old PRs and runs fall off the end

// what is new in now, against what was seen before (null: never visited, so nothing is new)
export function fresh(before, now) {
  if (!Array.isArray(before)) return new Set()
  const old = new Set(before)
  return new Set(now.filter((k) => !old.has(k)))
}

// what to keep after a visit: this visit's keys first, then the earlier ones, without repeats
export function merged(before, now, max = MAX) {
  return [...new Set([...now, ...(Array.isArray(before) ? before : [])])].slice(0, max)
}

const storeKey = (name) => `mason-seen-${name}`
function read(name) {
  try { const v = JSON.parse(localStorage.getItem(storeKey(name)) || 'null'); return Array.isArray(v) ? v : null } catch { return null }
}

// keys: a function returning every row key the view has loaded (not only the filtered ones)
export function useSeen(name, keys) {
  const before = read(name)
  const marked = computed(() => fresh(before, keys()))
  function save() {
    const now = keys()
    if (!now.length && before) return // nothing loaded (an error, a slow answer): keep what we had
    try { localStorage.setItem(storeKey(name), JSON.stringify(merged(read(name), now))) } catch { /* private mode */ }
  }
  // leaving the view, or closing the tab, counts as having seen what was shown
  onMounted(() => window.addEventListener('pagehide', save))
  onBeforeUnmount(() => { window.removeEventListener('pagehide', save); save() })
  return { isNew: (k) => marked.value.has(k), count: computed(() => marked.value.size) }
}
