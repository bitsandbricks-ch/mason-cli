import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/700.css'
import './style.css'
import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router.js'
import { scope } from './scope.js'
import { scopeFrom } from './saved.js'

// ?group= and ?provider= in a link (a saved view, a shared link) set the filter before the view loads
router.beforeEach((to) => { const s = scopeFrom(to.query); if (s) Object.assign(scope, s) })

createApp(App).use(router).mount('#app')
