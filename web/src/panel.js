// The side panel on a wide screen: a repo, a PR, a run, a release or an issue opens on the right, next to the
// list it came from, instead of in place of it. The open one is in the URL as ?side=, so a link, reload or
// the back button bring it back:
//   repo:acme/web   pr:acme/web#7   issue:acme/web#12   run:acme/web@123   release:acme/web@v1.2.0 (or release:acme/web)
// A repo can hold ':' (gitlab:grp/app) but neither '#' nor '@', so these split cleanly. No imports, so
// node --test can run it (web/test/panel.test.js).

// kind -> the page's path and what its query holds after the repo
export const PAGES = {
  repo: { path: '/repo', sep: '', field: '' },
  pr: { path: '/pr', sep: '#', field: 'number' },
  issue: { path: '/issue', sep: '#', field: 'number' },
  run: { path: '/run', sep: '@', field: 'id' },
  release: { path: '/release', sep: '@', field: 'tag' },
}
const BY_PATH = Object.fromEntries(Object.entries(PAGES).map(([k, p]) => [p.path, k]))

// {kind, repo, number|id|tag} -> 'pr:acme/web#7' ('' when it isn't one)
export function encodeSide(t) {
  const p = t && PAGES[t.kind]
  if (!p || !t.repo) return ''
  const extra = p.field ? t[p.field] : ''
  if (p.field && p.field !== 'tag' && !extra) return '' // a PR without a number is no PR
  return `${t.kind}:${t.repo}${extra ? p.sep + extra : ''}`
}

// 'pr:acme/web#7' -> {kind: 'pr', repo: 'acme/web', number: 7}; null when it isn't one
export function decodeSide(s) {
  const m = String(s || '').match(/^(\w+):(.+)$/)
  const p = m && PAGES[m[1]]
  if (!p) return null
  const kind = m[1]
  let repo = m[2]
  let extra = ''
  if (p.sep) {
    const at = repo.indexOf(p.sep)
    if (at >= 0) { extra = repo.slice(at + 1); repo = repo.slice(0, at) }
  }
  if (!repo || /[#@\s]/.test(repo)) return null
  const out = { kind, repo }
  if (p.field === 'tag') { if (extra) out.tag = extra } else if (p.field) {
    const n = Number(extra)
    if (!Number.isInteger(n) || n <= 0) return null
    out[p.field] = n
  }
  return out
}

// a route ({path, query}) of a detail page -> its target; null for any other route
export function targetOf(route) {
  const kind = BY_PATH[route?.path]
  if (!kind) return null
  const q = route.query || {}
  return decodeSide(encodeSide({ kind, repo: String(q.repo || ''), number: q.number, id: q.id, tag: q.tag ? String(q.tag) : '' }))
}

// a target -> the page's own route, for "open as page" and for a phone
export function pageRoute(t) {
  const p = PAGES[t.kind]
  const query = { repo: t.repo }
  if (p.field && t[p.field]) query[p.field] = String(t[p.field])
  return { path: p.path, query }
}

// a target -> the query the page reads (route.query has strings, so this does too)
export const queryOf = (t) => pageRoute(t).query

// the route that shows `target` in the side panel of `from` (null target: the panel closed)
export function withSide(from, target) {
  const query = { ...(from.query || {}) }
  const s = target ? encodeSide(target) : ''
  if (s) query.side = s
  else delete query.side
  return { path: from.path, query, hash: from.hash || '' }
}

// A navigation to a detail page, on a wide screen: open it in the side panel of the page you are on instead?
// Not for the first page you land on (a shared link opens as a page), not for back/forward to a page you
// opened as one, not to the page you are already on, and not when asked for the page itself.
export function sideFor(to, from, { wide, first, asPage, popping }) {
  if (!wide || first || asPage || popping) return null
  const t = targetOf(to)
  if (!t) return null
  if (from.path === to.path && encodeSide(targetOf(from) || {}) === encodeSide(t)) return null
  if (from.path === '/login' || from.path === '/device') return null
  return withSide(from, t)
}

// While the panel is open, moving in the list it came from shows the new row in it (like a mail app). Only
// for the same kind: a repo's panel doesn't turn into a PR because the list moved.
export function follow(open, next, anyKind = false) {
  if (!open || !next || (!anyKind && open.kind !== next.kind)) return null
  const s = encodeSide(next)
  return s && s !== encodeSide(open) ? next : null
}

// the panel's width in px: what was dragged (or saved), kept so the list keeps at least `list` px
export const MIN_WIDTH = 420
export function clampWidth(want, screen, list = 360) {
  const max = Math.max(MIN_WIDTH, screen - list)
  const w = Number.isFinite(want) && want > 0 ? want : Math.round(screen * 0.5)
  return Math.round(Math.max(MIN_WIDTH, Math.min(max, w)))
}

// whose keys a key press is for: with a panel open the page in it has them, the view under it doesn't
export const listens = ({ sideOpen, inSide }) => !sideOpen || inSide

// Does going from `from` to `to` take away what is on screen (and with it what you were editing)? Another
// page, or another thing in the side panel; not a change of a filter, a tab inside the page or #detail.
export function leaves(to, from) {
  return to.path !== from.path || (to.query?.side || '') !== (from.query?.side || '') ||
    (!!targetOf(to) && encodeSide(targetOf(to)) !== encodeSide(targetOf(from) || {}))
}

// The browser tab's title: what is open first (the panel's item, a detail page's item, or the view), so tabs
// and history entries tell apart. labels: path -> the view's name (router.js TABS).
export function titleFor(route, labels = {}, app = 'Mason') {
  const name = (t) => encodeSide(t).replace(/^\w+:/, '').replace(/^gitlab:/, '')
  const side = decodeSide(route?.query?.side)
  const page = targetOf(route)
  const view = labels[route?.path]
  const parts = side ? [name(side), view] : page ? [name(page)] : [view]
  return [...parts.filter(Boolean), app].join(' · ')
}
