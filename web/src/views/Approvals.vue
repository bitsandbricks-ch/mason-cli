<script setup>
// What waits for you: environments you review, outside contributors' runs, GitLab deployments and manual jobs.
// Enter opens the run (beside the list on a wide screen) like the other lists do; a approves.
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { act, useLoad } from '../load.js'
import { useKeys } from '../keys.js'
import { loadGroups, scope } from '../scope.js'
import { ago } from '../ui.js'
import DataTable from '../components/DataTable.vue'
import Scope from '../components/Scope.vue'
import TextPane from '../components/TextPane.vue'
import { openOut } from '../links.js'
import { encodeSide, pageRoute } from '../panel.js'
import { useTrack } from '../side.js'

const { data, error, loading, load } = useLoad((q) => `/approvals${q}`)
loadGroups()
const sel = ref(null)
const output = ref('')
const rows = computed(() => (data.value?.approvals || []).map((r) => ({ ...r, key: `${r.repo}|${r.kind}|${r.id}`, when: ago(r.created) })))
const columns = [
  { key: 'repo', label: 'repo', cls: (r) => (r.provider === 'gitlab' ? 'warn' : '') },
  { key: 'name', label: 'run', cls: () => '', card: 'main' },
  { key: 'waits_for', label: 'waits for', cls: (r) => (r.blocked ? 'dim' : 'warn') },
  { key: 'blocked', label: 'you can approve', fmt: (v) => (v ? `no: ${v}` : 'yes'), cls: (r) => (r.blocked ? 'bad' : 'ok') },
  { key: 'branch', label: 'branch', cls: () => '' },
  { key: 'when', label: 'since', cls: () => 'dim' },
]
const current = computed(() => rows.value.find((r) => r.key === sel.value))
// the selected one in full (the table cuts long reasons short); an approval's output until you move on
watch(sel, (_, before) => { if (rows.value.some((r) => r.key === before)) output.value = '' }) // an approved run that left the list keeps its output
const summary = computed(() => {
  const r = current.value
  if (!r) return ''
  const line = (k, v) => (v ? `  ${k.padEnd(16)}${v}\n` : '')
  return `${r.repo}\n${line('run', r.name)}${line('branch', r.branch)}${line('waits for', r.waits_for)}` +
    `${line('you can approve', r.blocked ? `no: ${r.blocked}` : 'yes')}${line('since', r.when)}${line('link', r.url)}` +
    `\n${r.blocked ? 'Enter opens the run' : 'a approves it; Enter opens the run'}`
})
async function approve(r = current.value) {
  if (!r) return
  if (r.blocked) { output.value = `you can't approve it: ${r.blocked}`; return }
  const text = await act(`Approve ${r.waits_for} for ${r.repo} ${r.branch || ''}?`, '/approve', { repo: r.repo, id: r.id, kind: r.kind })
  if (text !== null) { output.value = text; load(true) }
}
const open = (r) => openOut(r?.url)
// a GitLab deployment or manual job has no page of its own: its repo's
const targetOf = (r) => (!r.kind || r.kind === 'run' ? { kind: 'run', repo: r.repo, id: r.id } : { kind: 'repo', repo: r.repo })
const router = useRouter()
const page = (r) => { const x = r || current.value; if (x) router.push(pageRoute(targetOf(x))) }
useTrack(() => current.value && targetOf(current.value),
  { sel, kind: '*', key: (t) => rows.value.find((r) => encodeSide(targetOf(r)) === encodeSide(t))?.key ?? null })
useKeys({ r: () => load(true), a: () => approve(), o: () => open(current.value), p: () => page() })
</script>

<template>
  <div class="view">
    <div class="toolbar">
      <Scope :groups="scope.groups" />
      <span class="spacer" />
      <button class="primary" :disabled="!current || !!current.blocked" @click="approve()"><span class="k">a</span> approve</button>
      <button :disabled="!current" @click="open(current)"><span class="k">o</span> open</button>
      <button class="any" :disabled="!current" @click="page()"><span class="k">p</span> page</button>
    </div>
    <div class="split ld">
      <div><DataTable v-model="sel" :error="error" :columns="columns" :rows="rows" :empty="loading ? 'loading…' : '✓ no run waits for your approval'" @activate="page" /></div>
      <div class="pad"><TextPane :text="output || summary" placeholder="a approves the selected run; Enter opens it" /></div>
    </div>
  </div>
</template>
