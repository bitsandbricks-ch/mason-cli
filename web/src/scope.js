import { reactive, watch } from 'vue'
import { get, qs } from './api.js'

// Shared by every list: the provider and group filter, the groups of the defaults, and the orgs (GitHub)
// and GitLab groups the repos are in. An org filters as `acme/` or `gitlab:grp/`.
// The filter outlives a reload and a new tab (it was lost on each, so pages opened from a link showed every
// repo again); ?group= and ?provider= in a link win over the saved one.
const KEY = 'mason-scope'
function saved() {
  let out = {}
  try { out = JSON.parse(localStorage.getItem(KEY) || '{}') || {} } catch { /* private mode */ }
  try {
    const q = new URLSearchParams(window.location.search)
    if (q.has('group')) out.group = q.get('group')
    if (q.has('provider')) out.provider = q.get('provider')
  } catch { /* no window */ }
  return {
    provider: ['all', 'github', 'gitlab'].includes(out.provider) ? out.provider : 'all',
    group: typeof out.group === 'string' ? out.group : '',
  }
}
export const scope = reactive({ ...saved(), groups: [], owners: [] })
watch(() => [scope.provider, scope.group], ([provider, group]) => {
  try { localStorage.setItem(KEY, JSON.stringify({ provider, group })) } catch { /* private mode */ }
})

// The scope as a request body (posts: checks, sync, merge) or query.
export function scoped() {
  return { provider: scope.provider === 'all' ? undefined : scope.provider, group: scope.group || undefined }
}

// The filter in words: "org acme", "group plugins", "every repo"; with the provider when it is one.
export function scopeLabel() {
  const g = scope.group.endsWith('/') ? ownerLabel(scope.group) : scope.group ? `group ${scope.group}` : 'every repo'
  return scope.provider === 'all' ? g : `${g} on ${scope.provider}`
}

// How an org filter reads in a menu: acme/ -> org acme, gitlab:a/b/ -> gitlab a/b.
export function ownerLabel(o) {
  return o.startsWith('gitlab:') ? `gitlab ${o.slice(7, -1)}` : `org ${o.slice(0, -1)}`
}

let loading = null
export function loadGroups() {
  if (!loading) {
    loading = get('/repos').then((r) => {
      scope.groups = r.groups || []
      scope.owners = r.owners || []
      // a saved group that is gone (renamed in the defaults, an org you left) would hide every repo
      if (scope.group && !scope.groups.includes(scope.group) && !scope.owners.includes(scope.group)) scope.group = ''
      return r
    }).catch(() => { loading = null })
  }
  return loading
}

// The repos the filter lets through, for pickers (a new release's or issue's repo).
export async function scopedRepos() {
  const r = await get(`/repos${qs(scoped())}`)
  return r.repos.map((x) => x.repo)
}
