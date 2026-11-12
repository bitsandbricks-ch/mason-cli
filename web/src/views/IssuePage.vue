<script setup>
// One issue as a page (Enter on Issues): its text and comments, comment, close or reopen, and its event
// log at the bottom.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { get, qs } from '../api.js'
import { act, forget } from '../load.js'
import { useKeys } from '../keys.js'
import { ask, fieldOf } from '../ui.js'
import ActionList from '../components/ActionList.vue'
import StatusHeader from '../components/StatusHeader.vue'
import EventLog from '../components/EventLog.vue'
import TextPane from '../components/TextPane.vue'

const route = useRoute()
const router = useRouter()
const repo = computed(() => String(route.query.repo || ''))
const number = computed(() => Number(route.query.number) || 0)
const name = computed(() => `${repo.value}#${number.value}`)
const detail = ref('')
const output = ref('')
const isOpen = ref(true)
const log = ref(null)
const sheet = ref(null)

async function load() {
  if (!repo.value || !number.value) return
  if (!detail.value) detail.value = '…'
  try {
    const t = (await get(`/issue${qs({ repo: repo.value, number: number.value })}`)).text
    detail.value = t
    const line = t.split('\n').find((l) => /^\s+state\s/.test(l)) || ''
    isOpen.value = !/\bclosed\b/.test(line)
  } catch (e) { detail.value = `error: ${e.message}` }
}
watch([repo, number], () => { detail.value = ''; output.value = ''; load() }, { immediate: true })

function changed(text, open) {
  output.value = text
  if (text.startsWith('error')) return
  if (open !== undefined && !/\[dry-run\]/.test(text)) isOpen.value = open
  forget('/issues')
  load()
  setTimeout(load, 3000)
  log.value?.burst()
}
async function setState(close) {
  if (close !== isOpen.value) return
  const t = await act(`${close ? 'Close' : 'Reopen'} ${name.value}?`, '/issue', { repo: repo.value, number: number.value, action: close ? 'close' : 'reopen' })
  if (t !== null) changed(t, !close)
}
async function comment() {
  const said = await ask(`Comment on ${name.value}`, { input: { placeholder: 'your comment' }, allowDry: false })
  if (!said?.trim()) return
  const t = await act(`Post the comment on ${name.value}?`, '/issue', { repo: repo.value, number: number.value, action: 'comment', text: said }, { detail: said })
  if (t !== null) changed(t)
}
const visit = () => { const url = detail.value.split('\n')[1]; if (url?.startsWith('http')) window.open(url, '_blank', 'noopener') }
const back = () => (window.history.state?.back ? router.back() : router.push('/issues'))
const url = computed(() => { const u = detail.value.split('\n')[1] || ''; return u.startsWith('http') ? u : '' })
const titleLine = computed(() => (detail.value === '…' ? '' : (detail.value.split('\n')[0] || '').replace(/^[#!]\d+\s*/, '')))
const badges = computed(() => {
  if (!titleLine.value) return []
  const out = [{ label: 'state', value: isOpen.value ? 'open' : 'closed', cls: isOpen.value ? '' : 'ok' }]
  for (const k of ['labels', 'assignees', 'milestone']) {
    const v = fieldOf(detail.value, k)
    if (v) out.push({ label: k, value: v, cls: '' })
  }
  return out
})
const actions = computed(() => [
  { k: 'm', primary: true, label: 'comment', fn: comment },
  { k: 'c', label: 'close', fn: () => setState(true), off: !isOpen.value },
  { k: 'u', label: 'reopen', fn: () => setState(false), off: isOpen.value },
  { k: 'o', label: `open on ${repo.value.startsWith('gitlab:') ? 'GitLab' : 'GitHub'}`, fn: visit },
  { k: 'g', label: 'the repo page', fn: () => router.push({ path: '/repo', query: { repo: repo.value } }) },
])
const keys = { '.': () => sheet.value?.pick(), Escape: back, Backspace: back, r: () => { load(); log.value?.refresh() } }
watch(actions, (list) => list.forEach((a) => { keys[a.k] = () => !a.off && a.fn() }), { immediate: true })
useKeys(keys)
</script>

<template>
  <div class="view">
    <div class="toolbar">
      <button class="hide-xs" @click="back"><span class="k">esc</span> back</button>
      <router-link class="dim hide-xs" to="/issues">issues ›</router-link>
      <router-link class="dim hide-xs" :to="{ path: '/repo', query: { repo } }">{{ repo }}</router-link>
      <span class="spacer" />
      <ActionList ref="sheet" class="show-compact" :actions="actions" :title="name" compact />
      <button class="any" @click="load(); log?.refresh()"><span class="k">r</span> reload</button>
    </div>
    <StatusHeader :title="titleLine || name" :sub="name" :url="url" :badges="badges" />
    <div class="split page">
      <div class="pad">
        <div class="hide-xs"><h2>actions</h2><ActionList :actions="actions" /></div>
        <template v-if="output"><h2 style="margin-top: 16px">output</h2><TextPane :text="output" /></template>
      </div>
      <div class="pad">
        <TextPane :text="detail" :skip="url ? 2 : 0" placeholder="loading…" />
      </div>
    </div>
    <EventLog ref="log" band :repo="repo" kind="issue" :number="number" :title="name" />
  </div>
</template>
