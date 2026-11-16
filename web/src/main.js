import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/700.css'
import './style.css'
import { createApp } from 'vue'
import App from './App.vue'
import { TABS, router } from './router.js'
import { watch } from 'vue'
import { state } from './api.js'
import { markFor, pageTitle } from './title.js'

createApp(App).use(router).mount('#app')

// the tab's title follows the page; a change that finishes while the tab is hidden puts ✓ or ✗ in front
const seen = [] // kinds of log lines since the tab was hidden
const show = () => { const m = markFor(seen); document.title = (m ? `${m} ` : '') + pageTitle(router.currentRoute.value, TABS) }
router.afterEach(show)
watch(() => state.log[0], (l) => { if (l && document.hidden) { seen.push(l.kind); show() } })
document.addEventListener('visibilitychange', () => { if (!document.hidden) { seen.length = 0; show() } })
