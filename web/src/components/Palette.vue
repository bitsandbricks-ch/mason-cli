<script setup>
// The jump box: ctrl+k (or ⌘k, or the ⌕ button) and a few letters of a repo, PR, issue or view; Enter goes
// there (a repo, PR or issue opens in the side panel on a wide screen). ↑↓ pick, Esc closes. The lists come
// from the answers the views already have (remembered for a minute), so opening it costs nothing most times.
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { cached } from '../load.js'
import { TABS } from '../router.js'
import { itemsFrom, rank } from '../palette.js'

const open = defineModel({ type: Boolean, default: false })
const router = useRouter()
const query = ref('')
const at = ref(0)
const input = ref(null)
const data = ref({ repos: [], prs: [], issues: [] })
const loading = ref(false)

async function load() {
  loading.value = true
  const got = await Promise.allSettled([cached('/status'), cached('/prs'), cached('/issues')])
  const [s, p, i] = got.map((g) => (g.status === 'fulfilled' ? g.value : null))
  data.value = { repos: (s?.rows || []).map((r) => r.repo), prs: p?.prs || [], issues: i?.issues || [] }
  loading.value = false
}
const items = computed(() => itemsFrom({ views: TABS, ...data.value }))
const shown = computed(() => rank(items.value, query.value, 12))
watch(shown, () => { at.value = 0 })
watch(open, (o) => {
  if (!o) return
  query.value = ''
  at.value = 0
  load()
  nextTick(() => input.value?.focus())
})

function go(it) {
  if (!it) return
  open.value = false
  router.push(it.to)
}
function key(e) {
  const k = e.key
  if (k === 'ArrowDown' || (k === 'n' && e.ctrlKey)) at.value = Math.min(at.value + 1, shown.value.length - 1)
  else if (k === 'ArrowUp' || (k === 'p' && e.ctrlKey)) at.value = Math.max(at.value - 1, 0)
  else if (k === 'Enter') go(shown.value[at.value])
  else if (k === 'Escape') open.value = false
  else return
  e.preventDefault()
  e.stopPropagation()
}
const KIND = { view: 'view', repo: 'repo', pr: 'PR', issue: 'issue' }
</script>

<template>
  <div v-if="open" class="modal palette-wrap" @click.self="open = false">
    <div class="palette" role="dialog" aria-label="jump to">
      <div class="row"><span class="accent">⌕</span>
        <input ref="input" v-model="query" class="grow" placeholder="jump to a repo, PR, issue or view" aria-label="jump to"
               role="combobox" aria-expanded="true" aria-controls="palette-list" :aria-activedescendant="`palette-${at}`" @keydown="key">
        <span v-if="loading" class="dim cursor" aria-label="loading" />
      </div>
      <ul id="palette-list" role="listbox">
        <li v-for="(it, i) in shown" :id="`palette-${i}`" :key="`${it.kind}:${it.label}`" role="option" :aria-selected="i === at"
            :class="{ sel: i === at }" @mousemove="at = i" @click="go(it)">
          <span class="kind dim">{{ KIND[it.kind] }}</span><span class="label">{{ it.label }}</span><span v-if="it.hint" class="dim hint">{{ it.hint }}</span>
        </li>
        <li v-if="!shown.length" class="dim static">{{ loading ? 'loading…' : 'nothing matches' }}</li>
      </ul>
      <div class="dim foot-keys"><b>↑↓</b> pick <b>⏎</b> go <b>esc</b> close</div>
    </div>
  </div>
</template>
