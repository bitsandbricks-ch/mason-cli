// Links that come from elsewhere (GitHub's and GitLab's answers, a plugin, the plugin index): only http(s) ones
// become links. The CSP already blocks javascript: URLs; this keeps them from even being links, and keeps a
// data: or file: URL out of a new tab. No imports, so node --test can run it (web/test/links.test.js).

export function safeHref(url) {
  const u = String(url ?? '').trim()
  return /^https?:\/\/[^\s/]/i.test(u) ? u : ''
}

// open an outside link in a new tab, without handing it this window (noopener); nothing for a bad one
export function openOut(url, win = globalThis.window) {
  const u = safeHref(url)
  if (u) win?.open(u, '_blank', 'noopener')
  return !!u
}

// A view's file that the server no longer has (an update came in since the tab opened).
export function staleChunk(err) {
  return /dynamically imported module|Importing a module script failed|error loading dynamically|Unable to preload CSS/i.test(String(err?.message || err || ''))
}
