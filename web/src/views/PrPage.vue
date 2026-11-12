<script setup>
// One pull or merge request as a page (Enter on Pull requests): its detail, what you can do with it, what
// that printed, and its event log at the bottom. A change updates the page at once: the state flips right
// away, then the detail and the events are asked again until GitHub or GitLab shows it.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { get, qs } from '../api.js'
import { act, forget } from '../load.js'
import { useKeys } from '../keys.js'
import ActionList from '../components/ActionList.vue'
import EventLog from '../components/EventLog.vue'
import StatusHeader from '../components/StatusHeader.vue'
import TextPane from '../components/TextPane.vue'

const route = useRoute()
const router = useRouter()
const repo = computed(() => String(route.query.repo || ''))
const number = computed(() => Number(route.query.number) || 0)
const gitlab = computed(() => repo.value.startsWith('gitlab:'))
const ref_ = computed(() => `${repo.value}${gitlab.value ? '!' : '#'}${number.value}`)
const target = computed(() => `${repo.value}#${number.value}`) // what /merge and the audit log call it
const detail = ref('')
const output = ref('')
const diff = ref(false)
const log = ref(null)
const sheet = ref(null)
// what the detail says, and what a change just did (shown until the next answer agrees)
const state = ref({ draft: false, auto: false, merged: false, closed: false })

function parse(text) {
  const line = text.split('\n').find((l) => /^\s+state\s/.test(l)) || ''
  return {
    draft: /\(draft\)/.test(line), auto: /auto-merge on/.test(text),
    merged: /\bmerged\b/i.test(line), closed: /\bclosed\b/i.test(line),
  }
}
async function load() {
  if (!repo.value || !number.value) return
  if (!detail.value) detail.value = '…'
  try {
    const t = (await get(`/pr${qs({ repo: repo.value, number: number.value, diff: diff.value })}`)).text
    detail.value = t
    state.value = parse(t)
  } catch (e) { detail.value = `error: ${e.message}` }
}
// whether you may merge past the base branch's rules (GitHub's bypass), rule by rule
const bypass = ref(null)
async function loadBypass() {
  bypass.value = null
  if (gitlab.value || !repo.value || !number.value) return
  try { bypass.value = await get(`/pr/bypass${qs({ repo: repo.value, number: number.value })}`, { quiet: true }) } catch { bypass.value = null }
}
watch([repo, number], () => { detail.value = ''; output.value = ''; load(); loadBypass() }, { immediate: true })
watch(diff, load)

// after a change: show it now, then ask again (GitHub takes a moment to show auto-merge and merges)
function changed(text, flip) {
  output.value = text
  if (text.startsWith('error')) return
  if (flip && !/\[dry-run\]/.test(text)) state.value = { ...state.value, ...flip }
  forget('/prs'); forget('/repo'); forget('/status')
  load()
  setTimeout(load, 3000)
  setTimeout(load, 10000)
  log.value?.burst()
}
const open = computed(() => !state.value.merged && !state.value.closed)
async function merge_(now) {
  if (!open.value) return
  const t = await act(`${now ? 'Merge' : 'Auto-merge'} ${ref_.value}?`, '/merge', { targets: [target.value], now, ready: state.value.draft })
  if (t !== null) changed(t, now ? { merged: true, draft: false } : { auto: true, draft: false })
}
async function mergeBypass() {
  const b = bypass.value
  if (!open.value || !b?.can) return
  const t = await act(`Merge ${ref_.value} now, bypassing the branch rules?`, '/merge', { targets: [target.value], bypass: true, ready: state.value.draft },
    { detail: `Skips what ${b.base} asks for (reviews, checks): ${b.rules.map((r) => `${r.name} (${r.why})`).join(', ')}. The audit log keeps it.` })
  if (t !== null) changed(t, { merged: true, draft: false })
}
async function ready() {
  if (!state.value.draft) return
  const t = await act(`Mark ${ref_.value} ready for review?`, '/ready', { repo: repo.value, number: number.value })
  if (t !== null) changed(t, { draft: false })
}
const url = computed(() => detail.value.split('\n')[1])

