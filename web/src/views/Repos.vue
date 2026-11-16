<script setup>
// Repos: the status table (mason status) and, on the right, a short summary of the selected repo: its state,
// open PRs and drift. Enter (or "repo page") opens the repo as its own page, where everything else is; the
// actions on the selected repo sit behind one "actions" button (and their keys).
import { computed, ref, watch } from 'vue'
import { qs } from '../api.js'
import { act, cached, useLoad } from '../load.js'
import { useRouter } from 'vue-router'
import { useKeys } from '../keys.js'
import { loadGroups, reloadGroups, scope } from '../scope.js'
import FirstRun from '../components/FirstRun.vue'
import EventLog from '../components/EventLog.vue'
import DataTable from '../components/DataTable.vue'
import Scope from '../components/Scope.vue'
import DoctorPanel from '../components/DoctorPanel.vue'
import TextPane from '../components/TextPane.vue'
import ActionList from '../components/ActionList.vue'
import StatusHeader from '../components/StatusHeader.vue'
import { ask, choose, stateClass } from '../ui.js'
import { alive } from '../pick.js'
import { useTrack } from '../side.js'
import { openOut } from '../links.js'

const emit = defineEmits(['rate'])
const { data, error, loading, load } = useLoad((q) => `/status${q}`)
loadGroups()
const sel = ref(null)
const detail = ref('')
const output = ref('')

const head = computed(() => data.value?.head || [])
const rows = computed(() => (data.value?.rows || []).map((r) => {
  const o = { repo: r.repo, provider: r.provider }
  head.value.forEach((h, i) => { o[h] = r.cells[i] })
  return o
}))
// the cells in words: "2 ready · 1 draft" instead of 2/1, "never" instead of -
function prsCell(v) {
  const m = String(v || '').match(/^(\d+)\/(\d+)$/)
  if (!m) return v || ''
  const [ready, drafts] = [Number(m[1]), Number(m[2])]
  if (!ready && !drafts) return '–'
  return [ready && `${ready} ready`, drafts && `${drafts} draft`].filter(Boolean).join(' · ')
}
const COLUMN = {
  'PRs ready/draft': { label: 'pull requests', fmt: prsCell, cls: (r) => (/ready/.test(prsCell(r['PRs ready/draft'])) ? 'ok' : 'dim'), mark: false },
  released: { fmt: (v) => (!v || v === '-' ? 'never' : v), cls: (r) => (!r.released || r.released === '-' ? 'dim' : '') },
  CI: { fmt: (v) => (!v || v === '-' ? 'no runs' : v) },
}
const columns = computed(() => [
  { key: 'repo', label: 'repo', cls: (r) => (r.provider === 'gitlab' ? 'warn' : '') },
  ...head.value.map((h) => ({ key: h, label: h.toLowerCase(), ...(COLUMN[h] || {}) })),
  { key: 'doctor', label: 'defaults', fmt: (_, r) => doctorCell(r.repo), cls: (r) => doctorClass(r.repo) },
])
const row = computed(() => rows.value.find((r) => r.repo === sel.value))
// nothing to list, with no filter on: the first visit, so show how to get started instead of an empty table
const firstRun = computed(() => !!data.value && !loading.value && !error.value && !rows.value.length && !scope.group && scope.provider === 'all')
const started = () => { load(true); reloadGroups() }
const info = ref(null)
const badges = computed(() => {
  const r = row.value
  if (!r) return []
  const out = [{ label: 'CI', value: COLUMN.CI.fmt(r.CI) }, { label: 'released', value: COLUMN.released.fmt(r.released), cls: '' },
    { label: 'PRs', value: prsCell(r['PRs ready/draft']), cls: '' }]
  out.push({ label: 'defaults', value: doctorCell(r.repo), cls: doctorClass(r.repo) === 'dim' ? '' : doctorClass(r.repo) })
  return out
})
// the last doctor check of each repo (Checks, a repo page, c): ok, how many issues, or - when not checked yet
const checks = computed(() => data.value?.doctor || {})
function doctorCell(repo) {
  const d = checks.value[repo]
  if (!d) return 'not checked'
  if (d.error) return 'check failed'
  return d.ok ? 'ok' : `${d.issues} issue${d.issues === 1 ? '' : 's'}`
}
function doctorClass(repo) {
  const d = checks.value[repo]
  return !d ? 'dim' : d.error ? 'bad' : d.ok ? 'ok' : 'warn'
}

watch(sel, async (repo) => {
  output.value = ''
  info.value = null
  if (!repo) return
  detail.value = '…'
  try {
    const got = await cached(`/repo${qs({ repo })}`)
    if (repo !== sel.value) return
    detail.value = got.text
    info.value = got.info || null
  } catch (e) { detail.value = `error: ${e.message}` }
})
watch(() => data.value, () => emit('rate'))

