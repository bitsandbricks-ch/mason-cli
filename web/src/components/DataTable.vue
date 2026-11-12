<script setup>
// A keyboard-driven table: ↑/↓ or j/k move, Enter activates, / filters, click a header to sort.
// On a phone it is a list of cards instead: the first column (and those with card: 'head') on top, a
// card: 'main' column on its own line, the rest as small "label value" pairs. In a list and detail view
// (.split.ld) a tap opens the detail; elsewhere a tap selects and the selected card offers activate.
import { computed, getCurrentInstance, nextTick, onMounted, ref, watch } from 'vue'
import ErrorNote from './ErrorNote.vue'
import { glyph, openDetail, phone, stateClass } from '../ui.js'

const props = defineProps({
  columns: { type: Array, required: true }, // [{key, label, cls?: (row) => str, fmt?: (v,row) => str, right?, mark?: false}]
  rows: { type: Array, default: () => [] },
  rowKey: { type: Function, default: (r) => r.key ?? r.repo ?? JSON.stringify(r) },
  empty: { type: String, default: 'nothing here' },
  error: { type: String, default: '' }, // the list couldn't load: said in plain words instead of "empty"
  modelValue: { default: null }, // the selected row's key
})
const emit = defineEmits(['update:modelValue', 'activate'])
const filter = ref('')
const sortKey = ref('')
const sortDir = ref(1)
const filterInput = ref(null)
const table = ref(null)

const cell = (c, r) => (c.fmt ? c.fmt(r[c.key], r) : r[c.key] ?? '')
const cls = (c, r) => (c.cls ? c.cls(r) : stateClass(cell(c, r)))
// a status cell (ok, bad, warn) gets its mark: ✓ ✗ ●; mark: false on a column leaves it plain
const mark = (c, r) => (c.mark === false || c === props.columns[0] ? '' : glyph(cls(c, r)))
const shown = computed(() => {
  const f = filter.value.trim().toLowerCase()
  let out = f ? props.rows.filter((r) => props.columns.some((c) => String(cell(c, r)).toLowerCase().includes(f)))
    : props.rows.slice()
  if (sortKey.value) {
    const c = props.columns.find((x) => x.key === sortKey.value)
    out.sort((a, b) => String(cell(c, a)).localeCompare(String(cell(c, b)), undefined, { numeric: true }) * sortDir.value)
  }
  return out
})
const head = computed(() => props.columns.filter((c, i) => i === 0 || c.card === 'head'))
const main = computed(() => props.columns.filter((c) => c.card === 'main'))
const meta = computed(() => props.columns.filter((c, i) => i > 0 && !c.card))
const blank = (v) => v === '' || v === '-' || v == null
const activates = !!getCurrentInstance()?.vnode.props?.onActivate
const root = ref(null)
const inSplit = ref(false)
onMounted(() => {
  inSplit.value = !!root.value?.closest('.split.ld')
  // a list that opens with nothing else focused takes the keys at once (↑↓, j/k, Enter), not after a click
  const at = document.activeElement
  if (!at || at === document.body) table.value?.focus({ preventScroll: true })
})
function tap(r) {
  emit('update:modelValue', props.rowKey(r))
  if (inSplit.value) openDetail()
}
const sortChoice = computed({
  get: () => (sortKey.value ? `${sortKey.value}:${sortDir.value}` : ''),
  set: (v) => { const [k, d] = v.split(':'); sortKey.value = k; sortDir.value = Number(d) || 1 },
})
const index = computed(() => shown.value.findIndex((r) => props.rowKey(r) === props.modelValue))

