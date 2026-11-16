// The browser tab's title: the page you are on ("acme/web#7 · pull requests · Mason"), so tabs and history
// read at a glance. When a change finishes while the tab is in the background, its result leads the title
// (✓ or ✗) until you come back. The naming is a pure function, for node --test.

const PAGES = { repo: 'repos', pr: 'pull requests', issue: 'issues', run: 'runs', release: 'releases' }

// route: {name, query, params}; tabs: router.js TABS
export function pageTitle(route, tabs) {
  const q = route?.query || {}
  const name = route?.name
  let where = tabs.find((t) => t.name === name)?.label
  if (!where && PAGES[name]) {
    const which = q.number ? `${q.repo}#${q.number}` : q.id ? `${q.repo} run ${q.id}` : q.tag ? `${q.repo} ${q.tag}` : q.repo
    where = which ? `${which} · ${PAGES[name]}` : PAGES[name]
  }
  if (!where && name === 'plugin-tab') where = `${route.params?.plugin || 'plugin'}`
  if (!where && name && name !== 'login') where = String(name)
  return where ? `${where} · Mason` : 'Mason'
}

// the mark a finished change puts in front while the tab is hidden: an error wins over a success
export function markFor(kinds) {
  if (kinds.includes('error')) return '✗'
  if (kinds.includes('ok')) return '✓'
  return ''
}
