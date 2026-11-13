// Small shared helpers: confirmation prompts, time, links in text.
import { reactive, ref } from 'vue'
import { router } from './router.js'

export const prompt = reactive({ open: false, question: '', detail: '', resolve: null, allowDry: true, input: null,
  links: [], notice: false, choices: null })

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

export function ago(stamp) {
  if (!stamp) return '-'
  const secs = (Date.now() - new Date(stamp.endsWith('Z') || stamp.includes('+') ? stamp : stamp + 'Z')) / 1000
  for (const [u, s] of [['d', 86400], ['h', 3600], ['m', 60]]) if (secs >= s) return `${Math.floor(secs / s)}${u} ago`
  return 'just now'
}

const URL_RE = /(https?:\/\/[^\s)\]>,'"]+)/g

// Text -> [{text}|{href,label}] so templates can render links without v-html.
export function linkify(text) {
  const out = []
  let last = 0
  for (const m of String(text || '').matchAll(URL_RE)) {
    if (m.index > last) out.push({ text: text.slice(last, m.index) })
    out.push({ href: m[0], label: shortLink(m[0]) })
    last = m.index + m[0].length
  }
  if (last < String(text || '').length) out.push({ text: String(text).slice(last) })
  return out
}

export function shortLink(url) {
  return url.replace(/^https:\/\/(github\.com|gitlab\.com)\//, '').replace(/^https?:\/\//, '')
}

export function stateClass(value) {
  const v = String(value || '').toLowerCase()
  if (/^(success|passing|ok|approved|merged|verified|ready|green)/.test(v)) return 'ok'
  if (/(fail|error|conflict|critical|high|secret|denied|unverified|missing|blocked)/.test(v)) return 'bad'
  if (/(pending|running|waiting|draft|medium|moderate|manual|review)/.test(v)) return 'warn'
  return ''
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

// A status word's mark, so a column reads at a glance: ✓ fine, ✗ needs you, ● on its way.
export function glyph(cls) {
  return { ok: '✓', bad: '✗', warn: '●' }[cls] || ''
}

// An error from the API (often a gh or glab command's output) in plain words: {title, raw}. raw is the
// original, for a "details" toggle.
export function explain(message, what = '') {
  const raw = String(message || '').replace(/^error:\s*/i, '').trim()
  const lead = what ? `${what}: ` : ''
  const say = (t) => ({ title: lead + t, raw })
  if (/bad credentials|\b401\b|token.*(expired|revoked)|sign in again/i.test(raw)) return say('your sign-in has expired. Sign out and in again.')
  if (/rate limit|\b429\b/i.test(raw)) return say('the GitHub rate limit is used up. Try again in a few minutes.')
  if (/must have admin|admin rights|\b403\b|resource not accessible|forbidden|permission/i.test(raw)) return say("your account isn't allowed to do this here (it may need admin rights on the repo).")
  if (/no answer for|\b404\b|not found|could not resolve/i.test(raw)) return say("GitHub says it doesn't exist, or your account can't see it.")
  if (/connect gitlab/i.test(raw)) return say('connect GitLab under setup › settings first.')
  if (/timed? ?out|econn|network|failed to fetch|unreachable/i.test(raw)) return say("couldn't reach the server. Check the connection and try again.")
  // no idea: the first line, without the command that printed it
  const first = raw.split('\n')[0].replace(/^(gh|glab) (api )?(-X \w+ )?\S+:\s*/, '').replace(/^[^:]{0,40}: (gh|glab) [^:]+: /, '')
  return { title: lead + (first.length > 160 ? first.slice(0, 157) + '…' : first || 'something went wrong'), raw }
}

// "  state    open, by ann" -> 'open, by ann': a field of a detail text (the CLI's layout)
export function fieldOf(text, name) {
  const re = new RegExp(`^\\s+${name}\\s`)
  return (String(text || '').split('\n').find((l) => re.test(l)) || '').trim().slice(name.length).trim()
}
