<script setup>
// One repo as a page (Enter on Repos): its whole detail, what you can do with it, and what that printed;
// its drift against the defaults (doctor: the kept check, or checked when the page opens), its open PRs as links to their
// pages, and its event log at the bottom. After a change, and while a release run is going, the page reads
// the repo again by itself (see useFollow).
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { qs } from '../api.js'
import { act, cached, forget, useFollow } from '../load.js'
import { useKeys } from '../keys.js'
import DoctorPanel from '../components/DoctorPanel.vue'
import ActionList from '../components/ActionList.vue'
import EventLog from '../components/EventLog.vue'
import StatusHeader from '../components/StatusHeader.vue'
import ReleaseForm from '../components/ReleaseForm.vue'
import SecretsPanel from '../components/SecretsPanel.vue'
import TextPane from '../components/TextPane.vue'
import VersionBar from '../components/VersionBar.vue'
import { stateClass } from '../ui.js'

const route = useRoute()
const router = useRouter()
const repo = computed(() => String(route.query.repo || ''))
const gitlab = computed(() => repo.value.startsWith('gitlab:'))
const detail = ref('')
const output = ref('')
const form = ref('') // '', 'release' or 'tag'
const suggest = ref('')
const publishes = ref('')
const version = ref(null)
const busy = ref(false) // a release run is going
const checked = ref(0) // bumped after c or f: the doctor panel shows the new result
const info = ref(null) // /repo's info: what the status header shows
const doctor = ref(null) // the doctor panel's last result
const sheet = ref(null)
const vbar = ref(null)

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

async function run(q, path, body) {
  const t = await act(q, path, body)
  if (t === null) return
  output.value = t
  forget('/status'); forget('/repo'); forget('/release')
  load(true)
  follow.now([repo.value])
  log.value?.burst()
  if (path === '/doctor') checked.value++
}
const r = () => [repo.value]
const fixFrom = (kind) => actions.value.find((a) => a.k === (kind === 'sync' ? 's' : 'f'))?.fn()
const actions = computed(() => [
  { k: 'c', group: 'defaults', label: 'check against the defaults', fn: () => run(`Check ${repo.value} against the defaults?`, '/doctor', { repos: r() }) },
  { k: 'f', group: 'defaults', label: 'fix the drift', fn: () => run(`Fix the drift of ${repo.value} (settings, security, rulesets)?`, '/doctor', { repos: r(), fix: true }) },
  { k: 's', group: 'defaults', label: 'open a PR with the shared files', fn: () => run(`Open a PR that syncs the shared files into ${repo.value}?`, '/sync', { repos: r() }) },
  { k: 'm', group: 'pull requests', off: !pulls.value.length, label: 'auto-merge the ready ones', fn: () => run(`Auto-merge the ready PRs of ${repo.value}?`, '/merge', { targets: r() }) },
  { k: 'M', group: 'pull requests', off: !pulls.value.length, label: 'merge the ready ones now', fn: () => run(`Merge the ready PRs of ${repo.value} now?`, '/merge', { targets: r(), now: true }) },
  { k: 'n', group: 'releases', primary: true, label: 'create a release', fn: () => newRelease('release') },
  { k: 'T', group: 'releases', label: 'push a tag (its workflow releases)', fn: () => newRelease('tag') },
  { k: 'l', group: 'releases', label: 'all its releases', fn: () => router.push({ path: '/release', query: { repo: repo.value } }) },
  { k: 'o', group: 'elsewhere', label: `open on ${gitlab.value ? 'GitLab' : 'GitHub'}`, fn: open },
])
async function loadReleases(fresh = false, quiet = false) {
  try {
    const p = await cached(`/release${qs({ repo: repo.value, fresh })}`, fresh, { quiet })
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
const open = () => { const url = info.value?.url || detail.value.split('\n')[1]; if (url?.startsWith('http')) window.open(url, '_blank', 'noopener') }
const back = () => (window.history.state?.back ? router.back() : router.push('/'))
const doctorPanel = ref(null)
const reload = () => { load(true); log.value?.refresh(); doctorPanel.value?.load(true) }
const keys = { '.': () => sheet.value?.pick(), Escape: () => (form.value ? (form.value = '') : back()), Backspace: back, r: () => reload() }
watch(actions, (list) => list.forEach((a) => { keys[a.k] = () => !a.off && a.fn() }), { immediate: true })
useKeys(keys)
// last: the immediate watch uses everything above
watch(repo, () => { detail.value = ''; output.value = ''; form.value = ''; version.value = null; suggest.value = ''; info.value = null; doctor.value = null; load(); loadReleases() }, { immediate: true })
</script>

<template>
  <div class="view">
    <div class="toolbar">
      <button class="hide-xs" @click="back"><span class="k">esc</span> back</button>
      <span class="dim hide-xs">repos ›</span>
      <span class="spacer" />
      <ActionList ref="sheet" class="show-compact" :actions="actions" :title="repo" compact />
      <button class="any" @click="reload"><span class="k">r</span> reload</button>
    </div>
    <StatusHeader :title="repo" :url="info?.url" :badges="badges" :next="next" />
    <div class="split page">
      <div class="pad">
        <div class="hide-xs"><h2>actions</h2><ActionList :actions="actions" /></div>
        <DoctorPanel ref="doctorPanel" :repo="repo" :stamp="checked" @result="(d) => (doctor = d)" @run="fixFrom" />
        <SecretsPanel v-if="!gitlab" :repo="repo" @done="({ text }) => (output = text)" />
        <template v-if="output"><h2 style="margin-top: 16px">output</h2><TextPane :text="output" /></template>
      </div>
      <div class="pad">
        <VersionBar v-if="version" ref="vbar" :repo="repo" :version="version" @done="done" />
        <ReleaseForm v-if="form" :key="form" :mode="form" :repo="repo" :suggest="suggest" :publishes="publishes"
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
        <TextPane v-if="rest || !info" :text="info ? rest : detail" placeholder="loading…" />
      </div>
    </div>
    <EventLog ref="log" band :repo="repo" kind="repo" :title="repo" />
  </div>
</template>
