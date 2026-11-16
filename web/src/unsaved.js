// Unsaved text (a file in an editor, a half-written issue): leaving the page asks first, and closing or
// reloading the tab gets the browser's own warning. Edits were lost silently on a tab switch or a key like 2.
import { onBeforeUnmount, onMounted } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ask } from './ui.js'

// drop: called when the person chose to leave without saving (to forget a kept draft)
export function useUnsaved(isDirty, what = 'your changes', drop = null) {
  const warn = (e) => { if (isDirty()) { e.preventDefault(); e.returnValue = '' } }
  onMounted(() => window.addEventListener('beforeunload', warn))
  onBeforeUnmount(() => window.removeEventListener('beforeunload', warn))
  onBeforeRouteLeave(async (to, from) => {
    // the same page with another query or #detail (a phone's detail view) isn't leaving
    if (to.path === from.path || to.name === 'login' || !isDirty()) return true // signed out: no one to ask (the defaults editor keeps a draft)
    const leave = !!(await ask(`Leave this page and drop ${what}?`, { allowDry: false }))
    if (leave) drop?.()
    return leave
  })
}
