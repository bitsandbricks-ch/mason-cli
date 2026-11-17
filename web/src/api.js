// Every call to the operator's /api/v1. Writes carry the session's CSRF token; errors become exceptions
// with the operator's message, which the views show in the log line.
import { reactive } from 'vue'
import { toast } from './toast.js'

export const state = reactive({
  me: null,          // /api/v1/me
  loaded: false,
  dryRun: savedDry(), // every change is a dry run while this is on (kept for this tab: a reload doesn't turn it off)
  unreachable: '', // why /me failed when the server couldn't answer it
  log: [],           // [{at, text, kind, detail, where}] the bottom log (click it for all of them)
  busy: 0,
  rate: null,
})

// dry run survives a reload of the tab: switched on as a safety, it mustn't go off without you noticing
function savedDry() { try { return sessionStorage.getItem('mason-dry-run') === '1' } catch { return false } }
export function keepDry(on) { try { if (on) sessionStorage.setItem('mason-dry-run', '1'); else sessionStorage.removeItem('mason-dry-run') } catch { /* private mode */ } }

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status }
}

// detail: the whole output of a change (shown when the entry is opened); where: the page it was done on.
// An ok or an error also shows as a toast (toast: the id of a "working" one it finishes, or false for none).
export function log(text, kind = 'info', { detail = '', where = '', toast: id = 0 } = {}) {
  const at = where || (typeof location !== 'undefined' ? location.pathname + location.search : '')
  state.log.unshift({ at: new Date().toLocaleTimeString(), text: String(text), kind, detail: String(detail || ''), where: at })
  if (state.log.length > 200) state.log.length = 200
  if (id !== false && (kind === 'ok' || kind === 'error' || id)) toast(text, kind, { detail, where: at, id })
}

// quiet: a background read (a follow-up, see useFollow) that doesn't light up "working…".
export async function api(method, path, body, { quiet = false, again = true } = {}) {
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
    } catch {
      // the browser's own words ("Failed to fetch", "NetworkError…") say nothing about what to do
      throw new ApiError(`can't reach Mason: check your connection${method === 'GET' ? '' : ' (the change may or may not have gone through)'}`, 0)
    }
    const data = res.status === 204 ? {} : await res.json().catch(() => ({}))
    if (!res.ok) {
      // signed in again in another tab: this tab's token is the old session's. The server refused the write
      // before doing anything, so ask for the new token and send it once more, if it is still the same person.
      if (res.status === 403 && again && /CSRF token/.test(data.error || '') && path !== '/me') {
        const was = state.me?.user?.id
        const now = await get('/me', { quiet: true }).catch(() => null)
        if (now?.user && now.user.id === was) { state.me = now; return api(method, path, body, { quiet, again: false }) }
        if (now) state.me = now // someone else, or signed out: the app shows that instead of acting for them
      }
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
