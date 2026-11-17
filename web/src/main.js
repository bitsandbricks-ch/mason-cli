import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/700.css'
import './style.css'
import { createApp, watch } from 'vue'
import App from './App.vue'
import { keepDry, log, state } from './api.js'
import { TABS, router } from './router.js'
import { titleFor } from './panel.js'
import { installSide } from './side.js'
import { installUnsaved } from './unsaved.js'
import { staleChunk } from './links.js'
import { markFor, notifyText, shouldNotify } from './title.js'
import { notifyOn, permission } from './notify.js'
import { scope } from './scope.js'
import { scopeFrom } from './saved.js'

// ?group= and ?provider= in a link (a saved view, a shared link) set the filter before the view loads
router.beforeEach((to) => { const s = scopeFrom(to.query); if (s) Object.assign(scope, s) })

watch(() => state.dryRun, keepDry)

installUnsaved(router) // first: a page you won't leave doesn't turn into a panel either
installSide(router)

// After an update the server has new files: a tab opened before it asks for a view's old file and gets none.
// Load the page you wanted afresh (once: a second failure in a row is a real error and shows in the log).
router.onError((err, to) => {
  if (!staleChunk(err)) return
  let tried = ''
  try { tried = sessionStorage.getItem('mason-reloaded') || '' } catch { /* private mode */ }
  if (tried === to.fullPath) { log(`couldn't load this view: ${err.message}`, 'error'); return }
  try { sessionStorage.setItem('mason-reloaded', to.fullPath) } catch { /* private mode */ }
  window.location.assign(to.fullPath)
})
router.afterEach(() => { try { sessionStorage.removeItem('mason-reloaded') } catch { /* private mode */ } })
// each tab and history entry says what it shows: "acme/web#7 · pull requests · Mason"; a change that finishes
// while the tab is hidden puts ✓ or ✗ in front until you come back, and notifies when you asked for that
const LABELS = Object.fromEntries(TABS.map((t) => [t.path, t.label]))
const seen = [] // kinds of log lines since the tab was hidden
const show = (to = router.currentRoute.value) => { const m = markFor(seen); document.title = (m ? `${m} ` : '') + titleFor(to, LABELS) }
router.afterEach((to) => show(to))
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

const app = createApp(App)
// a bug in a view shows in the log line instead of only in the browser console, and the rest keeps working
app.config.errorHandler = (err) => { log(`something broke: ${err?.message || err}`, 'error'); console.error(err) }
window.addEventListener('unhandledrejection', (e) => { if (staleChunk(e.reason)) return; log(`something broke: ${e.reason?.message || e.reason}`, 'error') })
app.use(router).mount('#app')
