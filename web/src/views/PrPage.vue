<script setup>
// One pull or merge request as a page (Enter on Pull requests): its detail, what you can do with it, what
// that printed, and its event log at the bottom. A change updates the page at once: the state flips right
// away, then the detail and the events are asked again until GitHub or GitLab shows it.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { get, qs } from '../api.js'
import { act, forget } from '../load.js'
import { useKeys } from '../keys.js'
import EventLog from '../components/EventLog.vue'
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
watch([repo, number], () => { detail.value = ''; output.value = ''; load() }, { immediate: true })
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
async function merge(now) {
  if (!open.value) return
  const t = await act(`${now ? 'Merge' : 'Auto-merge'} ${ref_.value}?`, '/merge', { targets: [target.value], now, ready: state.value.draft })
  if (t !== null) changed(t, now ? { merged: true, draft: false } : { auto: true, draft: false })
}
async function ready() {
  if (!state.value.draft) return
  const t = await act(`Mark ${ref_.value} ready for review?`, '/ready', { repo: repo.value, number: number.value })
  if (t !== null) changed(t, { draft: false })
}
const url = computed(() => detail.value.split('\n')[1])
const visit = () => { if (url.value?.startsWith('http')) window.open(url.value, '_blank', 'noopener') }
const back = () => (window.history.state?.back ? router.back() : router.push('/prs'))
const actions = computed(() => [
  { k: 'm', label: state.value.auto ? 'auto-merge is on' : 'auto-merge when checks pass', fn: () => merge(false), off: !open.value || state.value.auto },
  { k: 'M', label: 'merge now', fn: () => merge(true), off: !open.value },
  { k: 'y', label: 'mark ready for review', fn: ready, off: !state.value.draft || !open.value },
  { k: 'd', label: diff.value ? 'hide the diff' : 'show the diff', fn: () => { diff.value = !diff.value } },
  { k: 'o', label: `open on ${gitlab.value ? 'GitLab' : 'GitHub'}`, fn: visit },
  { k: 'g', label: 'the repo page', fn: () => router.push({ path: '/repo', query: { repo: repo.value } }) },
])
const keys = { Escape: back, Backspace: back, r: () => { load(); log.value?.refresh() } }
watch(actions, (list) => list.forEach((a) => { keys[a.k] = () => !a.off && a.fn() }), { immediate: true })
useKeys(keys)
</script>

<template>
  <div class="view">
    <div class="toolbar">
      <button class="hide-xs" @click="back"><span class="k">esc</span> back</button>
      <span class="accent hide-xs">pull requests › {{ ref_ }}</span>
      <span class="row">
        <span v-if="state.merged" class="chip on">merged</span>
        <span v-else-if="state.closed" class="chip">closed</span>
        <span v-else-if="state.draft" class="chip">draft</span>
        <span v-else class="chip on">open</span>
        <span v-if="state.auto && open" class="chip on">auto-merge</span>
      </span>
      <span class="spacer" />
      <button @click="load(); log?.refresh()"><span class="k">r</span> reload</button>
    </div>
    <div class="split page">
      <div class="pad">
        <h2>actions</h2>
        <div class="actions">
          <button v-for="a in actions" :key="a.k" :disabled="a.off" :class="{ primary: a.k === 'm' && !a.off }" @click="a.fn">
            <span class="k">{{ a.k }}</span> {{ a.label }}</button>
        </div>
        <template v-if="output"><h2 style="margin-top: 16px">output</h2><TextPane :text="output" /></template>
      </div>
      <div class="pad">
        <TextPane :text="detail" placeholder="loading…" />
      </div>
    </div>
    <EventLog ref="log" band :repo="repo" kind="pr" :number="number" :title="ref_" />
  </div>
</template>
