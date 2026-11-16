// Saved views: a list as you set it up (which view, its filter, the group and provider), under a name, in
// your settings (settings.views), so every browser you sign in with has them. The rules are pure, for node --test.

export const MAX_VIEWS = 30

// The link a saved view keeps: the page and its query, plus the group and provider filter (which otherwise
// live in this browser only), without #detail.
export function viewPath(route, scope = {}) {
  const q = { ...(route.query || {}) }
  delete q.side // the side panel's item is what you looked at, not part of the view
  if (scope.group) q.group = scope.group
  else delete q.group
  if (scope.provider && scope.provider !== 'all') q.provider = scope.provider
  else delete q.provider
  const s = new URLSearchParams(Object.entries(q).filter(([, v]) => v != null && v !== '').map(([k, v]) => [k, String(v)])).toString()
  return route.path + (s ? `?${s}` : '')
}

// Add (or rename onto) a view: one per name and one per link, newest last, at most MAX_VIEWS.
export function addView(list, name, path) {
  const n = String(name || '').trim().slice(0, 40)
  if (!n) return list || []
  const rest = (list || []).filter((v) => v.name.toLowerCase() !== n.toLowerCase() && v.path !== path)
  return [...rest, { name: n, path }].slice(-MAX_VIEWS)
}

export const removeView = (list, path) => (list || []).filter((v) => v.path !== path)

// The scope a link asks for: ?group= and ?provider= (null when the link says nothing)
export function scopeFrom(query) {
  const out = {}
  if (typeof query?.group === 'string') out.group = query.group
  if (['all', 'github', 'gitlab'].includes(query?.provider)) out.provider = query.provider
  return Object.keys(out).length ? out : null
}

// A short name to suggest: "pull requests · mine · acme/"
export function suggestName(label, route, scope = {}) {
  const q = route.query || {}
  return [label, q.show, q.filter, scope.group].filter(Boolean).join(' · ').slice(0, 40)
}
