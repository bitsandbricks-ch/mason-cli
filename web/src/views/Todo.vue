<script setup>
// To do: everything across your repos that waits for you, most urgent first: runs to approve and PRs that ask
// you for a review, what is broken (CI on the default branch, conflicts, failing checks, a failed release run),
// PRs ready to merge, drift against the defaults, versions not released yet and open issues assigned to you.
// Enter opens one (in the side panel on a wide screen, where ↑↓ then walk through the list).
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { cached, useLoad } from '../load.js'
import { state } from '../api.js'
import { useKeys } from '../keys.js'
import { loadGroups, scope } from '../scope.js'
import { pageRoute, encodeSide } from '../panel.js'
import { useTrack } from '../side.js'
import { RANKS, sinceLastLook, todoItems } from '../todo.js'
import DataTable from '../components/DataTable.vue'
import Scope from '../components/Scope.vue'

const missing = ref([]) // lists that couldn't load: the to do may lack their items
const repoCount = ref(null) // no repos at all (and no filter): the first visit, so say how to start
const { data, error, loading, load } = useLoad(async (q, fresh) => {
  const names = ['status', 'prs', 'approvals', 'releases', 'issues']
  const extra = { issues: 'mine=1&state=open' } // your open issues only
  const url = (n) => `/${n}${q}${extra[n] ? `${q ? '&' : '?'}${extra[n]}` : ''}`
  const got = await Promise.allSettled(names.map((n) => cached(url(n), fresh, { quiet: true })))
  missing.value = names.filter((_, i) => got[i].status === 'rejected')
  if (missing.value.length === names.length) throw got[0].reason
  const [status, prs, approvals, releases, issues] = got.map((g) => (g.status === 'fulfilled' ? g.value : null))
  repoCount.value = status ? (status.rows || []).length : null
  return todoItems({ status, prs: prs?.prs, approvals: approvals?.approvals, releases: releases?.releases, issues: issues?.issues,
    me: (state.me?.identities || []).filter((i) => i.provider === 'github').map((i) => i.login) })
})
loadGroups()
const sel = ref(null)
const keyOf = (i) => `${encodeSide(i.target)}|${i.why}`
// what appeared since your last look at the to do (in this browser) is marked "new"
const SEEN = 'mason.todo.seen'
const fresh = ref([])
watch(data, (items) => {
  if (!items) return
  let seen = null
  try { seen = JSON.parse(localStorage.getItem(SEEN) || 'null') } catch { /* private mode */ }
  const got = sinceLastLook(items.map(keyOf), seen, { before: fresh.value })
  fresh.value = got.fresh
  try { localStorage.setItem(SEEN, JSON.stringify(got.seen)) } catch { /* private mode */ }
})
const rows = computed(() => (data.value || []).map((i) => {
  const key = keyOf(i)
  return { ...i, key, group: fresh.value.includes(key) ? `${RANKS[i.rank]} · new` : RANKS[i.rank] }
}))
const columns = [
  { key: 'group', label: 'what', cls: (r) => r.cls, mark: false, card: 'head' },
  { key: 'repo', label: 'repo', cls: () => '' },
  { key: 'what', label: 'about', cls: () => '', card: 'main' },
  { key: 'why', label: 'why', cls: (r) => r.cls },
]
const current = computed(() => rows.value.find((r) => r.key === sel.value))
const router = useRouter()
const page = (r) => { const x = r || current.value; if (x) router.push(pageRoute(x.target)) }
// any kind: the list mixes runs, repos, PRs and releases, and the panel shows whichever row you are on
useTrack(() => current.value?.target, { sel, kind: '*', key: (t) => rows.value.find((r) => encodeSide(r.target) === encodeSide(t))?.key ?? null })
const counts = computed(() => Object.entries(RANKS).map(([k, label]) => ({ label, n: rows.value.filter((r) => r.rank === Number(k)).length })))
useKeys({ r: () => load(true), p: () => page() })
</script>

<template>
  <div class="view">
    <div class="toolbar">
      <Scope :groups="scope.groups" />
      <button class="hide-xs" @click="load(true)"><span class="k">r</span> reload</button>
      <span class="row todo-counts">
        <span v-for="c in counts" :key="c.label" :class="c.n ? '' : 'dim'"><b>{{ c.n }}</b> {{ c.label }}</span>
        <span v-if="fresh.length" class="accent"><b>{{ fresh.length }}</b> new since your last look</span>
      </span>
      <span class="spacer" />
      <button class="primary hide-xs" :disabled="!current" @click="page()"><span class="k">⏎</span> open</button>
    </div>
    <div v-if="missing.length" class="pad warn">couldn't read {{ missing.join(', ') }}: their items may be missing (r tries again)</div>
    <div v-if="repoCount === 0 && !scope.group && scope.provider === 'all' && !loading" class="pad">
      <div class="box" style="max-width: 72ch">
        <div class="accent">nothing to look after yet</div>
        <ol>
          <li>Under <router-link to="/settings">setup › settings</router-link>, name your GitHub orgs (or single repos) and GitLab groups.</li>
          <li>Optionally a defaults repo with <span class="accent">mason.toml</span>, so checks can tell drift.</li>
          <li>Come back here: what waits for you shows up, most urgent first.</li>
        </ol>
      </div>
    </div>
    <div v-else class="scroll">
      <DataTable v-model="sel" :error="error" :columns="columns" :rows="rows" :row-key="(r) => r.key"
                 :empty="loading ? 'loading…' : '✓ nothing waits for you: no approvals, nothing broken, no drift'" @activate="page" />
    </div>
  </div>
</template>