function select(i, scroll = true) {
  const r = shown.value[Math.max(0, Math.min(i, shown.value.length - 1))]
  if (!r) return
  emit('update:modelValue', props.rowKey(r))
  if (scroll) nextTick(() => table.value?.querySelector('tr.sel')?.scrollIntoView({ block: 'nearest' }))
}
function key(e) {
  if (e.target.tagName === 'INPUT') return
  const k = e.key
  if (k === 'ArrowDown' || k === 'j') { select(index.value + 1); e.preventDefault() }
  else if (k === 'ArrowUp' || k === 'k') { select(index.value - 1); e.preventDefault() }
  else if (k === 'Home' || k === 'g') { select(0); e.preventDefault() }
  else if (k === 'End' || k === 'G') { select(shown.value.length - 1); e.preventDefault() }
  else if (k === 'Enter') { const r = shown.value[index.value]; if (r) emit('activate', r); e.preventDefault() }
  else if (k === '/') { filterInput.value?.focus(); e.preventDefault() }
}
function sort(c) {
  if (sortKey.value === c.key) sortDir.value = -sortDir.value
  else { sortKey.value = c.key; sortDir.value = 1 }
}
watch(() => props.rows, () => { if (index.value < 0 && shown.value.length && props.modelValue == null) select(0, false) })
defineExpose({ focus: () => table.value?.focus(), shown })
</script>

<template>
  <div ref="root">
    <div class="row pad" style="padding-bottom: 4px">
      <span class="dim">/</span>
      <input ref="filterInput" v-model="filter" class="grow" placeholder="filter" aria-label="filter the list"
             @keydown.esc="filter = ''; table?.focus()" @keydown.enter="table?.focus()">
      <span class="dim nowrap">{{ shown.length }}<template v-if="shown.length !== rows.length">/{{ rows.length }}</template></span>
      <select v-if="phone && rows.length > 1" v-model="sortChoice" class="sort" aria-label="sort by">
        <option value="">sort</option>
        <template v-for="c in columns" :key="c.key">
          <option :value="`${c.key}:1`">{{ c.label || c.key }} ↑</option>
          <option :value="`${c.key}:-1`">{{ c.label || c.key }} ↓</option>
        </template>
      </select>
    </div>
    <ul v-if="phone" class="cards" role="listbox" aria-label="list">
      <li v-for="r in shown" :key="rowKey(r)" role="option" :aria-selected="rowKey(r) === modelValue"
          :class="{ sel: rowKey(r) === modelValue }" @click="tap(r)">
        <div class="head">
          <span v-for="c in head" :key="c.key" :class="cls(c, r)"><span v-if="mark(c, r)" class="mark" aria-hidden="true">{{ mark(c, r) }}</span>{{ cell(c, r) }}</span>
          <span v-if="inSplit" class="go dim" aria-hidden="true">›</span>
        </div>
        <div v-for="c in main" :key="c.key" class="main">{{ cell(c, r) }}</div>
        <div class="meta">
          <template v-for="c in meta" :key="c.key">
            <span v-if="!blank(cell(c, r))"><span v-if="c.label && c.label !== '#'" class="dim">{{ c.label }} </span><span
              :class="cls(c, r)"><span v-if="mark(c, r)" class="mark" aria-hidden="true">{{ mark(c, r) }}</span>{{ cell(c, r) }}</span></span>
          </template>
        </div>
        <button v-if="activates && !inSplit && rowKey(r) === modelValue" class="open" @click.stop="emit('activate', r)">open ↗</button>
      </li>
    </ul>
    <table v-else ref="table" class="table" tabindex="0" @keydown="key">
      <thead>
        <tr>
          <th v-for="c in columns" :key="c.key" :class="{ right: c.right }" @click="sort(c)">
            {{ c.label }}<span v-if="sortKey === c.key">{{ sortDir > 0 ? ' ↑' : ' ↓' }}</span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in shown" :key="rowKey(r)" :class="{ sel: rowKey(r) === modelValue }"
            @click="emit('update:modelValue', rowKey(r))" @dblclick="emit('activate', r)">
          <td v-for="c in columns" :key="c.key" :class="[cls(c, r), { right: c.right }]"
              :title="String(cell(c, r))"><span v-if="mark(c, r)" class="mark" aria-hidden="true">{{ mark(c, r) }}</span>{{ cell(c, r) }}</td>
        </tr>
      </tbody>
    </table>
    <div v-if="error && !rows.length" class="empty"><ErrorNote :error="error" what="couldn't load the list" /><span class="dim">r tries again.</span></div>
    <div v-else-if="!shown.length" class="empty">{{ rows.length ? 'nothing matches the filter' : empty }}</div>
  </div>
</template>
