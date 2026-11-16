// Changes not saved yet (the defaults editor, a repo's settings): leaving the page or the side panel, or
// closing the tab, asks first instead of dropping them.
import { onBeforeUnmount, watch } from 'vue'
import { leaves } from './panel.js'
import { ask } from './ui.js'

const dirty = new Map() // owner -> what it is ("your changes to mason.toml")
let owners = 0

// useUnsaved(() => dirty.value, () => 'your changes to mason.toml')
export function useUnsaved(isDirty, what) {
  const me = ++owners
  const stop = watch(isDirty, (d) => { if (d) dirty.set(me, what); else dirty.delete(me) }, { immediate: true })
  onBeforeUnmount(() => { stop(); dirty.delete(me) })
}

// true when nothing is unsaved, or you said to drop it
export async function confirmLeave() {
  if (!dirty.size) return true
  const list = [...new Set([...dirty.values()].map((w) => (typeof w === 'function' ? w() : w)))].join(' and ')
  if (!(await ask(`Leave without saving ${list}?`, { allowDry: false }))) return false
  dirty.clear()
  return true
}

export function installUnsaved(router) {
  router.beforeEach(async (to, from) => {
    if (!dirty.size || !from.matched.length || !leaves(to, from)) return
    return (await confirmLeave()) ? undefined : false
  })
  window.addEventListener('beforeunload', (e) => { if (dirty.size) { e.preventDefault(); e.returnValue = '' } })
}
