<script setup>
// The console: type mason commands as in a terminal. ↑/↓ walk the history; changes ask first.
import { nextTick, onMounted, ref } from 'vue'
import { get, log, post, state } from '../api.js'
import { ask } from '../ui.js'
import TextPane from '../components/TextPane.vue'
import { prepare } from '../consoleline.js'

const HISTORY = 'mason.console.history'
const line = ref('')
const out = ref([]) // [{line, text}]
const writes = ref(new Set())
const plugins = ref(new Set())
const history = ref(load())
const at = ref(-1)
let draft = '' // the typed line while ↑ walks the history
const input = ref(null)
const screen = ref(null)
const running = ref(false)

function load() { try { return JSON.parse(localStorage.getItem(HISTORY) || '[]') } catch { return [] } }
function remember(l) {
  history.value = [l, ...history.value.filter((x) => x !== l)].slice(0, 100)
  try { localStorage.setItem(HISTORY, JSON.stringify(history.value)) } catch { /* private window */ }
}
const QUICK = ['status', 'prs', 'runs', 'approve --dry-run', 'releases --problems', 'security', 'doctor', 'stats']
function quick(l) { line.value = l; run() }
onMounted(async () => {
  if (!window.matchMedia('(pointer: coarse)').matches) input.value?.focus() // no keyboard popping up on phones
  try {
    const c = await get('/console/commands')
    writes.value = new Set(c.writes)
    plugins.value = new Set(c.plugins)
    out.value.push({ line: '', text: `${c.help}\nhere: ${[...c.reads, ...c.writes, ...c.plugins].sort().join(' ')}` })
  } catch (e) { log(e.message, 'error') }
})
async function run() {
  const typed = line.value.trim()
  if (!typed || running.value) return
  if (typed === 'clear') { out.value = []; line.value = ''; return }
  remember(typed)
  at.value = -1
  line.value = ''
  // the header's dry-run switch counts here too; a line that can change repos asks first
  let { line: l, ask: asks } = prepare(typed, { writes: writes.value, plugins: plugins.value, dryRun: state.dryRun })
  if (asks) {
    const a = await ask(`Run "${l}"? It can change repos.`)
    if (!a) { out.value.push({ line: l, text: 'cancelled' }); await settle(); return }
    if (a === 'dry') l = prepare(l, { writes: writes.value, plugins: plugins.value, dryRun: true }).line
  }
  running.value = true
  try {
    out.value.push({ line: l, text: (await post('/console', { line: l })).text })
  } catch (e) {
    out.value.push({ line: l, text: `error: ${e.message}` })
  } finally {
    running.value = false
    await settle()
  }
}
// the newest answer in view and the keys back in the line, also after a cancelled ask
async function settle() {
  await nextTick()
  screen.value?.scrollTo({ top: screen.value.scrollHeight })
  input.value?.focus()
}
function key(e) {
  // ↓ past the newest line gives back what was being typed, as a shell does
  if (e.key === 'ArrowUp' && at.value < history.value.length - 1) {
    if (at.value < 0) draft = line.value
    at.value++; line.value = history.value[at.value]; e.preventDefault()
  } else if (e.key === 'ArrowDown' && at.value >= 0) { at.value--; line.value = at.value < 0 ? draft : history.value[at.value]; e.preventDefault() }
  else if (e.key === 'l' && e.ctrlKey) { out.value = []; e.preventDefault() }
}
</script>

<template>
  <div class="view" @click.self="input?.focus()">
    <div ref="screen" class="scroll pad console-out">
      <div v-for="(o, i) in out" :key="i" style="margin-bottom: 10px">
        <div v-if="o.line"><span class="accent">$ mason</span> {{ o.line.replace(/^mason\s+/, '') }}</div>
        <TextPane :text="o.text" />
      </div>
      <div v-if="running" class="warn cursor">running </div>
    </div>
    <div class="toolbar quick" aria-label="quick commands">
      <button v-for="q in QUICK" :key="q" :disabled="running" @click="quick(q)">{{ q }}</button>
    </div>
    <div class="toolbar" style="border-top: 1px solid var(--line); border-bottom: 0">
      <span class="accent">$ mason</span>
      <input ref="input" v-model="line" class="grow" :disabled="running" aria-label="command"
             placeholder="status · prs · runs · doctor --group web · stats --days 90 · clear" @keydown.enter="run" @keydown="key">
      <span v-if="state.dryRun" class="warn">dry run</span>
    </div>
  </div>
</template>
