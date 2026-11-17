<script setup>
// One repo as a page (Enter on Repos): its whole detail, what you can do with it, and what that printed;
// its drift against the defaults (doctor: the kept check, or checked when the page opens), its open PRs as links to their
// pages, and its event log at the bottom. After a change, and while a release run is going, the page reads
// the repo again by itself (see useFollow).
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { usePage } from '../side.js'
import { qs } from '../api.js'
import { cached, change, forget, useFollow } from '../load.js'
import { toast } from '../toast.js'
import { useKeys } from '../keys.js'
import DoctorPanel from '../components/DoctorPanel.vue'
import ActionList from '../components/ActionList.vue'
import BranchesPanel from '../components/BranchesPanel.vue'
import EventLog from '../components/EventLog.vue'
import StatusHeader from '../components/StatusHeader.vue'
import ReleaseForm from '../components/ReleaseForm.vue'
import MasonPanel from '../components/MasonPanel.vue'
import SecretsPanel from '../components/SecretsPanel.vue'
import SettingsPanel from '../components/SettingsPanel.vue'
import TextPane from '../components/TextPane.vue'
import VersionBar from '../components/VersionBar.vue'
import { stateClass } from '../ui.js'
import { pinned, togglePin } from '../pins.js'
import { openOut } from '../links.js'

// the route's query, or the side panel's when it shows in one (and then back closes the panel)
const { query, back } = usePage('/')
const router = useRouter()
const repo = computed(() => String(query.value.repo || ''))
const gitlab = computed(() => repo.value.startsWith('gitlab:'))
// no GitLab (or GitHub) account to read it with: one card that says how, instead of an error in every panel
const needs = computed(() => (/^error: connect (GitLab|GitHub)\b/i.exec(detail.value) || [])[1] || '')
const detail = ref('')
const output = ref('')
const form = ref('') // '', 'release' or 'tag'
const formEl = ref(null) // the release form: asks before its notes go
const suggest = ref('')
const publishes = ref('')
const version = ref(null)
const busy = ref(false) // a release run is going
const checked = ref(0) // bumped after c or f: the doctor panel shows the new result
const info = ref(null) // /repo's info: what the status header shows
const doctor = ref(null) // the doctor panel's last result
const sheet = ref(null)
const vbar = ref(null)
const running = ref('') // the key of the action under way: its button says so (one at a time)
const ended = reactive({}) // {key: 'ok' | 'bad'}: how an action just ended, shown on its button for a while
let fixed = '' // a fix just ran on this repo: say what's left once the defaults panel has checked again

async function load(fresh = false) {
  if (!repo.value) return
  if (!detail.value) detail.value = '…'
  try { const got = await cached(`/repo${qs({ repo: repo.value, fresh })}`, fresh); detail.value = got.text; info.value = got.info || null } catch (e) { detail.value = `error: ${e.message}` }
}

// the open PRs (and MRs), as links to their pages
const pulls = computed(() => info.value?.prs || [])
const ready = computed(() => pulls.value.filter((p) => !p.draft && (p.merge || 'mergeable') === 'mergeable'))
// what the header shows; the text below keeps only what it doesn't (plugin lines, recently merged)
const badges = computed(() => {
  const i = info.value
  if (!i) return []
  const out = []
  if (i.ci || !gitlab.value) out.push({ label: 'CI', value: i.ci || 'no runs', href: i.actions_url, cls: i.ci ? undefined : '' })
  const v = version.value
  out.push({ label: 'released', value: i.released || 'never', to: { path: '/release', query: { repo: repo.value } }, cls: i.released ? '' : 'warn' })
  if (v?.todo) out.push({ label: v.file || 'version', value: `${v.version} not released`, cls: 'warn' })
  const drafts = pulls.value.filter((p) => p.draft).length
  out.push({ label: gitlab.value ? 'MRs' : 'PRs', value: pulls.value.length ? `${pulls.value.length} open${drafts ? ` (${drafts} draft)` : ''}` : 'none', cls: '' })
  const d = doctor.value
  if (d) out.push({ label: 'defaults', value: d.error ? 'check failed' : d.ok ? 'ok' : `${d.problems.length} issue${d.problems.length === 1 ? '' : 's'}`, cls: d.error ? 'bad' : d.ok ? 'ok' : 'warn' })
  out.push({ label: 'group', value: i.group || 'default', cls: '' })
  return out
})
// one next step, the most useful first: CI red, drift, an unreleased version, ready PRs
const next = computed(() => {
  const i = info.value
  if (!i) return null
  if (/fail|error/.test(i.ci)) return { text: 'CI fails on the default branch.', label: 'see the runs', fn: () => router.push({ path: '/runs', query: { repo: repo.value } }), cls: 'bad' }
  if (doctor.value && !doctor.value.ok && !doctor.value.error) return { text: `${doctor.value.problems.length} setting${doctor.value.problems.length === 1 ? '' : 's'} differ from the defaults.`, label: 'fix the drift', key: 'f', fn: actions.value.find((a) => a.k === 'f').fn }
  if (version.value?.todo) return { text: `${version.value.version} isn't released yet.`, label: `release ${version.value.tag}`, key: 'R', fn: () => vbar.value?.release() }
  if (ready.value.length) return { text: `${ready.value.length} PR${ready.value.length === 1 ? ' is' : 's are'} ready to merge.`, label: 'auto-merge them', key: 'm', fn: actions.value.find((a) => a.k === 'm').fn }
  return { text: 'nothing waiting on you.', cls: 'ok' }
})
const rest = computed(() => {
  const lines = detail.value.split('\n').slice(2)
  const out = []
  let skipping = false
  for (const l of lines) {
    if (/^open (pull|merge) requests/.test(l)) { skipping = true; continue }
    if (skipping) { if (/^\s/.test(l)) continue; skipping = false }
    if (/^(group|released|CI)\s/.test(l)) continue
    out.push(l)
  }
  return out.join('\n').replace(/\n{3,}/g, '\n\n').trim()
})
const log = ref(null)