// What the header shows, read from the detail (the same text the CLI prints): the fields, and the checks
// with their states, so it can say why the PR can't merge yet.
const field = (name) => (detail.value.split('\n').find((l) => new RegExp(`^\\s+${name}\\s`).test(l)) || '').trim().slice(name.length).trim()
const titleLine = computed(() => (detail.value.split('\n')[0] || '').replace(/^[#!]\d+\s*/, ''))
const checks = computed(() => {
  const lines = detail.value.split('\n')
  const at = lines.findIndex((l) => /^(Checks \(|Pipeline )/.test(l))
  if (at < 0) return []
  const out = []
  for (const l of lines.slice(at + 1)) {
    if (!l.trim()) break
    const m = l.match(/^\s{2}(\S+)\s+(.+)$/)
    if (m && !/^https?:/.test(m[2]) && !/^https?:/.test(m[1])) out.push({ state: m[1], name: m[2] })
  }
  return out
})
const FAILED = /^(failure|failed|error|timed_out|cancelled|canceled|action_required|startup_failure)$/
const RUNNING = /^(pending|in_progress|queued|running|waiting|expected|created)$/
const failing = computed(() => checks.value.filter((c) => FAILED.test(c.state)))
const running = computed(() => checks.value.filter((c) => RUNNING.test(c.state)))
const merge = computed(() => field('merge').replace(/; auto-merge on$/, ''))
const review = computed(() => field('review'))
const blockers = computed(() => {
  if (!open.value) return []
  const out = failing.value.map((c) => `check ${c.name} fails`)
  if (/required|changes requested|not approved/.test(review.value)) out.push(`review: ${review.value}`)
  if (/conflict/.test(merge.value)) out.push('it has merge conflicts with the base branch')
  if (/behind/.test(merge.value)) out.push('it is behind the base branch: update it first')
  return out
})
const badges = computed(() => {
  const st = state.value
  const out = [{ label: 'state', value: st.merged ? 'merged' : st.closed ? 'closed' : st.draft ? 'draft' : 'open', cls: st.merged ? 'ok' : st.draft ? 'warn' : '' }]
  if (checks.value.length) {
    out.push({ label: 'checks', value: failing.value.length ? `${failing.value.length} of ${checks.value.length} failing`
      : running.value.length ? `${running.value.length} running` : `${checks.value.length} passing`,
    cls: failing.value.length ? 'bad' : running.value.length ? 'warn' : 'ok', href: url.value ? `${url.value}/checks` : undefined })
  }
  if (review.value) out.push({ label: 'review', value: review.value.replace(/^review /, '') })
  if (open.value && merge.value) out.push({ label: 'merge', value: merge.value.replace(/:.*/, ''), cls: /^(ready|mergeable)/.test(merge.value) ? 'ok' : undefined })
  if (st.auto && open.value) out.push({ label: 'auto-merge', value: 'on', cls: 'ok' })
  if (open.value && bypass.value?.rules?.length) out.push({ label: 'bypass', value: bypass.value.can ? 'you may' : 'not allowed', cls: bypass.value.can ? 'warn' : '' })
  const size = field('size')
  if (size) out.push({ label: 'size', value: size, cls: '' })
  return out
})
const next = computed(() => {
  const st = state.value
  if (!detail.value || detail.value === '…' || /^error/.test(detail.value)) return null
  if (st.merged) return { text: 'merged.', cls: 'ok' }
  if (st.closed) return { text: 'closed without merging.' }
  if (st.draft) return { text: 'still a draft.', label: 'mark ready for review', key: 'y', fn: ready }
  if (st.auto) return { text: blockers.value.length ? 'auto-merge is on: it merges once the above is sorted.' : 'auto-merge is on: it merges by itself.', cls: 'ok' }
  if (!blockers.value.length && /^(ready|mergeable)/.test(merge.value)) return { text: 'ready to merge.', label: 'merge now', key: 'M', fn: () => merge_(true) }
  return { text: running.value.length ? 'checks are still running.' : "it can't merge yet.", label: 'auto-merge when it can', key: 'm', fn: () => merge_(false) }
})
const visit = () => { if (url.value?.startsWith('http')) window.open(url.value, '_blank', 'noopener') }
const back = () => (window.history.state?.back ? router.back() : router.push('/prs'))
const actions = computed(() => [
  { k: 'm', group: 'merge', primary: true, label: state.value.auto ? 'auto-merge is on' : 'auto-merge when checks pass', fn: () => merge_(false), off: !open.value || state.value.auto },
  { k: 'M', group: 'merge', label: 'merge now', fn: () => merge_(true), off: !open.value },
  { k: 'B', group: 'merge', label: 'merge now, bypassing the rules', fn: mergeBypass, off: !open.value || !bypass.value?.can },
  { k: 'y', group: 'merge', label: 'mark ready for review', fn: ready, off: !state.value.draft || !open.value },
  { k: 'd', group: 'look', label: diff.value ? 'hide the diff' : 'show the diff', fn: () => { diff.value = !diff.value } },
  { k: 'o', group: 'look', label: `open on ${gitlab.value ? 'GitLab' : 'GitHub'}`, fn: visit },
  { k: 'g', group: 'look', label: 'the repo page', fn: () => router.push({ path: '/repo', query: { repo: repo.value } }) },
])
const keys = { '.': () => sheet.value?.pick(), Escape: back, Backspace: back, r: () => { load(); log.value?.refresh() } }
watch(actions, (list) => list.forEach((a) => { keys[a.k] = () => !a.off && a.fn() }), { immediate: true })
useKeys(keys)
</script>

<template>
  <div class="view">
    <div class="toolbar">
      <button class="hide-xs" @click="back"><span class="k">esc</span> back</button>
      <router-link class="dim hide-xs" to="/prs">pull requests ›</router-link>
      <router-link class="dim hide-xs" :to="{ path: '/repo', query: { repo } }">{{ repo }}</router-link>
      <span class="spacer" />
      <ActionList ref="sheet" class="show-compact" :actions="actions" :title="ref_" compact />
      <button class="any" @click="load(); log?.refresh()"><span class="k">r</span> reload</button>
    </div>
    <StatusHeader :title="titleLine || ref_" :sub="ref_" :url="url?.startsWith('http') ? url : ''" :badges="badges" :blockers="blockers" :next="next" />
    <div class="split page">
      <div class="pad">
        <div class="hide-xs"><h2>actions</h2><ActionList :actions="actions" /></div>
        <template v-if="output"><h2 style="margin-top: 16px">output</h2><TextPane :text="output" /></template>
      </div>
      <div class="pad">
        <TextPane :text="detail" :skip="2" placeholder="loading…" />
      </div>
    </div>
    <EventLog ref="log" band :repo="repo" kind="pr" :number="number" :title="ref_" />
  </div>
</template>
