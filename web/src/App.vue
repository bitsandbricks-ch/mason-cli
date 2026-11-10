<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { get, loadMe, log, post, put, state } from './api.js'
import { THEMES } from './themes.js'
import { GROUPS, TABS } from './router.js'
import { typing } from './keys.js'
import { closeDetail, phone, prompt } from './ui.js'
import PromptDialog from './components/PromptDialog.vue'

const route = useRoute()
const router = useRouter()
const signedIn = computed(() => !!state.me?.user)
const themes = THEMES
function stored() { try { return localStorage.getItem('mason-theme') } catch { return null } }
// No choice yet: bricks, or mortar (its light twin) when the system is set to light.
function fallback() { try { return matchMedia('(prefers-color-scheme: light)').matches ? 'mortar' : 'bricks' } catch { return 'bricks' } }
const theme = ref(themes.includes(stored()) ? stored() : fallback())
const plugins = ref([])
watch(theme, (t) => { document.documentElement.dataset.theme = t; try { localStorage.setItem('mason-theme', t) } catch { /* private mode */ } }, { immediate: true })
// The theme is a per-user setting: signing in picks up your choice, and switching saves it to your account.
watch(() => state.me?.settings?.theme, (t) => { if (themes.includes(t)) theme.value = t }, { immediate: true })
watch(theme, async (t) => {
  if (!signedIn.value || state.me.scope === 'read' || state.me.settings?.theme === t) return
  try { state.me.settings = { ...state.me.settings, ...(await put('/settings', { theme: t })) } } catch { /* stays on this device */ }
})

const who = computed(() => (state.me?.identities || []).map((i) => `${i.provider}:${i.login}`).join(' '))
const last = computed(() => state.log[0])
const rate = computed(() => {
  const c = state.rate?.github?.core
  return c ? `gh ${c.remaining}/${c.limit}` : ''
})

async function refreshRate() {
  if (!signedIn.value) return
  try { state.rate = await get('/rate') } catch { /* not important */ }
}

onMounted(async () => {
  await loadMe()
  guard()
  if (signedIn.value) {
    refreshRate()
    try { plugins.value = (await get('/plugins')).plugins.filter((p) => p.on && p.tabs.length) } catch { /* none */ }
  }
})
function guard() {
  if (!state.loaded) return
  if (!signedIn.value && !route.meta.public) router.replace({ name: 'login', query: route.path !== '/' ? { next: route.fullPath } : {} })
}
watch(() => route.fullPath, guard)
watch(signedIn, guard)

// Phones: a bar at the bottom with the views used most and "more", which opens a menu of every view,
// the theme, dry run and sign out.
const DOCK = [
  { name: 'repos', path: '/', label: 'repos', icon: '▤' },
  { name: 'prs', path: '/prs', label: 'PRs', icon: '⇅' },
  { name: 'issues', path: '/issues', label: 'issues', icon: '◎' },
  { name: 'runs', path: '/runs', label: 'runs', icon: '▶' },
]
const menu = ref(false)
const detail = computed(() => phone.value && route.hash === '#detail')
const current = computed(() => route.meta.tab || route.name)
const inDock = computed(() => DOCK.some((d) => d.name === current.value))
const title = computed(() => {
  if (route.name === 'plugin-tab') return `${route.params.plugin}`
  const t = TABS.find((x) => x.name === current.value)
  const label = t ? t.label.replace(/ /g, '-') : route.name
  return route.query.repo && route.name !== current.value ? `${label}/${route.query.repo}` : label
})
// ‹ in the title bar: closes a detail, or leaves a row's own page (a repo, its releases) for its list
const canBack = computed(() => detail.value || (!!route.meta.tab && route.name !== route.meta.tab))
function goBack() {
  if (detail.value) return closeDetail()
  if (window.history.state?.back) return router.back()
  router.push(TABS.find((t) => t.name === current.value)?.path || '/')
}
const moreLabel = computed(() => (inDock.value || menu.value ? 'more' : TABS.find((x) => x.name === current.value)?.label || route.name))
watch(() => route.path, () => { menu.value = false })
watch(phone, (p) => { if (!p) menu.value = false })

// the last log line, for a few seconds (errors longer), above the bottom bar
const toast = ref(null)
let toastTimer = null
watch(() => state.log[0], (l) => {
  if (!phone.value || !l) return
  toast.value = l
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = null }, l.kind === 'error' ? 10000 : 4000)
})

async function logout() {
  try { await post('/auth/logout') } catch (e) { log(e.message, 'error') }
  state.me = { user: null, providers: state.me?.providers || [] }
  router.replace('/login')
}

window.addEventListener('keydown', (e) => {
  if (prompt.open || typing(e) || e.ctrlKey || e.metaKey || e.altKey || !signedIn.value) return
  const tab = TABS.find((t) => t.key === e.key)
  if (tab) { router.push(tab.path); e.preventDefault(); return }
  if (e.key === 't') { theme.value = themes[(themes.indexOf(theme.value) + 1) % themes.length] }
  else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
    const i = TABS.findIndex((t) => t.name === route.name || t.name === route.meta.tab)
    if (i >= 0) { router.push(TABS[(i + (e.key === 'ArrowRight' ? 1 : TABS.length - 1)) % TABS.length].path); e.preventDefault() }
  } else if (e.key === '?') { router.push('/console'); log('keys: 1-9 tabs · ←→ next tab · ↑↓/jk move · Enter act · / filter · r reload · t theme · : console') }
})
</script>