async function run(q, path, body, k = '') {
  if (running.value) {
    toast(`wait: ${actions.value.find((a) => a.k === running.value)?.label || 'a change'} is still under way`, 'info')
    return
  }
  const name = repo.value
  let got
  try {
    got = await change(q, path, body, { started: () => { running.value = k } })
  } finally { running.value = '' }
  if (got === null || name !== repo.value) return
  output.value = got.text
  if (k) mark(k, got.ok)
  forget('/status'); forget('/repo'); forget('/release')
  load(true)
  follow.now([repo.value])
  log.value?.burst()
  if (path !== '/doctor') return
  if (body.fix && !got.dry && got.ok) { fixed = name; doctorPanel.value?.load(true) } else checked.value++
}
const timers = {}
function mark(k, ok) {
  ended[k] = ok ? 'ok' : 'bad'
  clearTimeout(timers[k])
  timers[k] = setTimeout(() => { delete ended[k] }, 8000)
}
// the defaults panel's new result: after a fix, say whether it's all fixed now or what is left
function checkedNow(d) {
  doctor.value = d
  if (!fixed || fixed !== repo.value || d.repo !== repo.value) return
  fixed = ''
  if (d.ok) toast(`${repo.value} matches its defaults now`, 'ok')
  else if (!d.error) {
    const n = d.problems.length
    toast(`${repo.value}: ${n} issue${n === 1 ? '' : 's'} left that fixing the drift can't change: see "defaults"`, 'info',
      { detail: d.problems.join('\n') })
  }
}
const r = () => [repo.value]
const fixFrom = (kind) => (kind === 'protect' ? masonPanel.value?.protectNow()
  : actions.value.find((a) => a.k === (kind === 'sync' ? 's' : 'f'))?.fn())
const actions = computed(() => [
  { k: 'c', group: 'defaults', label: 'check against the defaults', fn: () => run(`Check ${repo.value} against the defaults?`, '/doctor', { repos: r() }, 'c') },
  { k: 'f', group: 'defaults', label: 'fix the drift', fn: () => run(`Fix the drift of ${repo.value} (settings, security, rulesets)?`, '/doctor', { repos: r(), fix: true }, 'f') },
  { k: 's', group: 'defaults', label: 'open a PR with the shared files', fn: () => run(`Open a PR that syncs the shared files into ${repo.value}?`, '/sync', { repos: r() }, 's') },
  { k: 'm', group: 'pull requests', off: !pulls.value.length, label: 'auto-merge the ready ones', fn: () => run(`Auto-merge the ready PRs of ${repo.value}?`, '/merge', { targets: r() }, 'm') },
  { k: 'M', group: 'pull requests', off: !pulls.value.length, label: 'merge the ready ones now', fn: () => run(`Merge the ready PRs of ${repo.value} now?`, '/merge', { targets: r(), now: true }, 'M') },
  { k: 'n', group: 'releases', primary: true, label: 'create a release', fn: () => newRelease('release') },
  { k: 'T', group: 'releases', label: 'push a tag (its workflow releases)', fn: () => newRelease('tag') },
  { k: 'l', group: 'releases', label: 'all its releases', fn: () => router.push({ path: '/release', query: { repo: repo.value } }) },
  { k: '*', group: 'elsewhere', label: pinned.value.has(repo.value) ? 'unpin from the top of the lists' : 'pin to the top of the lists', fn: () => togglePin(repo.value) },
  { k: 'o', group: 'elsewhere', label: `open on ${gitlab.value ? 'GitLab' : 'GitHub'}`, fn: open },
])
async function loadReleases(fresh = false, quiet = false) {
  const name = repo.value
  try {
    const p = await cached(`/release${qs({ repo: name, fresh })}`, fresh, { quiet })
    if (name !== repo.value) return // the panel moved on to another repo
    suggest.value = p.suggest; publishes.value = p.publishes || ''; version.value = p.version || null; busy.value = !!p.busy
  } catch { suggest.value = suggest.value || 'v0.1.0' }
}
async function refresh() {
  const name = repo.value
  const got = await cached(`/repo${qs({ repo: name, fresh: true })}`, true, { quiet: true })
  if (name === repo.value) detail.value = got.text
  await loadReleases(true, true)
}
const follow = useFollow({ pending: () => (busy.value ? [repo.value] : []), refresh })
async function newRelease(mode) {
  form.value = mode
  if (!suggest.value) await loadReleases()
}
function done({ text, ok }) { output.value = text; if (ok) { form.value = ''; forget('/release'); forget('/releases'); follow.now([repo.value]); log.value?.burst() } }
const open = () => { const url = info.value?.url || detail.value.split('\n')[1]; openOut(url) }
const doctorPanel = ref(null)
const masonPanel = ref(null)
const settingsPanel = ref(null)
const branchesPanel = ref(null)
const reload = () => { load(true); log.value?.refresh(); doctorPanel.value?.load(true); masonPanel.value?.load(); settingsPanel.value?.load(); branchesPanel.value?.load() }
const keys = { '.': () => sheet.value?.pick(), Escape: async () => { if (!form.value) back(); else if (await formEl.value?.leave() !== false) form.value = '' }, Backspace: back, r: () => reload() }
watch(actions, (list) => list.forEach((a) => { keys[a.k] = () => !a.off && a.fn() }), { immediate: true })
useKeys(keys)
// last: the immediate watch uses everything above
watch(repo, () => { fixed = ''; detail.value = ''; output.value = ''; form.value = ''; version.value = null; suggest.value = ''; info.value = null; doctor.value = null; load(); loadReleases() }, { immediate: true })
</script>

