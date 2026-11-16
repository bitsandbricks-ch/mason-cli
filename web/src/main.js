import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/700.css'
import './style.css'
import { createApp } from 'vue'
import App from './App.vue'
import { log } from './api.js'
import { router } from './router.js'
import { installSide } from './side.js'
import { installUnsaved } from './unsaved.js'
import { staleChunk } from './links.js'

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

const app = createApp(App)
// a bug in a view shows in the log line instead of only in the browser console, and the rest keeps working
app.config.errorHandler = (err) => { log(`something broke: ${err?.message || err}`, 'error'); console.error(err) }
window.addEventListener('unhandledrejection', (e) => { if (staleChunk(e.reason)) return; log(`something broke: ${e.reason?.message || e.reason}`, 'error') })
app.use(router).mount('#app')
