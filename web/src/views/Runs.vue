<script setup>
// Workflow runs and pipelines: the newest per repo, or only the failed ones. Enter opens a run's page.
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { change, forget, useLoad } from '../load.js'
import { useKeys } from '../keys.js'
import { emptyText } from '../empty.js'
import { useLinkFilters } from '../useLink.js'
import { loadGroups, narrowed, scope } from '../scope.js'
import { ago } from '../ui.js'
import EventLog from '../components/EventLog.vue'
import DataTable from '../components/DataTable.vue'
import Scope from '../components/Scope.vue'
import { useTrack } from '../side.js'
import { openOut } from '../links.js'

const LIMITS = [1, 3, 5, 10, 20]
// in the link (?failed=1&limit=10), so a bookmark or a saved view opens the same list
const f = reactive({ failed: false, limit: 3 })
useLinkFilters(f, { failed: { def: false }, limit: { def: 3, ok: (v) => LIMITS.includes(v) } })
const { data, error, loading, load } = useLoad((q) => `/runs${q}${q ? '&' : '?'}limit=${f.limit}${f.failed ? '&failed=1' : ''}`)
watch(() => [f.failed, f.limit], () => load())
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
const open = (r) => openOut(r?.url)
const current = computed(() => rows.value.find((r) => r.key === sel.value))
const router = useRouter()
useTrack(() => current.value?.id && { kind: 'run', repo: current.value.repo, id: current.value.id },
  { sel, kind: 'run', key: (t) => (t.kind === 'run' ? `${t.repo}|${t.id}` : null) })
const page = (r) => { const x = r || current.value; if (x?.id) router.push({ path: '/run', query: { repo: x.repo, id: x.id } }) }
// R: run the failed jobs of the selected run again, without opening it (the run page has the same)
const FAILED = /^(failure|failed|timed_out|cancelled|canceled|startup_failure)$/
const canRerun = computed(() => !!current.value?.id && FAILED.test(String(current.value.state || '')))
async function rerun() {
  const r = current.value
  if (!canRerun.value) return
  const got = await change(`Run the failed jobs of ${r.name || 'run'} ${r.id} in ${r.repo} again?`, '/run/rerun', { repo: r.repo, id: r.id })
  if (got?.ok && !got.dry) { forget('/runs'); setTimeout(() => load(true), 2000) }
}
const toggle = () => { f.failed = !f.failed }
useKeys({ r: () => load(true), R: rerun, f: toggle, o: () => open(current.value), p: () => page() })
</script>

<template>
  <div class="view">
    <div class="toolbar">
      <Scope :groups="scope.groups" />
      <label class="check"><input :checked="f.failed" type="checkbox" @change="toggle"> only failed <span class="dim k">(f)</span></label>
      <label class="row">per repo <select v-model.number="f.limit"><option v-for="n in LIMITS" :key="n">{{ n }}</option></select></label>
      <span class="spacer" />
      <button :disabled="!canRerun" @click="rerun"><span class="k">R</span> run failed jobs again</button>
      <button :disabled="!current" @click="open(current)"><span class="k">o</span> open</button>
      <button :disabled="!current?.id" @click="page()"><span class="k">p</span> page</button>
    </div>
    <div class="scroll"><DataTable v-model="sel" :error="error" :columns="columns" :rows="rows" :empty="loading ? 'loading…' : emptyText('no workflow runs yet: repos with GitHub Actions or GitLab CI show theirs here', [f.failed && 'only failed'], narrowed())" @activate="page" /></div>
    <EventLog band :repo="current?.id ? current.repo : ''" kind="run" :number="current?.id || ''" :title="current?.id ? `${current.repo} ${current.name}` : ''" />
  </div>
</template>