<template>
  <div v-if="!state.loaded" class="center"><span class="cursor">connecting</span></div>
  <router-view v-else-if="!signedIn || route.meta.public" />
  <div v-else-if="phone" class="screen phone">
    <header class="top">
      <button v-if="canBack" class="back" aria-label="back" @click="goBack">‹</button>
      <span class="title"><span class="prompt accent">mason</span><span class="dim">:~/</span>{{ title }}</span>
      <span class="spacer" />
      <span v-if="state.busy" class="warn cursor" aria-label="working" />
      <button v-if="state.dryRun" class="chip on" title="dry run is on: changes only show what they would do" @click="state.dryRun = false">dry run ✕</button>
    </header>
    <main :class="{ detail }">
      <router-view @rate="refreshRate" />
      <div v-if="menu" class="sheet" role="dialog" aria-label="every view">
        <section v-for="g in GROUPS" :key="g">
          <h2>{{ g }}</h2>
          <router-link v-for="t in TABS.filter((x) => x.group === g)" :key="t.name" :to="t.path" class="item"
                       :class="{ active: current === t.name }">
            <span>{{ t.label }}</span><span class="dim">{{ t.hint }}</span>
          </router-link>
          <template v-if="g === 'setup'">
            <router-link v-for="p in plugins" :key="p.name" :to="`/plugins/${p.name}/${p.tabs[0].id}`" class="item"
                         :class="{ active: route.params.plugin === p.name }">
              <span>{{ p.tabs[0].title.toLowerCase() }}</span><span class="dim">plugin {{ p.name }}</span>
            </router-link>
            <router-link v-if="state.me.user.is_operator" to="/operator" class="item" :class="{ active: route.name === 'operator' }">
              <span>operator</span><span class="dim">the server, accounts, plugins for everyone</span>
            </router-link>
          </template>
        </section>
        <section>
          <h2>you</h2>
          <div class="item static"><span>theme</span>
            <span class="row"><button v-for="t in themes" :key="t" class="chip" :class="{ on: theme === t }" @click="theme = t">{{ t }}</button></span>
          </div>
          <label class="item static"><span>dry run</span>
            <span class="row"><input v-model="state.dryRun" type="checkbox"> <span class="dim">changes only show what they would do</span></span>
          </label>
          <div class="item static"><span>{{ state.me.user.name }}</span>
            <span class="row"><span class="dim grow">{{ who }}<template v-if="rate"> · {{ rate }} calls left</template></span>
              <button @click="logout">sign out</button></span>
          </div>
        </section>
      </div>
    </main>
    <nav class="dock" aria-label="views">
      <router-link v-for="d in DOCK" :key="d.name" :to="d.path" :class="{ active: !menu && current === d.name }">
        <span class="ico" aria-hidden="true">{{ d.icon }}</span>{{ d.label }}
      </router-link>
      <button :class="{ active: menu || !inDock }" :aria-expanded="menu" @click="menu = !menu">
        <span class="ico" aria-hidden="true">{{ menu ? '✕' : '≡' }}</span>{{ moreLabel }}
      </button>
    </nav>
    <div v-if="toast" class="toast" :class="toast.kind === 'error' ? 'bad' : toast.kind === 'ok' ? 'ok' : ''" role="status"
         @click="toast = null">{{ toast.text }}</div>
  </div>
  <div v-else class="screen">
    <header class="top">
      <span class="prompt accent">{{ state.me.user.name.toLowerCase().replace(/\s+/g, '') }}@mason</span><span class="dim hide-xs">:~$</span>
      <span class="dim hide-sm">{{ who }}</span>
      <span class="spacer" />
      <span v-if="state.busy" class="warn">working…</span>
      <span class="dim hide-sm" :title="'API calls left at GitHub'">{{ rate }}</span>
      <label class="check" title="every change only shows what it would do">
        <input v-model="state.dryRun" type="checkbox"> <span :class="state.dryRun ? 'warn' : 'dim'">dry<span class="hide-xs"> run</span></span>
      </label>
      <button title="t switches the theme" aria-label="switch the theme" @click="theme = themes[(themes.indexOf(theme) + 1) % themes.length]"><span class="hide-xs">{{ theme }}</span><span class="show-xs">◐</span></button>
      <button @click="logout"><span class="hide-xs">logout</span><span class="show-xs">exit</span></button>
    </header>
    <nav class="tabs" aria-label="views">
      <router-link v-for="t in TABS" :key="t.name" :to="t.path" :class="{ active: route.name === t.name || route.meta.tab === t.name }">
        <span class="k">{{ t.key }}</span>{{ t.label }}
      </router-link>
      <router-link v-for="p in plugins" :key="p.name" :to="`/plugins/${p.name}/${p.tabs[0].id}`"
                   :class="{ active: route.params.plugin === p.name }">
        <span class="k">+</span>{{ p.tabs[0].title.toLowerCase() }}
      </router-link>
      <router-link v-if="state.me.user.is_operator" to="/operator" :class="{ active: route.name === 'operator' }">
        <span class="k">#</span>operator
      </router-link>
    </nav>
    <main><router-view @rate="refreshRate" /></main>
    <footer class="foot">
      <span v-if="last" class="last" :class="last.kind === 'error' ? 'bad' : last.kind === 'ok' ? 'ok' : 'dim'"
            :title="last.text">[{{ last.at }}] {{ last.text }}</span>
      <span v-else class="last dim">ready</span>
      <span class="keys"><b>1-9</b> tabs <b>↑↓</b> move <b>⏎</b> open <b>/</b> filter <b>r</b> reload <b>t</b> theme <b>:</b> console <b>?</b> help</span>
    </footer>
  </div>
  <PromptDialog />
</template>
