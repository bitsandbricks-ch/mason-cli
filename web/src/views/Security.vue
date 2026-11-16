<script setup>
// Open alerts: Dependabot, secret scanning and code scanning on GitHub, vulnerabilities on GitLab.
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useTrack } from '../side.js'
import { useLoad } from '../load.js'
import { useKeys } from '../keys.js'
import { loadGroups, scope } from '../scope.js'
import DataTable from '../components/DataTable.vue'
import Scope from '../components/Scope.vue'
import { openOut } from '../links.js'

const { data, error, loading, load } = useLoad((q) => `/security${q}`)
loadGroups()
const sel = ref(null)
const rows = computed(() => (data.value?.security || []).flatMap((s) => s.alerts.map((a, i) => ({ ...a, repo: s.repo, provider: s.provider, key: `${s.repo}|${i}` }))))
const unread = computed(() => (data.value?.security || []).filter((s) => s.unread.length))
const counts = computed(() => rows.value.reduce((m, a) => ({ ...m, [a.severity]: (m[a.severity] || 0) + 1 }), {}))
const columns = [
  { key: 'severity', label: 'severity' }, { key: 'repo', label: 'repo', cls: (r) => (r.provider === 'gitlab' ? 'warn' : ''), card: 'head' },
  { key: 'kind', label: 'kind', cls: () => 'dim' }, { key: 'title', label: 'alert', cls: () => '', card: 'main' }, { key: 'where', label: 'where', cls: () => 'dim' },
]
const current = computed(() => rows.value.find((r) => r.key === sel.value))
const open = (r) => openOut(r?.url)
const router = useRouter()
const repoPage = () => current.value && router.push({ path: '/repo', query: { repo: current.value.repo } })
// an open repo panel follows the selected row
useTrack(() => current.value?.repo && { kind: 'repo', repo: current.value.repo }, { kind: '*' })
useKeys({ r: () => load(true), o: () => open(current.value), p: repoPage })
</script>

<template>
  <div class="view">
    <div class="toolbar">
      <Scope :groups="scope.groups" />
      <span v-for="(n, s) in counts" :key="s" class="chip">{{ s }} {{ n }}</span>
      <span class="spacer" />
      <button :disabled="!current?.url" @click="open(current)"><span class="k">o</span> open the alert</button>
      <button class="any" :disabled="!current" @click="repoPage"><span class="k">p</span> repo page</button>
    </div>
    <div class="scroll">
      <DataTable v-model="sel" :error="error" :columns="columns" :rows="rows" :empty="loading ? 'loading…' : '✓ no open security alerts'" outside @activate="open" />
      <div v-if="unread.length" class="pad dim">
        <div v-for="s in unread" :key="s.repo">couldn't read {{ s.repo }}: {{ s.unread.join('; ') }}</div>
      </div>
    </div>
  </div>
</template>
