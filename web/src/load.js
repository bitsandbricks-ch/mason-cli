import { onMounted, onScopeDispose, ref, watch } from 'vue'
import { get, log, post, qs, state } from './api.js'
import { scope } from './scope.js'
import { ask } from './ui.js'

// Answers the views already have, by request path: switching tabs (or going back from a page) shows the
// last answer at once and asks again only when it is older than FRESH_MS. r and every change ask again.
const memo = new Map() // path -> {at, data}
const FRESH_MS = 60_000
const MAX = 200

function remember(path, data) {
  memo.delete(path)
  memo.set(path, { at: Date.now(), data })
  while (memo.size > MAX) memo.delete(memo.keys().next().value)
}

// Drop remembered answers whose path starts with prefix (all of them without one).
export function forget(prefix = '') {
  for (const k of [...memo.keys()]) if (k.startsWith(prefix)) memo.delete(k)
}

const keyOf = (path) => path.replace(/[?&]fresh=1/, '')

// A GET through the memo: a remembered answer younger than FRESH_MS, unless fresh.
export async function cached(path, fresh = false, opts = undefined) {
  const key = keyOf(path)
  const hit = memo.get(key)
  if (!fresh && hit && Date.now() - hit.at < FRESH_MS) return hit.data
  const data = await get(path, opts)
  remember(key, data)
  return data
}

// Load a list when the view opens (and again on r, or when the provider/group changes). The fetcher returns
// the request path; a remembered answer shows right away and is asked again when older than FRESH_MS.
export function useLoad(fetcher, { scoped = true } = {}) {
  const data = ref(null)
  const error = ref('')
  const loading = ref(false)
  let last = null // the memo key of what data shows
  async function load(fresh = false) {
    const q = scoped ? qs({ provider: scope.provider === 'all' ? '' : scope.provider, group: scope.group, fresh }) : ''
    const got = fetcher(q, fresh) // a path (remembered, see cached) or a promise
    const key = typeof got === 'string' ? keyOf(got) : null
    last = key
    const hit = key && memo.get(key)
    if (!fresh && hit) {
      data.value = hit.data
      if (Date.now() - hit.at < FRESH_MS) return
    }
    loading.value = true
    error.value = ''
    try {
      data.value = key ? await cached(got, true) : await got
    } catch (e) {
      error.value = e.message
      log(e.message, 'error')
    } finally {
      loading.value = false
    }
  }
  // Show a changed answer (a follow-up's), and remember it, so going back to the view shows it too.
  function keep(value) {
    data.value = value
    if (last) remember(last, value)
  }
  onMounted(() => load())
  if (scoped) watch(() => [scope.provider, scope.group], () => load())
  return { data, error, loading, load, keep }
}

// rows with the rows of `repos` swapped for fresh ones, in place: where a repo's first row was, its fresh rows go
// (repos that had none come last).
export function splice(rows, fresh, repos) {
  const named = new Set(repos)
  const by = new Map()
  for (const r of fresh || []) { if (!by.has(r.repo)) by.set(r.repo, []); by.get(r.repo).push(r) }
  const out = []
  for (const r of rows || []) {
    if (!named.has(r.repo)) { out.push(r); continue }
    if (by.has(r.repo)) { out.push(...by.get(r.repo)); by.delete(r.repo) }
  }
  for (const list of by.values()) out.push(...list)
  return out
}

// Follow-ups: what GitHub and GitLab finish in their own time shows without r. Right after a change (follow.now)
// the view asks again for just the repos it touched, and keeps asking while anything listed is still on its way
// (pending(): a PR with auto-merge on, a release run that hasn't finished): soon at first, then less often, only
// while the page is visible, and for at most FOLLOW_MS after the view opened or the last change.
const STEPS = [2000, 3000, 5000, 8000, 13000, 20000, 30000]
const FOLLOW_MS = 20 * 60_000
const AFTER_CHANGE_MS = 90_000 // a changed repo is followed this long even when nothing pending shows (yet)

export function useFollow({ pending, refresh }) {
  const extra = new Map() // repo -> until when it is followed after a change
  let timer = null
  let step = 0
  let since = Date.now()
  let running = false
  let stopped = false

  function repos() {
    const now = Date.now()
    for (const [r, until] of extra) if (until < now) extra.delete(r)
    return [...new Set([...(pending() || []), ...extra.keys()])].filter(Boolean)
  }
  function schedule(ms) {
    clearTimeout(timer)
    timer = null
    if (stopped || Date.now() - since > FOLLOW_MS || !repos().length) return
    timer = setTimeout(tick, ms ?? STEPS[Math.min(step, STEPS.length - 1)])
  }
  async function tick() {
    timer = null
    if (stopped || running) return
    if (typeof document !== 'undefined' && document.hidden) return // visible again: see below
    const list = repos()
    if (!list.length) return
    running = true
    try {
      await refresh(list)
    } catch (e) {
      if (e?.status === 429) step = STEPS.length // rate limited: slowest from now on
    } finally {
      running = false
    }
    step++
    schedule()
  }
  function now(changed = [], ms = AFTER_CHANGE_MS) {
    const until = Date.now() + ms
    for (const r of changed) if (r) extra.set(r, until)
    step = 0
    since = Date.now()
    schedule(0)
  }
  function visible() {
    if (typeof document === 'undefined' || document.hidden) return
    step = Math.min(step, 2)
    if (!running) schedule(0)
  }
  if (typeof document !== 'undefined') document.addEventListener('visibilitychange', visible)
  // something pending shows up (the first load, or a new answer): start following it
  const stop = watch(() => repos().join('\n'), (list) => { if (list && !timer && !running) schedule() })
  onScopeDispose(() => {
    stopped = true
    clearTimeout(timer)
    stop()
    if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', visible)
  })
  return { now }
}

// A change: ask first (y / d for a dry run / n), then send it; returns {text, dry, ok} (null when not asked to).
export async function change(question, path, body = {}, { detail = '' } = {}) {
  const a = await ask(question, { detail: detail || (state.dryRun ? 'dry run is on: nothing changes' : '') })
  if (!a) return null
  const dry = a === 'dry'
  try {
    const got = await post(path, { ...body, dry_run: dry })
    if (!dry) forget() // a change: every remembered answer may be stale now
    const text = got.text ?? ''
    const failed = /^\s*error/m.test(text)
    log(`${dry ? '[dry-run] ' : ''}${question.replace(/\?$/, '')}: ${failed ? 'had errors' : 'done'}`, failed ? 'error' : 'ok', { detail: text })
    return { text, dry, ok: !failed }
  } catch (e) {
    log(`${question.replace(/\?$/, '')}: ${e.message}`, 'error')
    return { text: `error: ${e.message}`, dry, ok: false }
  }
}

// The same, returning only the command output (or null).
export async function act(question, path, body = {}, opts = {}) {
  const got = await change(question, path, body, opts)
  return got && got.text
}
