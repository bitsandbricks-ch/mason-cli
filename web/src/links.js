// Links from data (GitHub, GitLab, plugins, the plugin index): only http(s) ever becomes an href or a new tab.
// The CSP already stops javascript: links from running; this keeps them from being links at all.
export function safeUrl(url) {
  const s = String(url || '').trim()
  return /^https?:\/\/[^\s/]/i.test(s) ? s : ''
}

// Open a link in a new tab, without giving the page a handle on this one.
export function openLink(url) {
  const s = safeUrl(url)
  if (s) window.open(s, '_blank', 'noopener,noreferrer')
  return !!s
}

// Where to go after signing in: a path on this site, like the server's safe_next, else '/'.
export function safeNext(next) {
  const s = String(next || '/')
  return s.length < 200 && /^\/(?![/\\])[A-Za-z0-9/._~%!$&'()*+,;=:@?#-]*$/.test(s) ? s : '/'
}
