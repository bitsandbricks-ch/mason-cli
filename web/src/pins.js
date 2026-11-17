// Pinned repos: the ones you look after most, first in the repo and pull request lists. Kept in your
// settings (settings.pinned), so every browser you sign in with has them.
import { computed } from 'vue'
import { log, put, state } from './api.js'

export const pinned = computed(() => new Set(state.me?.settings?.pinned || []))

// rows with a pinned repo first; otherwise the order stays as it was
export function pinnedFirst(rows, set, repoOf = (r) => r.repo) {
  return rows.map((r, i) => [r, i]).sort(([a, i], [b, j]) => (set.has(repoOf(b)) - set.has(repoOf(a))) || i - j).map(([r]) => r)
}

export async function togglePin(repo) {
  if (!repo || !state.me?.user) return
  const before = state.me.settings?.pinned || []
  const after = before.includes(repo) ? before.filter((x) => x !== repo) : [...before, repo]
  state.me.settings = { ...state.me.settings, pinned: after } // at once; put back if the server says no
  try {
    const got = await put('/settings', { pinned: after })
    state.me.settings = { ...state.me.settings, pinned: got.pinned }
    log(after.length > before.length ? `pinned ${repo}: it comes first in the lists` : `unpinned ${repo}`, 'ok')
  } catch (e) {
    state.me.settings = { ...state.me.settings, pinned: before }
    log(`couldn't pin ${repo}: ${e.message}`, 'error')
  }
}
