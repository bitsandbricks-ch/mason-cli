import '@fontsource/jetbrains-mono/400.css'
import '@fontsource/jetbrains-mono/700.css'
import './style.css'
import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router.js'
import { installSide } from './side.js'
import { installUnsaved } from './unsaved.js'

installUnsaved(router) // first: a page you won't leave doesn't turn into a panel either
installSide(router)

createApp(App).use(router).mount('#app')
