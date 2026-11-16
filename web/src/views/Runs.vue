<script setup>
// Workflow runs and pipelines: the newest per repo, or only the failed ones. Enter opens a run's page.
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { forget, useLoad } from '../load.js'
import { log, post, state } from '../api.js'
import { BULK_MAX, bulkQuestion, rerunnable } from '../bulk.js'
import { useKeys } from '../keys.js'
import { loadGroups, scope } from '../scope.js'
import { ago, ask } from '../ui.js'
import EventLog from '../components/EventLog.vue'
import DataTable from '../components/DataTable.vue'
import Scope from '../components/Scope.vue'

const failed = ref(false)
const limit = ref(3)
const { data, error, loading, load } = useLoad((q) => `/runs${q}${q ? '&' : '?'}limit=${limit.value}${failed.value ? '&failed=1' : ''}`)
loadGroups()
const sel = ref(null)
const rows = computed(() => (data.value?.runs || []).map((r) => ({ ...r, key: `${r.repo}|${r.id ?? r.error}`, when: ago(r.created) })))
const columns = [
  { key: 'repo', label: 'repo', cls: (r) => (r.provider === 'gitlab' ? 'warn' : '') },
  { key: 'state', label: 'state', fmt: (v, r) => r.error || v, card: 'head' },
  { key: 'name', label: 'workflow', cls: () => '', card: 'main' },
  { key: 'event', label: 'event', cls: () => 'dim' },
  { key: 'branch', label: 'branch', cls: () => '' },
  { key: 'when', label: 'when', cls: () => 'dim' },
]
const open = (r) => r?.url && window.open(r.url, '_blank', 'noopener')
const current = computed(() => rows.value.find((r) => r.key === sel.value))
const router = useRouter()
const page = (r) => { const x = r || current.value; if (x?.id) router.push({ path: '/run', query: { repo: x.repo, id: x.id } }) }
const toggle = () => { failed.value = !failed.value; load() }
// R: every failed run in the list (the newest of each workflow) runs its failed jobs again, after one question
const failedRuns = computed(() => rerunnable(rows.value))
async function rerunAll() {
  const list = failedRuns.value.slice(0, BULK_MAX)
  if (!list.length) return
  const { question, detail } = bulkQuestion('Run the failed jobs again', 'run', list, (x) => `${x.repo}  ${x.name}  (${x.branch || x.event || x.id})`)
  const a = await ask(question, { detail: detail + (state.dryRun ? '\n\ndry run is on: nothing changes' : '') })
  if (!a) return
  const dry = a === 'dry'
  const out = []
  let bad = 0
  for (const x of list) { // one after the other: GitHub's secondary rate limit dislikes bursts of writes
    try { out.push((await post('/run/rerun', { repo: x.repo, id: x.id, dry_run: dry })).text || `${x.repo}: ${x.id}`) }
    catch (e) { bad++; out.push(`error: ${x.repo} run ${x.id}: ${e.message}`) }
  }
  log(`${dry ? '[dry-run] ' : ''}ran the failed jobs again in ${list.length - bad} of ${list.length} runs`, bad ? 'error' : 'ok', { detail: out.join('\n') })
  if (!dry) { forget('/runs'); setTimeout(() => load(true), 2000) }
}
useKeys({ R: rerunAll, r: () => load(true), f: toggle, o: () => open(current.value), p: () => page() })
</script>

<template>
  <div class="view">
    <div class="toolbar">
      <Scope :groups="scope.groups" />
      <label class="check"><input :checked="failed" type="checkbox" @change="toggle"> only failed <span class="dim k">(f)</span></label>
      <label class="row">per repo <select v-model.number="limit" @change="load()"><option v-for="n in [1, 3, 5, 10, 20]" :key="n">{{ n }}</option></select></label>
      <button class="any" :disabled="!failedRuns.length" title="run the failed jobs of every failed run in the list again, after one question"
              @click="rerunAll"><span class="k">R</span> rerun failed<template v-if="failedRuns.length"> ({{ failedRuns.length }})</template></button>
      <span class="spacer" />
      <button :disabled="!current" @click="open(current)"><span class="k">o</span> open</button>
      <button :disabled="!current?.id" @click="page()"><span class="k">p</span> page</button>
    </div>
    <div class="scroll"><DataTable v-model="sel" :error="error" :columns="columns" :rows="rows" :empty="loading ? 'loading…' : 'no workflow runs yet: repos with GitHub Actions or GitLab CI show theirs here'" @activate="page" /></div>
    <EventLog band :repo="current?.id ? current.repo : ''" kind="run" :number="current?.id || ''" :title="current?.id ? `${current.repo} ${current.name}` : ''" />
  </div>
</template>
