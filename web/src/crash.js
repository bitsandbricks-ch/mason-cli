// When the page itself goes wrong. Two cases:
// - Mason was updated while the tab was open: the views are loaded on demand, and the old build's files are gone,
//   so a click on a tab did nothing at all. The page loads the new build instead, at the page that was asked for.
// - A bug in a view: it goes to the log line in words, instead of only to the browser console.

// The words browsers use when a script or style of the build can't be loaded (Chrome, Firefox, Safari, Vite).
const STALE = /dynamically imported module|Importing a module script failed|Unable to preload CSS|module script.*MIME type/i

export const isStaleBuild = (err) => STALE.test(String(err?.message || err || ''))

// Reload at most once a minute: a build that really is broken must not reload forever.
const KEY = 'mason-reloaded'
const GAP_MS = 60_000
export function mayReload(storage, now = Date.now()) {
  let last = 0
  try { last = Number(storage?.getItem(KEY)) || 0 } catch { /* private mode */ }
  if (now - last < GAP_MS) return false
  try { storage?.setItem(KEY, String(now)) } catch { /* private mode: a reload may then happen once more */ }
  return true
}

// What the log line says for a bug: the message, without a stack.
export function crashText(err) {
  const what = String(err?.message || err || 'unknown error').split('\n')[0].slice(0, 200)
  return `something went wrong on this page: ${what}. Reloading the page starts over`
}
