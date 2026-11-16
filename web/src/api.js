// Every call to the operator's /api/v1. Writes carry the session's CSRF token; errors become exceptions
// with the operator's message, which the views show in the log line.
import { reactive, watch } from 'vue'

export const state = reactive({
  me: null,          // /api/v1/me
  loaded: false,
  dryRun: dryAtStart(), // every change is a dry run while this is on
  log: [],           // [{at, text, kind, detail, where}] the bottom log (click it for all of them)
  busy: 0,
  rate: null,
  unreachable: '', // why /me failed when the server couldn't answer it
})

// Dry run outlives a reload of the tab: turned on to try things out, a reload must not quietly make the next
// change a real one. Per tab (sessionStorage), so a new tab starts with real changes, as the header shows.
function dryAtStart() {
  try { return sessionStorage.getItem('mason-dry-run') === '1' } catch { return false }
}
watch(() => state.dryRun, (on) => {
  try { if (on) sessionStorage.setItem('mason-dry-run', '1'); else sessionStorage.removeItem('mason-dry-run') } catch { /* private mode */ }
})

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status }
}

// detail: the whole output of a change (shown when the entry is opened); where: the page it was done on
export function log(text, kind = 'info', { detail = '', where = '' } = {}) {
  state.log.unshift({ at: new Date().toLocaleTimeString(), text: String(text), kind, detail: String(detail || ''),
    where: where || (typeof location !== 'undefined' ? location.pathname + location.search : '') })
  if (state.log.length > 200) state.log.length = 200
}

// quiet: a background read (a follow-up, see useFollow) that doesn't light up "working…".
export async function api(method, path, body, { quiet = false } = {}) {
  const headers = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (method !== 'GET' && state.me?.csrf) headers['X-CSRF-Token'] = state.me.csrf
  if (!quiet) state.busy++
  try {
    let res
    try {
      res = await fetch(`/api/v1${path}`, {
        method, headers, credentials: 'same-origin', body: body === undefined ? undefined : JSON.stringify(body),
      })
    } catch { // the browser's own words ("Failed to fetch", "NetworkError…") don't say what to do
      throw new ApiError("can't reach Mason: check your connection and try again", 0)
    }
    const data = res.status === 204 ? {} : await res.json().catch(() => ({}))
    if (!res.ok) {
      if (res.status === 401 && path !== '/me') { state.me = { user: null, providers: state.me?.providers || [] } }
      throw new ApiError(data.error || `${res.status} ${res.statusText}`, res.status)
    }
    return data
  } finally {
    if (!quiet) state.busy--
  }
}

export const get = (path, opts) => api('GET', path, undefined, opts)
export const post = (path, body = {}) => api('POST', path, body)
export const put = (path, body = {}) => api('PUT', path, body)
export const del = (path) => api('DELETE', path)

// Signed out or account gone: what this account typed (console history with comments and titles) and the
// log of its outputs stay with it, not with the next person on this browser.
export function forgetLocal() {
  try { localStorage.removeItem('mason.console.history') } catch { /* private mode */ }
  state.log.length = 0
}

export async function loadMe() {
  state.unreachable = ''
  try { state.me = await get('/me') } catch (e) {
    // down or unreachable isn't signed out: say so and offer a retry instead of a sign-in page with no way in
    if (e.status === 0 || e.status >= 500) state.unreachable = e.status ? `Mason answered ${e.message}` : e.message
    state.me = { user: null, providers: [] }
    log(e.message, 'error')
  }
  state.loaded = true
  return state.me
}

export function qs(params) {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '' || v === false) continue
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x)); else p.append(k, v === true ? '1' : v)
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}
