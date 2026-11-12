import { createRouter, createWebHistory } from 'vue-router'

const v = (name) => () => import(`./views/${name}.vue`)

// The tab bar shows sections, not every view: a section's views are its sub-tabs (the second row). Paths and
// keys stay the same, so links and muscle memory still work. group and hint: the phone menu, which lists
// every view by group with what it is for.
export const TABS = [
  { path: '/', name: 'repos', label: 'repos', key: '1', section: 'repos', group: 'work', hint: 'every repo: drift, PRs, CI' },
  { path: '/prs', name: 'prs', label: 'pull requests', key: '2', section: 'prs', group: 'work', hint: 'open pull and merge requests' },
  { path: '/issues', name: 'issues', label: 'issues', key: 'I', section: 'issues', group: 'work', hint: 'issues across your repos' },
  { path: '/runs', name: 'runs', label: 'runs', key: '3', section: 'runs', group: 'work', hint: 'latest workflow runs' },
  { path: '/approvals', name: 'approvals', label: 'approvals', key: '4', section: 'runs', group: 'work', hint: 'runs waiting for you' },
  { path: '/releases', name: 'releases', label: 'releases', key: '5', section: 'releases', group: 'work', hint: 'latest releases, new ones' },
  { path: '/checks', name: 'checks', label: 'checks', key: '8', section: 'health', group: 'health', hint: 'check, fix drift, sync files' },
  { path: '/security', name: 'security', label: 'security', key: '7', section: 'health', group: 'health', hint: 'open security alerts' },
  { path: '/packages', name: 'packages', label: 'packages', key: '6', section: 'health', group: 'health', hint: 'container images' },
  { path: '/workflows', name: 'workflows', label: 'workflows', key: 'W', section: 'health', group: 'health', hint: 'actions not pinned to a commit' },
  { path: '/stats', name: 'stats', label: 'stats', key: '9', section: 'health', group: 'health', hint: 'merges, runs and releases' },
  { path: '/settings', name: 'settings', label: 'settings', key: 'S', section: 'setup', group: 'setup', hint: 'accounts, repos, API keys' },
  { path: '/defaults', name: 'defaults', label: 'defaults', key: 'D', section: 'setup', group: 'setup', hint: 'edit mason.toml and the shared files' },
  { path: '/plugins', name: 'plugins', label: 'plugins', key: 'P', section: 'setup', group: 'setup', hint: 'your plugins and their actions' },
  { path: '/market', name: 'market', label: 'market', key: 'K', section: 'setup', group: 'setup', hint: 'plugins to install' },
  { path: '/audit', name: 'audit', label: 'audit', key: 'L', section: 'setup', group: 'setup', hint: 'what was done, and by whom' },
  { path: '/console', name: 'console', label: 'console', key: ':', section: 'setup', group: 'setup', hint: 'type mason commands' },
]

export const GROUPS = ['work', 'health', 'setup']

// The tab bar: one entry per section, opening its first view. Detail pages (a repo, a PR, a run) light up
// their section through meta.tab.
export const SECTIONS = [
  { name: 'repos', label: 'repos' },
  { name: 'prs', label: 'pull requests' },
  { name: 'issues', label: 'issues' },
  { name: 'runs', label: 'runs' },
  { name: 'releases', label: 'releases' },
  { name: 'health', label: 'health' },
  { name: 'setup', label: 'setup' },
].map((s) => {
  const views = TABS.filter((t) => t.section === s.name)
  return { ...s, views, path: views[0].path, key: views[0].key }
})
export const sectionOf = (tab) => TABS.find((t) => t.name === tab)?.section || (tab === 'plugin-tab' || tab === 'operator' ? 'setup' : '')

const VIEWS = {
  repos: 'Repos', prs: 'Prs', issues: 'Issues', runs: 'Runs', approvals: 'Approvals', releases: 'Releases', packages: 'Packages',
  security: 'Security', checks: 'Checks', workflows: 'Workflows', stats: 'Stats', defaults: 'Defaults', console: 'Console',
  plugins: 'Plugins', market: 'Market', settings: 'Settings', audit: 'Audit',
}

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: v('Login'), meta: { public: true } },
    { path: '/device', name: 'device', component: v('Device') },
    ...TABS.map((t) => ({ path: t.path, name: t.name, component: v(VIEWS[t.name]) })),
    { path: '/repo', name: 'repo', component: v('RepoPage'), meta: { tab: 'repos' } },
    { path: '/release', name: 'release', component: v('ReleasePage'), meta: { tab: 'releases' } },
    { path: '/pr', name: 'pr', component: v('PrPage'), meta: { tab: 'prs' } },
    { path: '/issue', name: 'issue', component: v('IssuePage'), meta: { tab: 'issues' } },
    { path: '/run', name: 'run', component: v('RunPage'), meta: { tab: 'runs' } },
    { path: '/plugins/:plugin/:tab', name: 'plugin-tab', component: v('PluginTab') },
    { path: '/operator', name: 'operator', component: v('Operator') },
    { path: '/:rest(.*)*', redirect: '/' },
  ],
})
