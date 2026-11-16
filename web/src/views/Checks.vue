<script setup>
// Checks: the repos against the defaults (mason doctor), fixing drift, syncing files, plus plugin checks.
import { computed, onMounted, ref, watch } from 'vue'
import { get, log, post } from '../api.js'
import { act, forget } from '../load.js'
import { useRouter } from 'vue-router'
import { useKeys } from '../keys.js'
import { loadGroups, scope, scopeLabel, scoped, scopedRepos } from '../scope.js'
import DataTable from '../components/DataTable.vue'
import Scope from '../components/Scope.vue'
import TextPane from '../components/TextPane.vue'
import { useTrack } from '../side.js'
import { ago } from '../ui.js'

const output = ref('')
const found = ref([]) // doctor's result per repo: the table on top, the full output below it
const sel = ref(null)
const router = useRouter()
const columns = [
  { key: 'repo', label: 'repo' },
  { key: 'result', label: 'result', fmt: (_, r) => (r.error ? 'error' : r.ok ? 'ok' : `${r.problems.length} issue${r.problems.length === 1 ? '' : 's'}`),
    cls: (r) => (r.error ? 'bad' : r.ok ? 'ok' : 'warn') },
  { key: 'first', label: 'first issue', card: 'main', fmt: (_, r) => r.error || r.problems[0] || r.where || '', cls: () => '' },
  { key: 'checked', label: 'checked', fmt: (v) => (v ? ago(new Date(v * 1000).toISOString()) : 'now'), cls: () => 'dim' },
]
const rows = computed(() => found.value.slice().sort((a, b) => (a.ok - b.ok) || (b.problems.length - a.problems.length) || a.repo.localeCompare(b.repo)))
const page = (r) => router.push({ path: '/repo', query: { repo: r.repo } })
useTrack(() => sel.value && { kind: 'repo', repo: sel.value }, { sel, kind: 'repo', key: (t) => (t.kind === 'repo' && rows.value.some((r) => r.repo === t.repo) ? t.repo : null) })
const running = ref('')
const only = ref('')
const pluginChecks = ref([])
loadGroups()
onMounted(async () => {
  try {
    pluginChecks.value = (await get('/plugins')).plugins.filter((p) => p.on).flatMap((p) => p.checks.map((c) => ({ ...c, plugin: p.name })))
  } catch { /* none */ }
})
const repos = computed(() => only.value.split(/[\s,]+/).filter(Boolean))
const where = computed(() => (repos.value.length ? repos.value.join(', ') : scopeLabel()))
// The last check of each repo in the filter, kept by the server (it checks nothing): the page opens with
// what is known instead of empty. Results of another scope would read as this one's, so a new filter reads again.
const fromKept = ref(false)
const unchecked = ref(0) // repos in the filter that were never checked
async function kept() {
  const asked = `${scope.provider}|${scope.group}`
  try {
    const [all, names] = await Promise.all([get('/doctor', { quiet: true }), scopedRepos()])
    if (asked !== `${scope.provider}|${scope.group}` || running.value) return
    found.value = names.map((n) => all.repos?.[n]).filter(Boolean)
    unchecked.value = names.length - found.value.length
    fromKept.value = found.value.length > 0
  } catch { /* the button still checks */ }
}
onMounted(kept)
watch(() => [scope.provider, scope.group], () => { found.value = []; output.value = ''; kept() })

async function doctor() {
  running.value = 'doctor'
  output.value = ''
  found.value = []
  try {
    const got = await post('/doctor', { repos: repos.value, ...scoped() })
    output.value = got.text || 'ok'
    found.value = got.repos || []
    fromKept.value = false
    forget('/status') // the repo list's doctor column
  } catch (e) { output.value = `error: ${e.message}`; log(e.message, 'error') }
  running.value = ''
}
async function fix() {
  const t = await act(`Apply the defaults to ${where.value} (settings, security, rulesets, protected branches)?`, '/doctor', { repos: repos.value, ...scoped(), fix: true })
  if (t !== null) { output.value = t; found.value = [] }
}
async function sync() {
  const t = await act(`Open PRs that sync the shared files into ${where.value}?`, '/sync', { repos: repos.value, ...scoped() })
  if (t !== null) output.value = t
}
async function plugin(c) {
  running.value = c.key
  try { output.value = (await post(`/plugins/${c.plugin}/checks/${c.key}`)).text } catch (e) { output.value = `error: ${e.message}` }
  running.value = ''
}
useKeys({ c: doctor, f: fix, s: sync })
</script>

<template>
  <div class="view">
    <div class="toolbar">
      <Scope :groups="scope.groups" />
      <input v-model="only" placeholder="repos (empty: all), e.g. web api gitlab:grp/x" style="min-width: 28ch">
      <button class="primary" :disabled="!!running" @click="doctor"><span class="k">c</span> check {{ where }}</button>
      <button :disabled="!!running" @click="fix"><span class="k">f</span> fix the drift</button>
      <button :disabled="!!running" @click="sync"><span class="k">s</span> open PRs with the shared files</button>
      <span class="spacer" />
      <button v-for="c in pluginChecks" :key="c.plugin + c.key" :disabled="!!running" @click="plugin(c)">{{ c.label }} <span class="dim">[{{ c.plugin }}]</span></button>
    </div>
    <div class="scroll pad">
      <div v-if="running" class="warn cursor">running {{ running }} </div>
      <p v-if="fromKept && !running" class="dim">the last check of each repo{{ unchecked ? `, ${unchecked} not checked yet` : '' }};
        <span class="accent">c</span> checks them{{ unchecked ? '' : ' again' }}</p>
      <DataTable v-if="found.length" v-model="sel" :columns="columns" :rows="rows" :row-key="(r) => r.repo" style="margin-bottom: 16px" @activate="page" />
      <TextPane :text="output" placeholder="c checks the repos against the defaults: settings, security, release immutability, rulesets (GitHub), protected branches (GitLab) and files. f fixes what it can, s opens PRs with the files." />
    </div>
  </div>
</template>
