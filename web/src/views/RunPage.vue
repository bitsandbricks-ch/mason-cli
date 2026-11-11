<script setup>
// One workflow run (GitHub) or pipeline (GitLab) as a page (Enter on Runs): its jobs and steps with their
// times, re-run what failed, and its event log at the bottom. While it runs, the page asks again every 10s.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { get, qs } from '../api.js'
import { act, forget } from '../load.js'
import { useKeys } from '../keys.js'
import EventLog from '../components/EventLog.vue'
import TextPane from '../components/TextPane.vue'

const route = useRoute()
const router = useRouter()
const repo = computed(() => String(route.query.repo || ''))
const id = computed(() => Number(route.query.id) || 0)
const gitlab = computed(() => repo.value.startsWith('gitlab:'))
const detail = ref('')
const output = ref('')
const log = ref(null)
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
const actions = computed(() => [
  { k: 'R', label: 'run the failed jobs again', fn: rerun, off: !failed.value },
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
      <span class="accent hide-xs">runs › {{ repo }} {{ gitlab ? 'pipeline' : 'run' }} {{ id }}</span>
      <span class="row"><span v-if="word" class="chip" :class="{ on: !failed }">{{ word }}</span>
        <span v-if="running" class="warn cursor">live</span></span>
      <span class="spacer" />
      <button @click="load(); log?.refresh()"><span class="k">r</span> reload</button>
    </div>
    <div class="split page">
      <div class="pad">
        <h2>actions</h2>
        <div class="actions">
          <button v-for="a in actions" :key="a.k" :disabled="a.off" @click="a.fn"><span class="k">{{ a.k }}</span> {{ a.label }}</button>
        </div>
        <template v-if="output"><h2 style="margin-top: 16px">output</h2><TextPane :text="output" /></template>
      </div>
      <div class="pad">
        <TextPane :text="detail" placeholder="loading…" />
      </div>
    </div>
    <EventLog ref="log" band :repo="repo" kind="run" :number="id" :title="`${repo} ${gitlab ? 'pipeline' : 'run'} ${id}`" />
  </div>
</template>