<template>
  <div class="view">
    <div class="toolbar">
      <button class="hide-xs" @click="back"><span class="k">esc</span> back</button>
      <span class="dim hide-xs">repos ›</span>
      <span class="spacer" />
      <ActionList v-if="!needs" ref="sheet" class="show-compact" :actions="actions" :title="repo" :running="running" compact />
      <button class="any" @click="reload"><span class="k">r</span> reload</button>
    </div>
    <StatusHeader :title="pinned.has(repo) ? `★ ${repo}` : repo" :url="info?.url" :badges="badges"
                  :next="next && { ...next, busy: !!next.key && running === next.key }" />
    <div v-if="needs" class="pad">
      <div class="box">
        <p>Mason reads {{ repo }} with your {{ needs }} account, and none is connected yet.</p>
        <router-link class="btn primary" to="/settings">connect {{ needs }} in settings</router-link>
      </div>
    </div>
    <div v-else class="split page repo-cols">
      <div class="pad">
        <div class="hide-xs"><h2>actions</h2><ActionList :actions="actions" :running="running" :ended="ended" /></div>
        <!-- right under the buttons that made it, not below every panel -->
        <template v-if="output"><h2 class="row" style="margin-top: 16px">output <span class="spacer" /><button class="link" @click="output = ''">clear</button></h2><TextPane :text="output" /></template>
        <DoctorPanel ref="doctorPanel" :repo="repo" :stamp="checked" :running="running" @result="checkedNow" @run="fixFrom" />
        <MasonPanel ref="masonPanel" :repo="repo" @done="({ text, ok }) => { output = text; if (ok) { checked++; log?.burst() } }" />
        <SecretsPanel v-if="!gitlab" :repo="repo" @done="({ text }) => (output = text)" />
        <SettingsPanel ref="settingsPanel" :repo="repo" @done="({ text, ok }) => { output = text; if (ok) { checked++; masonPanel?.load(); log?.burst() } }" />
      </div>
      <div class="pad">
        <VersionBar v-if="version" ref="vbar" :repo="repo" :version="version" @done="done" />
        <ReleaseForm v-if="form" ref="formEl" :key="form" :mode="form" :repo="repo" :suggest="suggest" :publishes="publishes"
                     @done="done" @cancel="form = ''" />
        <h2>{{ gitlab ? 'merge requests' : 'pull requests' }} <span class="dim">({{ pulls.length }})</span></h2>
        <ul v-if="pulls.length" class="pull-list">
          <li v-for="p in pulls" :key="p.number">
            <router-link :to="{ path: '/pr', query: { repo, number: p.number } }">
              <span class="dim">{{ gitlab ? '!' : '#' }}{{ p.number }}</span> {{ p.title }}</router-link>
            <span v-if="p.draft" class="dim">draft</span>
            <span v-else-if="p.merge" :class="stateClass(p.merge)">{{ p.merge }}</span>
            <span v-if="p.checks && p.checks !== 'no checks'" :class="stateClass(p.checks)">checks {{ p.checks }}</span>
          </li>
        </ul>
        <div v-else-if="info" class="empty" style="padding: 0 0 8px">no open {{ gitlab ? 'merge' : 'pull' }} requests</div>
        <BranchesPanel ref="branchesPanel" :repo="repo" @done="({ text, ok }) => { output = text; if (ok) { load(true); log?.burst() } }" />
        <TextPane v-if="rest || !info" :text="info ? rest : detail" placeholder="loading…" />
      </div>
    </div>
    <EventLog v-if="!needs" ref="log" band :repo="repo" kind="repo" :title="repo" />
  </div>
</template>
