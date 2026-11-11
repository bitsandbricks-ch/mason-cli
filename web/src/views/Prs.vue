<script setup>
// Pull and merge requests: all open ones, with checks, review, conflicts and auto-merge.
// A change shows at once: the row changes right away, and its repo is read again (only that one) a moment later
// and then while a PR of it waits for auto-merge, so a PR that merges by itself leaves the list without r.
// Enter (or p) opens one as its own page, with its event log.
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { get, qs } from '../api.js'
import { act, change, splice, useFollow, useLoad } from '../load.js'
import { useKeys } from '../keys.js'
import { loadGroups, scope } from '../scope.js'
import DataTable from '../components/DataTable.vue'
import Scope from '../components/Scope.vue'
import TextPane from '../components/TextPane.vue'

const { data, loading, load, keep } = useLoad((q) => `/prs${q}`)
loadGroups()
const filter = ref('all')
const sel = ref(null)
const detail = ref('')
const diff = ref(false)
const FILTERS = { all: 'all open', ready: 'ready', drafts: 'drafts', auto: 'auto-merge', conflicts: 'conflicts', merged: 'merged' }

const keyOf = (p) => `${p.repo}#${p.number}`
const rows = computed(() => {
  if (filter.value === 'merged') return (data.value?.merged || []).map((p) => ({ ...p, state: `merged ${p.by ? 'by ' + p.by : ''}` }))
  return (data.value?.prs || []).filter((p) => ({
    all: true, ready: !p.draft && !p.conflicts, drafts: p.draft, auto: p.auto, conflicts: p.conflicts,
  })[filter.value]).map((p) => ({
    ...p, state: p.draft ? 'draft' : p.conflicts ? 'CONFLICTS' : p.merge || 'ready', flags: [p.auto && 'auto-merge', p.review].filter(Boolean).join(' · '),
  }))
})
const columns = [
  { key: 'repo', label: 'repo', cls: (r) => (r.provider === 'gitlab' ? 'warn' : '') },
  { key: 'number', label: '#', right: true, fmt: (v, r) => (r.provider === 'gitlab' ? `!${v}` : `#${v}`), card: 'head' },
  { key: 'title', label: 'title', cls: () => '', card: 'main' },
  { key: 'state', label: 'state', card: 'head' },
  { key: 'checks', label: 'checks' },
  { key: 'flags', label: '' },
  { key: 'author', label: 'by', cls: () => 'dim' },
]
const current = computed(() => rows.value.find((p) => keyOf(p) === sel.value))

// Read these repos again (fresh, only them) and put their PRs in place of the ones shown.
async function refresh(repos) {
  const got = await get(`/prs${qs({ repo: repos, fresh: true })}`, { quiet: true })
  if (!data.value) return
  keep({ ...data.value, prs: splice(data.value.prs, got.prs, repos), merged: splice(data.value.merged, got.merged, repos) })
}
const follow = useFollow({ pending: () => (data.value?.prs || []).filter((p) => p.auto).map((p) => p.repo), refresh })

// What the change will have done, shown before GitHub says so (the follow-up a moment later has the last word).
function expect(p, fields) {
  if (!data.value) return
  keep({ ...data.value, prs: data.value.prs.map((x) => (x.repo === p.repo && x.number === p.number ? { ...x, ...fields } : x)) })
}

async function show() {
  const p = current.value
  if (!p) { detail.value = ''; return }
  detail.value = '…'
  try { detail.value = (await get(`/pr${qs({ repo: p.repo, number: p.number, diff: diff.value })}`)).text } catch (e) { detail.value = `error: ${e.message}` }
}
watch([sel, diff], show)

async function doMerge(now) {
  const p = current.value
  if (!p) return
  const got = await change(`${now ? 'Merge' : 'Auto-merge'} ${keyOf(p)} ${p.title}?`, '/merge', { targets: [keyOf(p)], now, ready: p.draft })
  if (!got) return
  detail.value = got.text
  if (got.dry) return
  if (got.ok) expect(p, now ? { merge: 'merging…' } : { auto: true, draft: false })
  follow.now([p.repo])
}
async function mergeAll() {
  const text = await act('Auto-merge every ready PR (drafts and conflicts stay open)?', '/merge', { all: true })
  if (text !== null) { detail.value = text; load(true) }
}
async function ready() {
  const p = current.value
  if (!p || !p.draft) return
  const got = await change(`Mark ${keyOf(p)} ready for review?`, '/ready', { repo: p.repo, number: p.number })
  if (!got) return
  detail.value = got.text
  if (got.dry) return
  if (got.ok) expect(p, { draft: false })
  follow.now([p.repo])
}
const open = () => current.value && window.open(current.value.url, '_blank', 'noopener')
const router = useRouter()
const page = (p) => { const r = p || current.value; if (r) router.push({ path: '/pr', query: { repo: r.repo, number: r.number } }) }
const cycle = () => { const k = Object.keys(FILTERS); filter.value = k[(k.indexOf(filter.value) + 1) % k.length] }
useKeys({ r: () => load(true), m: () => doMerge(false), M: () => doMerge(true), A: mergeAll, y: ready, d: () => { diff.value = !diff.value }, o: open, p: () => page(), v: cycle })
</script>

<template>
  <div class="view">
    <div class="toolbar">
      <Scope :groups="scope.groups" />
      <span class="row"><button v-for="(l, k) in FILTERS" :key="k" class="chip" :class="{ on: filter === k }" @click="filter = k">{{ l }}</button></span>
      <span class="dim k">(v)</span>
      <span class="spacer" />
      <button :disabled="!current || filter === 'merged'" @click="doMerge(false)"><span class="k">m</span> auto-merge</button>
      <button :disabled="!current || filter === 'merged'" @click="doMerge(true)"><span class="k">M</span> merge now</button>
      <button :disabled="!current?.draft" @click="ready"><span class="k">y</span> ready</button>
      <button :class="{ primary: diff }" @click="diff = !diff"><span class="k">d</span> diff</button>
      <button class="any" :disabled="!current" @click="page()"><span class="k">p</span> page</button>
      <button class="any" @click="mergeAll"><span class="k">A</span> auto-merge all ready</button>
    </div>
    <div class="split ld">
      <div><DataTable v-model="sel" :columns="columns" :rows="rows" :row-key="keyOf" :empty="loading ? 'loading…' : 'no open pull requests'" @activate="page" /></div>
      <div class="pad"><TextPane :text="detail" placeholder="pick a pull request" /></div>
    </div>
  </div>
</template>
