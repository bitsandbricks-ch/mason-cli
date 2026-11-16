import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/700.css'
import './style.css'
import { createApp } from 'vue'
import App from './App.vue'
import { log } from './api.js'
import { crashText, isStaleBuild, mayReload } from './crash.js'
import { router } from './router.js'

const session = () => { try { return window.sessionStorage } catch { return undefined } }

const app = createApp(App)
// a bug in a view: in the log line in words, not only in the browser console
app.config.errorHandler = (err) => {
  console.error(err)
  log(crashText(err), 'error')
}
// Mason was updated while this tab was open: the old build's views are gone, so load the new build at the
// page that was asked for (once a minute at most, in case the new build is the broken one)
router.onError((err, to) => {
  if (isStaleBuild(err) && mayReload(session())) { window.location.assign(to.fullPath); return }
  console.error(err)
  log(isStaleBuild(err) ? 'Mason was updated: reload the page to load the new version' : crashText(err), 'error')
})
app.use(router).mount('#app')
