// Offline: when the server doesn't answer, try again on its own (2s, 4s, 8s … up to 30s, and at once when the
// browser says it is online again), and say so in a banner instead of a stream of errors. The delays are pure,
// for node --test.
import { reactive, watch } from 'vue'
import { api, log, state } from './api.js'

export function nextDelay(attempt) {
  return Math.min(30_000, 2000 * 2 ** Math.max(0, attempt))
}

export const net = reactive({ retryAt: 0, tries: 0 })
let timer = null

export async function retry() {
  clearTimeout(timer)
  timer = null
  try {
    const me = await api('GET', '/me', undefined, { quiet: true })
    const first = !state.me?.user
    state.me = me
    net.tries = 0
    log(first ? 'connected to the Mason server' : 'the Mason server answers again', 'ok')
  } catch {
    if (state.offline) schedule()
  }
}

function schedule() {
  if (timer) return
  const wait = nextDelay(net.tries++)
  net.retryAt = Date.now() + wait
  timer = setTimeout(retry, wait)
}

watch(() => state.offline, (off) => { if (off) schedule(); else { clearTimeout(timer); timer = null; net.tries = 0 } })
if (typeof window !== 'undefined') window.addEventListener('online', () => { if (state.offline) retry() })
