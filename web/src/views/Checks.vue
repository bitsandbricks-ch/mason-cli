<script setup>
// Checks: the repos against the defaults (mason doctor), fixing drift, syncing files, plus plugin checks.
import { computed, onMounted, ref } from 'vue'
import { get, log, post } from '../api.js'
import { act, forget } from '../load.js'
import { useRouter } from 'vue-router'
import { useKeys } from '../keys.js'
import { loadGroups, ownerLabel, scope } from '../scope.js'
import DataTable from '../components/DataTable.vue'
import GroupSelect from '../components/GroupSelect.vue'
import TextPane from '../components/TextPane.vue'

const output = ref('')
const found = ref([]) // doctor's result per repo: the table on top, the full output below it
const sel = ref(null)
const router = useRouter()
const columns = [
  { key: 'repo', label: 'repo' },
  { key: 'result', label: 'result', fmt: (_, r) => (r.error ? 'error' : r.ok ? 'ok' : `${r.problems.length} issue${r.problems.length === 1 ? '' : 's'}`),
    cls: (r) => (r.error ? 'bad' : r.ok ? 'ok' : 'warn') },
  { key: 'first', label: 'first issue', card: 'main', fmt: (_, r) => r.error || r.problems[0] || r.where || '', cls: () => '' },
]
const rows = computed(() => found.value.slice().sort((a, b) => (a.ok - b.ok) || (b.problems.length - a.problems.length) || a.repo.localeCompare(b.repo)))
const page = (r) => router.push({ path: '/repo', query: { repo: r.repo } })
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
const where = computed(() => (repos.value.length ? repos.value.join(', ') : scope.group.endsWith('/') ? ownerLabel(scope.group) : scope.group ? `group ${scope.group}` : 'every repo'))

async function doctor() {
  running.value = 'doctor'
  output.value = ''
  found.value = []
  try {
    const got = await post('/doctor', { repos: repos.value, group: scope.group || undefined })
    output.value = got.text || 'ok'
    found.value = got.repos || []
    forget('/status') // the repo list's doctor column
  } catch (e) { output.value = `error: ${e.message}`; log(e.message, 'error') }
  running.value = ''
}
async function fix() {
  const t = await act(`Apply the defaults to ${where.value} (settings, security, rulesets, protected branches)?`, '/doctor', { repos: repos.value, group: scope.group || undefined, fix: true })
  if (t !== null) { output.value = t; found.value = [] }
}
async function sync() {
  const t = await act(`Open PRs that sync the shared files into ${where.value}?`, '/sync', { repos: repos.value, group: scope.group || undefined })
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
      <GroupSelect :groups="scope.groups" />
      <input v-model="only" placeholder="repos (empty: all), e.g. web api gitlab:grp/x" style="min-width: 28ch">
      <button class="primary" :disabled="!!running" @click="doctor"><span class="k">c</span> check every repo</button>
      <button :disabled="!!running" @click="fix"><span class="k">f</span> fix the drift</button>
      <button :disabled="!!running" @click="sync"><span class="k">s</span> open PRs with the shared files</button>
      <span class="spacer" />
      <button v-for="c in pluginChecks" :key="c.plugin + c.key" :disabled="!!running" @click="plugin(c)">{{ c.label }} <span class="dim">[{{ c.plugin }}]</span></button>
    </div>
    <div class="scroll pad">
      <div v-if="running" class="warn cursor">running {{ running }} </div>
      <DataTable v-if="found.length" v-model="sel" :columns="columns" :rows="rows" :row-key="(r) => r.repo" style="margin-bottom: 16px" @activate="page" />
      <TextPane :text="output" placeholder="c checks the repos against the defaults: settings, security, release immutability, rulesets (GitHub), protected branches (GitLab) and files. f fixes what it can, s opens PRs with the files." />
    </div>
  </div>
</template>
