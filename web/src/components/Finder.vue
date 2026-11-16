<script setup>
// The finder (Ctrl+K, or ⌕ in the header): type a few letters of a view, a repo, a pull request or a command and
// press Enter. Repos and pull requests come from the lists the views already load (remembered for a minute), so
// opening it again costs nothing. Before you type it shows your last picks.
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { cached } from '../load.js'
import { TABS } from '../router.js'
import { finder } from '../ui.js'
import { remember, search } from '../palette.js'

const props = defineProps({ commands: { type: Array, default: () => [] } })
const router = useRouter()
const field = ref(null)
const list = ref(null)
const at = ref(0)
const repos = ref([])
const prs = ref([])
const note = ref('')

const RECENT = 'mason-finder-recent'
function readRecent() { try { return JSON.parse(localStorage.getItem(RECENT) || '[]') } catch { return [] } }
const recent = ref(readRecent())

async function fill() {
  note.value = ''
  const [r, p] = await Promise.allSettled([cached('/repos', false, { quiet: true }), cached('/prs', false, { quiet: true })])
  if (r.status === 'fulfilled') repos.value = r.value.repos || []
  if (p.status === 'fulfilled') prs.value = p.value.prs || []
  if (r.status === 'rejected' && p.status === 'rejected') note.value = `couldn't load repos: ${r.reason?.message || 'error'}`
}

watch(() => finder.open, (open) => {
  if (!open) return
  at.value = 0
  recent.value = readRecent()
  fill()
  nextTick(() => field.value?.focus())
})

const KIND = { view: 'view', repo: 'repo', pr: 'pr', cmd: 'do' }
const items = computed(() => [
  ...TABS.map((t) => ({ id: `view:${t.name}`, kind: 'view', label: t.label, hint: t.hint, key: t.key, to: t.path })),
  ...props.commands.map((c) => ({ id: `cmd:${c.label}`, kind: 'cmd', label: c.label, hint: c.hint || '', key: c.key, run: c.run })),
  ...repos.value.map((r) => ({ id: `repo:${r.repo}`, kind: 'repo', label: r.repo,
    hint: [r.alias !== r.repo && r.alias, r.group, ...(r.topics || [])].filter(Boolean).join(' · '),
    to: { path: '/repo', query: { repo: r.repo } } })),
  ...prs.value.map((p) => {
    const mark = p.provider === 'gitlab' ? '!' : '#'
    return { id: `pr:${p.repo}${mark}${p.number}`, kind: 'pr', label: `${p.repo}${mark}${p.number} ${p.title}`,
      hint: [p.author, p.draft ? 'draft' : p.merge, p.branch].filter(Boolean).join(' · '),
      to: { path: '/pr', query: { repo: p.repo, number: p.number } } }
  }),
])
const byId = computed(() => new Map(items.value.map((i) => [i.id, i])))
const shown = computed(() => {
  if (finder.query.trim()) return search(items.value, finder.query, 40)
  const last = recent.value.map((id) => byId.value.get(id)).filter(Boolean)
  const seen = new Set(last.map((i) => i.id))
  return [...last.map((i) => ({ ...i, recent: true })), ...items.value.filter((i) => i.kind !== 'pr' && !seen.has(i.id))].slice(0, 40)
})
watch(() => finder.query, () => { at.value = 0 })
watch(at, (i) => nextTick(() => list.value?.children[i]?.scrollIntoView({ block: 'nearest' })))

function close() { finder.open = false; finder.query = '' }
function pick(item) {
  if (!item) return
  recent.value = remember(recent.value, item.id)
  try { localStorage.setItem(RECENT, JSON.stringify(recent.value)) } catch { /* private mode */ }
  close()
  if (item.run) item.run()
  else router.push(item.to)
}
function key(e) {
  const n = shown.value.length
  if (e.key === 'Escape') { e.preventDefault(); close() }
  else if (e.key === 'ArrowDown' || (e.ctrlKey && e.key === 'n')) { e.preventDefault(); at.value = n ? (at.value + 1) % n : 0 }
  else if (e.key === 'ArrowUp' || (e.ctrlKey && e.key === 'p')) { e.preventDefault(); at.value = n ? (at.value + n - 1) % n : 0 }
  else if (e.key === 'Enter') { e.preventDefault(); pick(shown.value[at.value]) }
}
</script>

<template>
  <div v-if="finder.open" class="modal finder-modal" @click.self="close">
    <div class="dialog finder" role="dialog" aria-modal="true" aria-label="find a view, repo, pull request or command">
      <div class="bar">
      <input ref="field" v-model="finder.query" type="text" enterkeyhint="go" placeholder="find a view, repo, pull request or command…"
             autocomplete="off" spellcheck="false" aria-controls="finder-list"
             :aria-activedescendant="shown.length ? `finder-${at}` : undefined" @keydown="key">
        <button class="close" @click="close"><span class="hide-xs">esc</span><span class="show-xs">close</span></button>
      </div>
      <ul id="finder-list" ref="list" role="listbox">
        <li v-for="(item, i) in shown" :id="`finder-${i}`" :key="item.id" role="option" :aria-selected="i === at"
            :class="{ sel: i === at }" @mousemove="at = i" @click="pick(item)">
          <span class="kind dim">{{ item.recent ? 'last' : KIND[item.kind] }}</span>
          <span class="label">{{ item.label }}</span>
          <span class="hint dim">{{ item.hint }}</span>
          <span v-if="item.key" class="k">{{ item.key }}</span>
        </li>
        <li v-if="!shown.length" class="empty">nothing fits “{{ finder.query }}”</li>
      </ul>
      <div class="foot-note dim">
        <span class="hide-xs"><b>↑↓</b> move <b>⏎</b> open <b>esc</b> close</span>
        <span class="spacer" />
        <span v-if="note" class="bad">{{ note }}</span>
        <span v-else>{{ repos.length }} repos · {{ prs.length }} pull requests</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.finder-modal { place-items: start center; padding-top: 12vh; }
.finder { width: min(720px, 94vw); padding: 0; display: flex; flex-direction: column; max-height: 70vh; }
.finder .bar { display: flex; border-bottom: 1px solid var(--line); }
.finder .bar .close { border: 0; color: var(--dim); padding: 0 12px; }
.finder input { flex: 1; min-width: 0; border: 0; padding: 10px 12px; font-size: 15px; outline: none; }
.finder ul { list-style: none; margin: 0; padding: 4px 0; overflow-y: auto; min-height: 0; flex: 1; }
.finder li { display: grid; grid-template-columns: 5ch minmax(0, auto) minmax(0, 1fr) auto; gap: 10px; align-items: baseline;
  padding: 5px 12px; cursor: pointer; }
.finder li.sel { background: var(--sel); }
.finder li.sel .label { color: var(--accent); }
.finder li.empty { display: block; cursor: default; }
.finder .label, .finder .hint { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.finder .k { color: var(--accent); }
.foot-note { display: flex; gap: 8px; padding: 5px 12px; border-top: 1px solid var(--line); background: var(--bg2); font-size: 12px; }
.foot-note b { color: var(--accent); font-weight: 400; }
@media (max-width: 700px) {
  .finder-modal { place-items: stretch; padding-top: 0; }
  .finder { width: 100%; max-height: none; height: 100%; border: 0; }
  .finder input { font-size: 16px; min-height: 48px; } /* 16px: iOS doesn't zoom in */
  .finder li { grid-template-columns: 5ch minmax(0, 1fr); padding: 10px 12px; }
  .finder li .hint { grid-column: 2; }
  .finder li .k { display: none; }
}
</style>
