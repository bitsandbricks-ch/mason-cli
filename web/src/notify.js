import { ref } from 'vue'
import { log } from './api.js'

// Desktop notifications in this browser (a browser setting, so in localStorage, not in your settings): when a
// change you started finishes while the tab is in the background. Off until you turn them on in settings.
const KEY = 'mason-notify'
const read = () => { try { return localStorage.getItem(KEY) === '1' } catch { return false } }
export const notifyOn = ref(read())
export const notifySupported = () => typeof window !== 'undefined' && 'Notification' in window
export const permission = () => (notifySupported() ? Notification.permission : 'denied')

export async function setNotify(on) {
  if (on && notifySupported() && Notification.permission !== 'granted') {
    const got = await Notification.requestPermission().catch(() => 'denied')
    if (got !== 'granted') {
      log('the browser said no to notifications: allow them for this site in the browser, then try again', 'warn')
      on = false
    }
  }
  notifyOn.value = on
  try { localStorage.setItem(KEY, on ? '1' : '0') } catch { /* private mode: on for this tab only */ }
}
