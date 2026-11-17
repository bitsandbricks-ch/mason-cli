// Toasts: a change you started says when it's under way, and then whether it worked, wherever you are in the
// app, without looking for the log line at the bottom. Every ok or error the log gets shows as one (see log()
// in api.js); a change shows "working" first and turns into its result in the same place (working()).
import { reactive } from 'vue'

export const toasts = reactive([]) // [{id, text, kind: 'busy' | 'ok' | 'error' | 'info', detail, where}], newest first
const LIFE = { ok: 5000, info: 6000, error: 12000 } // ms; a busy one stays until it's done
const MAX = 4
const timers = new Map()
let next = 1

// Show text (or change the toast `id` to it). The same text shown again restarts its timer instead of stacking.
export function toast(text, kind = 'info', { detail = '', where = '', id = 0 } = {}) {
  let t = (id && toasts.find((x) => x.id === id)) || toasts.find((x) => x.text === text && x.kind === kind)
  if (!t) {
    toasts.unshift({ id: next++ })
    t = toasts[0]
  }
  Object.assign(t, { text: String(text), kind, detail: String(detail || ''), where })
  clearTimeout(timers.get(t.id))
  if (kind !== 'busy') timers.set(t.id, setTimeout(() => dismiss(t.id), LIFE[kind] || LIFE.info))
  // too many: the oldest finished one goes (one still working stays)
  while (toasts.length > MAX) {
    const old = [...toasts].reverse().find((x) => x.kind !== 'busy')
    if (!old) break
    dismiss(old.id)
  }
  return t.id
}

export function dismiss(id) {
  clearTimeout(timers.get(id))
  timers.delete(id)
  const i = toasts.findIndex((x) => x.id === id)
  if (i >= 0) toasts.splice(i, 1)
}

// A change under way: working('Fix the drift of acme/web') shows it, and the toast it returns becomes the result
// when log() is given it ({ toast: id }), or with done(text, kind).
export function working(text) {
  const id = toast(`${text}…`, 'busy')
  return { id, done: (said, kind = 'ok', opts = {}) => toast(said, kind, { ...opts, id }), drop: () => dismiss(id) }
}
