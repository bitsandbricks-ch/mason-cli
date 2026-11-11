<script setup>
// The event log at the bottom of a detail page: what happened to this repo, PR, issue, release or run on
// GitHub or GitLab, and your own changes from Mason's audit log, newest first. It asks again every 30s
// while the page is open, and every few seconds for a while after a change (burst), so a merge, a ready or
// a release shows up without a reload. A row with more text opens on a click.
// band: the full-width bar at the bottom of a view (lists and pages); it folds away, and stays folded.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { get, qs } from '../api.js'
import { ago } from '../ui.js'

const props = defineProps({
  repo: { type: String, required: true },
  kind: { type: String, required: true }, // repo, pr, issue, release, run
  number: { type: [Number, String], default: '' }, // pr, issue; the id of a run
  tag: { type: String, default: '' }, // release
  band: { type: Boolean, default: false },
  title: { type: String, default: '' }, // what it is about, in the band's header
})
const events = ref([])
const error = ref('')
const loading = ref(false)
const source = ref('all')
const open = ref(new Set())
const seen = ref(new Set())
const fresh = ref(new Set())
const at = ref(null)

const path = computed(() => `/events${qs({ repo: props.repo, kind: props.kind, number: props.number, tag: props.tag })}`)
const ready = computed(() => props.repo && (props.kind === 'repo' || (props.kind === 'release' ? props.tag : props.number)))
const keyOf = (e) => `${e.source}|${e.at}|${e.what}|${e.who}`

async function load() {
  if (!ready.value) { events.value = []; return }
  loading.value = true
  const asked = path.value
  try {
    const got = (await get(asked)).events || []
    if (asked !== path.value) return // the page moved on meanwhile
    const before = seen.value
    fresh.value = before.size ? new Set(got.map(keyOf).filter((k) => !before.has(k))) : new Set()
    seen.value = new Set(got.map(keyOf))
    events.value = got
    error.value = ''
    at.value = new Date()
  } catch (e) { if (asked === path.value) error.value = e.message } finally { loading.value = false }
}
// moving through a list asks once the selection rests (250ms), not for every row passed
let pending = null
watch(path, () => {
  events.value = []; seen.value = new Set(); fresh.value = new Set(); open.value = new Set()
  clearTimeout(pending)
  if (folded.value) return
  pending = setTimeout(load, props.band ? 250 : 0)
})
function stored() { try { return localStorage.getItem('mason-events') === 'folded' } catch { return false } }
const folded = ref(props.band && stored())
watch(folded, (f) => { try { localStorage.setItem('mason-events', f ? 'folded' : 'open') } catch { /* private mode */ } if (!f) load() })
if (!folded.value) load()

// every 30s while the tab is visible; burst() asks again after 2, 5, 10, 20 and 40s
let timer = null
let bursts = []
onMounted(() => { timer = setInterval(() => { if (!document.hidden && !folded.value) load() }, 30_000) })
onBeforeUnmount(() => { clearInterval(timer); clearTimeout(pending); bursts.forEach(clearTimeout) })
function burst() {
  bursts.forEach(clearTimeout)
  bursts = [2, 5, 10, 20, 40].map((s) => setTimeout(load, s * 1000))
  load()
}
defineExpose({ refresh: load, burst })

const sources = computed(() => ['all', ...new Set(events.value.map((e) => e.source))])
const shown = computed(() => (source.value === 'all' ? events.value : events.value.filter((e) => e.source === source.value)))
const label = (s) => (s === 'mason' ? 'yours' : s)
function toggle(e) {
  if (!e.more) return
  const k = keyOf(e)
  const s = new Set(open.value)
  if (s.has(k)) s.delete(k); else s.add(k)
  open.value = s
}
const mark = (e) => ({ ok: '✓', bad: '✗', warn: '!' }[e.state] || (e.source === 'mason' ? '$' : '·'))
const when = (s) => { try { return new Date(s).toLocaleString() } catch { return s } }
</script>

<template>
  <section class="events" :class="{ band, folded }" aria-label="event log">
    <div class="events-head">
      <button v-if="band" class="fold" :aria-expanded="!folded" :title="folded ? 'show the events' : 'fold the events away'"
              @click="folded = !folded">{{ folded ? '▸' : '▾' }}</button>
      <h2>events <span class="dim">({{ shown.length }})</span></h2>
      <span v-if="title" class="accent about">{{ title }}</span>
      <span class="row">
        <button v-for="s in sources" :key="s" class="chip" :class="{ on: source === s }" @click="source = s">{{ label(s) }}</button>
      </span>
      <span class="spacer" />
      <span class="dim" :title="at ? `asked ${at.toLocaleTimeString()}; again every 30s` : ''">
        <span v-if="loading" class="warn">updating…</span><template v-else-if="at">live · {{ at.toLocaleTimeString() }}</template>
      </span>
      <button :disabled="loading" @click="load">reload</button>
    </div>
    <template v-if="!folded">
    <div v-if="!ready" class="empty">pick a row to see what happened to it</div>
    <div v-else-if="error" class="bad">error: {{ error }}</div>
    <div v-else-if="!shown.length" class="empty">{{ loading ? 'loading…' : 'nothing yet' }}</div>
    <ol v-else class="event-list">
      <li v-for="e in shown" :key="keyOf(e)" :class="{ new: fresh.has(keyOf(e)), more: !!e.more }" @click="toggle(e)">
        <span class="when dim" :title="when(e.at)">{{ ago(e.at) }}</span>
        <span class="mark" :class="e.state">{{ mark(e) }}</span>
        <span class="body">
          <span class="what" :class="e.state === 'bad' ? 'bad' : e.source === 'mason' ? 'accent' : ''">{{ e.what }}</span>
          <span v-if="e.who" class="who dim"> · {{ e.who }}</span>
          <span v-if="e.source !== 'mason' && e.source !== 'github'" class="dim"> · {{ e.source }}</span>
          <span v-if="e.detail" class="detail dim">{{ e.detail }}<template v-if="e.more && !open.has(keyOf(e))"> …</template></span>
          <pre v-if="open.has(keyOf(e))" class="text more">{{ e.more }}</pre>
        </span>
        <a v-if="e.url" class="go" :href="e.url" target="_blank" rel="noopener noreferrer" :title="e.url" @click.stop>↗</a>
      </li>
    </ol>
    </template>
  </section>
</template>
