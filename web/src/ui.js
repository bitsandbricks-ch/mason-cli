// Small shared helpers: confirmation prompts, time, links in text.
import { reactive, ref } from 'vue'
import { router } from './router.js'
import { shortLink } from './text.js'

export const prompt = reactive({ open: false, question: '', detail: '', resolve: null, allowDry: true, input: null,
  links: [], notice: false, choices: null })

// the ? key help (KeysHelp.vue): while it is open, no view acts on keys
export const keysHelp = ref(false)

// ask('Merge acme/web#7 now?') -> 'yes' | 'dry' | null
export function ask(question, { detail = '', allowDry = true, input = null } = {}) {
  return new Promise((resolve) => {
    Object.assign(prompt, { open: true, question, detail, allowDry, input, resolve, links: [], notice: false, choices: null })
  })
}

// choose('Bump acme/web', [{ key: 'p', value: 'patch', label: 'patch → 1.2.4', hint: 'fixes' }, ...]) -> value | null
export function choose(question, choices, { detail = '' } = {}) {
  return new Promise((resolve) => {
    Object.assign(prompt, { open: true, question, detail, allowDry: false, input: null, resolve, links: [], notice: false, choices })
  })
}

// tell('Revoke it at GitHub', { links: [{ href, label }] }): a message with links and an ok button.
export function tell(question, { detail = '', links = [] } = {}) {
  return new Promise((resolve) => {
    Object.assign(prompt, { open: true, question, detail, allowDry: false, input: null, resolve, links, notice: true, choices: null })
  })
}

// What DELETE /me and /me/identities/:id answer about the tokens: links for those Mason couldn't revoke.
export async function tellRevoked(got) {
  const manual = (got?.revoked || []).filter((r) => !r.revoked && r.manual)
  if (!manual.length) return
  await tell('Mason deleted its copy of your token, but could not revoke it at the provider. Revoke it there:', {
    detail: 'The built-in GitHub sign-in has no client secret, and GitHub only lets an app revoke tokens with one.',
    links: manual.map((r) => ({ href: r.manual, label: `${r.provider} (${r.login}): ${shortLink(r.manual)}` })),
  })
}

export function answer(value) {
  const r = prompt.resolve
  Object.assign(prompt, { open: false, resolve: null, choices: null })
  if (r) r(value)
}

// Phones: one column. A list fills the screen, and tapping a row opens its detail (with the view's actions)
// on top, as #detail in the URL, so the phone's back gesture closes it again.
const narrow = (() => { try { return matchMedia('(max-width: 700px)') } catch { return null } })()
export const phone = ref(!!narrow?.matches)
narrow?.addEventListener?.('change', (e) => { phone.value = e.matches })

let opening = null // openDetail's navigation while it is under way
// what the open detail shows (the tapped card's name), for the title bar: it said only "releases" or "runs"
export const detailName = ref('')
export function openDetail() {
  const r = router.currentRoute.value
  if (!phone.value || r.hash === '#detail') return
  const nav = router.push({ path: r.path, query: r.query, hash: '#detail' })
  opening = nav.finally(() => { if (opening === nav) opening = null })
  return nav
}

// Change the query of the open view and keep its #detail. A tap selects a row and opens its detail at once:
// a replace started before that push lands would cancel it and drop #detail, so it waits for it.
export async function replaceQuery(patch) {
  if (opening) await opening.catch(() => {})
  const r = router.currentRoute.value
  return router.replace({ path: r.path, query: { ...r.query, ...patch }, hash: r.hash })
}

export function closeDetail() {
  const r = router.currentRoute.value
  if (r.hash !== '#detail') return
  if (window.history.state?.back === r.fullPath.replace(/#detail$/, '')) router.back()
  else router.replace({ path: r.path, query: r.query })
}

export { ago, explain, fieldOf, glyph, linkify, shortLink, stateClass } from './text.js'
