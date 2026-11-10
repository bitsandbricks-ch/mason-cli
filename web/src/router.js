import { createRouter, createWebHistory } from 'vue-router'

const v = (name) => () => import(`./views/${name}.vue`)

// group and hint: the phone menu, which lists every view by group with what it is for.
export const TABS = [
  { path: '/', name: 'repos', label: 'repos', key: '1', group: 'work', hint: 'every repo: drift, PRs, CI' },
  { path: '/prs', name: 'prs', label: 'pull requests', key: '2', group: 'work', hint: 'open pull and merge requests' },
  { path: '/issues', name: 'issues', label: 'issues', key: 'I', group: 'work', hint: 'issues across your repos' },
  { path: '/runs', name: 'runs', label: 'runs', key: '3', group: 'work', hint: 'latest workflow runs' },
  { path: '/approvals', name: 'approvals', label: 'approvals', key: '4', group: 'work', hint: 'runs waiting for you' },
  { path: '/releases', name: 'releases', label: 'releases', key: '5', group: 'work', hint: 'latest releases, new ones' },
  { path: '/packages', name: 'packages', label: 'packages', key: '6', group: 'health', hint: 'container images' },
  { path: '/security', name: 'security', label: 'security', key: '7', group: 'health', hint: 'open security alerts' },
  { path: '/checks', name: 'checks', label: 'checks', key: '8', group: 'health', hint: 'check, fix drift, sync files' },
  { path: '/workflows', name: 'workflows', label: 'workflows', key: 'W', group: 'health', hint: 'actions not pinned to a commit' },
  { path: '/stats', name: 'stats', label: 'stats', key: '9', group: 'health', hint: 'merges, runs and releases' },
  { path: '/defaults', name: 'defaults', label: 'defaults', key: 'D', group: 'setup', hint: 'edit mason.toml and the shared files' },
  { path: '/console', name: 'console', label: 'console', key: ':', group: 'setup', hint: 'type mason commands' },
  { path: '/plugins', name: 'plugins', label: 'plugins', key: 'P', group: 'setup', hint: 'your plugins and their actions' },
  { path: '/market', name: 'market', label: 'market', key: 'K', group: 'setup', hint: 'plugins to install' },
  { path: '/settings', name: 'settings', label: 'settings', key: 'S', group: 'setup', hint: 'accounts, repos, API keys' },
  { path: '/audit', name: 'audit', label: 'audit', key: 'L', group: 'setup', hint: 'what was done, and by whom' },
]

export const GROUPS = ['work', 'health', 'setup']

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
    { path: '/plugins/:plugin/:tab', name: 'plugin-tab', component: v('PluginTab') },
    { path: '/operator', name: 'operator', component: v('Operator') },
    { path: '/:rest(.*)*', redirect: '/' },
  ],
})
