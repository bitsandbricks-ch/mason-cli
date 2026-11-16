import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/700.css'
import './style.css'
import { createApp } from 'vue'
import App from './App.vue'
import { TABS, router } from './router.js'
import { watch } from 'vue'
import { state } from './api.js'
import { markFor, notifyText, pageTitle, shouldNotify } from './title.js'
import { notifyOn, permission } from './notify.js'

createApp(App).use(router).mount('#app')

// the tab's title follows the page; a change that finishes while the tab is hidden puts ✓ or ✗ in front
const seen = [] // kinds of log lines since the tab was hidden
const show = () => { const m = markFor(seen); document.title = (m ? `${m} ` : '') + pageTitle(router.currentRoute.value, TABS) }
router.afterEach(show)
watch(() => state.log[0], (l) => {
  if (!l || !document.hidden) return
  seen.push(l.kind)
  show()
  if (!shouldNotify(l, { on: notifyOn.value, hidden: document.hidden, permission: permission() })) return
  const { title, body } = notifyText(l)
  try {
    const n = new Notification(title, { body, tag: 'mason' }) // one at a time: a newer one replaces it
    n.onclick = () => { window.focus(); n.close() }
  } catch { /* some phones only notify from a service worker */ }
})
document.addEventListener('visibilitychange', () => { if (!document.hidden) { seen.length = 0; show() } })
