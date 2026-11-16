// The side panel's state and navigation (the rules are in panel.js, which tests can run). On a wide screen a
// navigation to a detail page turns into ?side= on the page you are on (see installSide); a detail page shown
// in the panel reads its query from the panel instead of the route (usePage), and its back closes the panel.
import { computed, inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { decodeSide, follow, pageRoute, queryOf, sideFor, withSide } from './panel.js'
import { phone, replaceQuery } from './ui.js'

export const SIDE = Symbol('side') // provided by SidePanel to the page inside it
export const sideOpen = ref(false) // a panel is showing: the page under it leaves the keys to the panel

let asPage = false // the next navigation to a detail page is meant as a page ("open as page", a phone)
let popping = false // back/forward: go where the history says, don't turn it into a panel

export function installSide(router) {
  // before the router's own listener: guards run after it, so the flag is set in time either way
  window.addEventListener('popstate', () => { popping = true }, true)
  router.beforeEach((to, from) => {
    const first = !from.matched.length
    const next = sideFor(to, from, { wide: !phone.value, first, asPage, popping })
    asPage = false
    if (next) return next
    // a link with ?side= opened on a phone: the page itself, full screen
    if (phone.value && to.query.side) {
      const t = decodeSide(to.query.side)
      const q = { ...to.query }
      delete q.side
      return t ? pageRoute(t) : { path: to.path, query: q, hash: to.hash }
    }
  })
  router.afterEach(() => { popping = false })
}

export function openAsPage(router, t) {
  asPage = true
  return router.push(pageRoute(t))
}

// The panel's target (null when closed), and opening, following and closing it.
export function useSide() {
  const route = useRoute()
  const router = useRouter()
  const target = computed(() => (phone.value ? null : decodeSide(route.query.side)))
  const open = (t) => router.push(withSide(route, t))
  function close() {
    if (!route.query.side) return
    const without = router.resolve(withSide(route, null)).fullPath
    if (window.history.state?.back === without) router.back()
    else router.replace(withSide(route, null))
  }
  // the list moved to another row: show it instead (replace: arrowing through a list isn't history)
  function track(next) {
    const t = follow(target.value, next)
    if (t) router.replace(withSide(route, t))
  }
  return { target, open, close, track }
}

// For a detail page: its query (the route's, or the panel's) and how to leave it.
export function usePage(list) {
  const side = inject(SIDE, null)
  const route = useRoute()
  const router = useRouter()
  const query = computed(() => (side?.target.value ? queryOf(side.target.value) : route.query))
  const back = () => {
    if (side) return side.close()
    if (window.history.state?.back) return router.back()
    router.push(list)
  }
  // change what the page shows (a release's tag): in the panel's ?side=, or in the page's own query
  const setQuery = (patch) => (side?.target.value ? router.replace(withSide(route, { ...side.target.value, ...patch })) : replaceQuery(patch))
  return { query, back, setQuery, inSide: !!side }
}

// For a list: while the panel is open, it shows the row you move to (fn: the selected row's target, or null).
// Not the row a list picks by itself when it loads: a link to /prs?side=pr:acme/web#7 keeps showing #7.
// sel and key: the other way round, the list selects the row the panel shows (a link, the back button, the
// jump box), when it has one; key(target) is that row's key, or null when the panel shows something else.
export function useTrack(fn, { sel, key } = {}) {
  const { track, target } = useSide()
  watch(fn, (t, before) => { if (before) track(t) })
  if (sel && key) watch(target, (t) => { const k = t && key(t); if (k != null && k !== sel.value) sel.value = k }, { immediate: true })
}
