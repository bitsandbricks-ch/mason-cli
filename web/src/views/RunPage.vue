<script setup>
// One workflow run (GitHub) or pipeline (GitLab) as a page (Enter on Runs): its jobs and steps with their
// times, re-run what failed, and its event log at the bottom. While it runs, the page asks again every 10s.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { get, qs } from '../api.js'
import { act, forget } from '../load.js'
import { useKeys } from '../keys.js'
import ActionList from '../components/ActionList.vue'
import EventLog from '../components/EventLog.vue'
import StatusHeader from '../components/StatusHeader.vue'
import { fieldOf } from '../ui.js'
import TextPane from '../components/TextPane.vue'

const route = useRoute()
const router = useRouter()
const repo = computed(() => String(route.query.repo || ''))
const id = computed(() => Number(route.query.id) || 0)
const gitlab = computed(() => repo.value.startsWith('gitlab:'))
const detail = ref('')
const output = ref('')
const log = ref(null)
const sheet = ref(null)
const word = computed(() => (detail.value.split('\n').find((l) => /^\s+state\s/.test(l)) || '').trim().split(/\s+/)[1] || '')
const running = computed(() => ['queued', 'in_progress', 'waiting', 'pending', 'running', 'created', 'requested', 'preparing'].includes(word.value))
const failed = computed(() => ['failure', 'failed', 'timed_out', 'cancelled', 'canceled', 'startup_failure'].includes(word.value))

async function load() {
  if (!repo.value || !id.value) return
  if (!detail.value) detail.value = '…'
  try { detail.value = (await get(`/run${qs({ repo: repo.value, id: id.value })}`)).text } catch (e) { detail.value = `error: ${e.message}` }
}
watch([repo, id], () => { detail.value = ''; output.value = ''; load() }, { immediate: true })
const timer = setInterval(() => { if (running.value && !document.hidden) { load(); log.value?.refresh() } }, 10_000)
onBeforeUnmount(() => clearInterval(timer))

async function rerun() {
  if (!failed.value) return
  const t = await act(`Run the failed jobs of ${gitlab.value ? 'pipeline' : 'run'} ${id.value} in ${repo.value} again?`, '/run/rerun', { repo: repo.value, id: id.value })
  if (t === null) return
  output.value = t
  if (!t.startsWith('error')) { forget('/runs'); setTimeout(load, 2000); log.value?.burst() }
}
const visit = () => { const url = detail.value.split('\n')[1]; if (url?.startsWith('http')) window.open(url, '_blank', 'noopener') }
const back = () => (window.history.state?.back ? router.back() : router.push('/runs'))
const url = computed(() => { const u = detail.value.split('\n')[1] || ''; return u.startsWith('http') ? u : '' })
// the header: what ran, how it ended, and which jobs failed
const failedJobs = computed(() => detail.value.split('\n').map((l) => l.match(/^\s{2}(failure|failed|timed_out|cancelled|canceled|startup_failure)\s+(.+?)(\s{2}\(.*\))?$/))
  .filter(Boolean).map((m) => `job ${m[2]} ${m[1] === 'failure' || m[1] === 'failed' ? 'failed' : m[1].replace('_', ' ')}`))
const badges = computed(() => {
  if (!word.value) return []
  const out = [{ label: 'state', value: word.value, cls: running.value ? 'warn' : undefined }]
  for (const [k, label] of [['event', 'event'], ['branch', 'branch'], ['started', 'started']]) {
    const v = fieldOf(detail.value, k)
    if (v) out.push({ label, value: v, cls: '' })
  }
  return out
})
const next = computed(() => {
  if (!word.value) return null
  if (running.value) return { text: 'still running: this page updates by itself.', cls: 'warn' }
  if (failed.value) return { text: 'it failed.', label: 'run the failed jobs again', key: 'R', fn: rerun }
  return { text: 'nothing to do.', cls: 'ok' }
})
const actions = computed(() => [
  { k: 'R', primary: true, label: 'run the failed jobs again', fn: rerun, off: !failed.value },
  { k: 'o', label: `open on ${gitlab.value ? 'GitLab' : 'GitHub'}`, fn: visit },
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
      <router-link class="dim hide-xs" to="/runs">runs ›</router-link>
      <router-link class="dim hide-xs" :to="{ path: '/repo', query: { repo } }">{{ repo }}</router-link>
      <span v-if="running" class="warn cursor">live</span>
      <span class="spacer" />
      <ActionList ref="sheet" class="show-compact" :actions="actions" :title="`${gitlab ? 'pipeline' : 'run'} ${id}`" compact />
      <button class="any" @click="load(); log?.refresh()"><span class="k">r</span> reload</button>
    </div>
    <StatusHeader :title="(detail.split('\n')[0] || '').trim() && detail !== '…' ? detail.split('\n')[0] : `${gitlab ? 'pipeline' : 'run'} ${id}`"
                  :sub="repo" :url="url" :badges="badges" :blockers="failedJobs" :next="next" />
    <div class="split page">
      <div class="pad">
        <div class="hide-xs"><h2>actions</h2><ActionList :actions="actions" /></div>
        <template v-if="output"><h2 style="margin-top: 16px">output</h2><TextPane :text="output" /></template>
      </div>
      <div class="pad">
        <TextPane :text="detail" :skip="url ? 2 : 0" placeholder="loading…" />
      </div>
    </div>
    <EventLog ref="log" band :repo="repo" kind="run" :number="id" :title="`${repo} ${gitlab ? 'pipeline' : 'run'} ${id}`" />
  </div>
</template>