const run = async (q, path, body, opts) => { const t = await act(q, path, body, opts); if (t !== null) { output.value = t; load(true) } }
// what c f s m M act on: the picked repos when there are any (space or the boxes), else the selected one
const picked = ref([])
watch(rows, (list) => { picked.value = alive(picked.value, list.map((r) => r.repo)) })
const them = () => (picked.value.length ? picked.value.slice() : sel.value ? [sel.value] : [])
const named = (list) => (list.length === 1 ? list[0] : `${list.length} repos`)
const many = (list) => (list.length > 1 ? { detail: list.join('\n') } : {})
const runOn = (q, path, body) => { const list = them(); if (list.length) run(q(named(list)), path, body(list), many(list)) }
const doctor = () => runOn((n) => `Check ${n} against the defaults?`, '/doctor', (repos) => ({ repos }))
const fix = () => runOn((n) => `Fix the drift of ${n} (settings, security, rulesets)?`, '/doctor', (repos) => ({ repos, fix: true }))
const sync = () => runOn((n) => `Open a PR that syncs the shared files into ${n}?`, '/sync', (repos) => ({ repos }))
const merge = (now) => runOn((n) => `${now ? 'Merge now' : 'Auto-merge'} the ready PRs of ${n}?`, '/merge', (targets) => ({ targets, now }))
const router = useRouter()
useTrack(() => sel.value && { kind: 'repo', repo: sel.value }, { sel, kind: 'repo', key: (t) => (t.kind === 'repo' ? t.repo : null) })
const page = (r) => router.push({ path: '/repo', query: { repo: r?.repo || sel.value } })
const open = () => { const url = info.value?.url || detail.value.split('\n')[1]; openOut(url) }
async function newRepo() {
  const name = await ask('New repo (owner/name, or gitlab:group/name)', { input: { placeholder: 'acme/new-service' }, allowDry: false })
  if (!name) return
  // a choice, not y/n: "n" meant private, and Esc made a private repo instead of stopping
  const vis = await choose(`Who may see ${name}?`, [{ key: 'p', value: 'private', label: 'private', hint: 'only those you add' },
    { key: 'P', value: 'public', label: 'public', hint: 'everyone' }])
  if (!vis) return
  await run(`Create ${name} (${vis}) the way its group wants it?`, '/new', { repo: name, public: vis === 'public' })
}
const sheet = ref(null)
const releases = () => sel.value && router.push({ path: '/release', query: { repo: sel.value } })
const actions = computed(() => [
  { k: 'c', group: 'defaults', label: 'check against the defaults', fn: doctor },
  { k: 'f', group: 'defaults', label: 'fix the drift', fn: fix },
  { k: 's', group: 'defaults', label: 'open a PR with the shared files', fn: sync },
  { k: 'm', group: 'pull requests', label: 'auto-merge the ready ones', fn: () => merge(false) },
  { k: 'M', group: 'pull requests', label: 'merge the ready ones now', fn: () => merge(true) },
  { k: 'l', group: 'releases', label: 'its releases', fn: releases },
  { k: 'o', group: 'elsewhere', label: `open on ${row.value?.provider === 'gitlab' ? 'GitLab' : 'GitHub'}`, fn: open },
])
const fixFrom = (kind) => (kind === 'sync' ? sync() : fix())
useKeys({ '.': () => sheet.value?.pick(), l: () => sel.value && router.push({ path: '/release', query: { repo: sel.value } }), r: () => load(true), c: doctor, f: fix, s: sync, m: () => merge(false), M: () => merge(true), o: open, n: newRepo })
</script>

<template>
  <div class="view">
    <div class="toolbar">
      <Scope :groups="scope.groups" />
      <button class="hide-xs" @click="load(true)"><span class="k">r</span> reload</button>
      <button class="any" @click="newRepo"><span class="k">n</span> new repo</button>
      <span class="spacer" />
      <ActionList ref="sheet" :actions="actions" :title="sel || 'actions'" :disabled="!sel" compact />
      <button class="primary" :disabled="!sel" @click="page()"><span class="k">⏎</span> repo page</button>
    </div>
    <div v-if="picked.length" class="picked-bar" role="status">
      <span><b>{{ picked.length }}</b> picked</span>
      <button @click="doctor"><span class="k">c</span> check them</button>
      <button @click="fix"><span class="k">f</span> fix their drift</button>
      <button @click="sync"><span class="k">s</span> sync their files</button>
      <button @click="merge(false)"><span class="k">m</span> auto-merge their ready PRs</button>
      <button @click="picked = []">clear</button>
    </div>
    <div class="split ld" :class="{ first: firstRun }">
      <FirstRun v-if="firstRun" @saved="started" />
      <div v-else>
        <DataTable v-model="sel" v-model:picked="picked" :error="error" :columns="columns" :rows="rows" :row-key="(r) => r.repo"
                   :empty="loading ? 'loading…' : 'no repos yet: add your orgs or a defaults repo under setup › settings'" @activate="page" />
      </div>
      <div class="preview">
        <StatusHeader v-if="row" :title="sel" :url="info?.url" :badges="badges" />
        <div class="pad">
          <div v-if="!sel" class="empty">pick a repo</div>
          <TextPane v-else-if="!info" :text="detail" />
          <template v-else>
            <h2>{{ row?.provider === 'gitlab' ? 'merge requests' : 'pull requests' }} <span class="dim">({{ info.prs.length }})</span></h2>
            <ul v-if="info.prs.length" class="pull-list">
              <li v-for="p in info.prs" :key="p.number">
                <router-link :to="{ path: '/pr', query: { repo: sel, number: p.number } }">
                  <span class="dim">{{ row?.provider === 'gitlab' ? '!' : '#' }}{{ p.number }}</span> {{ p.title }}</router-link>
                <span v-if="p.draft" class="dim">draft</span>
                <span v-else-if="p.merge" :class="stateClass(p.merge)">{{ p.merge }}</span>
              </li>
            </ul>
            <div v-else class="dim" style="margin-bottom: 8px">none open</div>
          </template>
          <DoctorPanel v-if="sel && checks[sel]" :key="sel" :repo="sel" :stamp="checks[sel].checked" @run="fixFrom" />
          <template v-if="output"><h2 style="margin-top: 16px">output</h2><TextPane :text="output" /></template>
          <button v-if="sel" class="primary wide hide-xs" style="margin-top: 14px" @click="page()">open the repo page: releases, secrets, events ›</button>
        </div>
      </div>
    </div>
    <EventLog band :repo="sel || ''" kind="repo" :title="sel || ''" />
  </div>
</template>
