<script setup>
// ? : a sheet on the right with the keys that work everywhere, and those of what is on screen (the side
// panel's when one is open), read from its buttons, so it never says a key that isn't there. Esc or ? closes it.
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { GLOBAL, keysOf } from '../help.js'

const open = defineModel({ type: Boolean, default: false })
const here = ref([])
const where = ref('')
const box = ref(null)

function read() {
  const side = document.querySelector('.side-panel')
  const root = side || document.querySelector('main')
  where.value = side ? 'in the panel' : 'on this view'
  const buttons = [...(root?.querySelectorAll('button, a.btn') || [])].filter((b) => b.querySelector(':scope > .k'))
  here.value = keysOf(buttons.map((b) => {
    const k = b.querySelector(':scope > .k')
    return { key: k.textContent, label: b.textContent.replace(k.textContent, ''), off: b.disabled }
  }))
}
watch(open, (o) => { if (o) { read(); nextTick(() => box.value?.focus()) } })
// before the views' own keys: Esc here closes the sheet, it doesn't also leave the page under it
function key(e) {
  if (!open.value) return
  if (e.key === 'Escape' || e.key === '?') { open.value = false; e.preventDefault() }
  // nothing under the sheet reacts while it is open (arrows still scroll it: their default stays)
  if (e.key !== 'Tab') e.stopImmediatePropagation()
}
onMounted(() => window.addEventListener('keydown', key, true))
onBeforeUnmount(() => window.removeEventListener('keydown', key, true))
</script>

<template>
  <div v-if="open" class="keys-wrap" @click.self="open = false">
    <aside ref="box" class="keys-sheet" role="dialog" aria-label="keys" tabindex="-1">
      <div class="side-head"><span class="side-title">keys</span><span class="spacer" />
        <button aria-label="close" @click="open = false"><span class="k">esc</span> ✕</button></div>
      <div class="pad">
        <template v-if="here.length">
          <h2>{{ where }}</h2>
          <dl>
            <template v-for="r in here" :key="r.key"><dt>{{ r.key }}</dt><dd :class="{ dim: r.off }">{{ r.label }}<span v-if="r.off"> (not now)</span></dd></template>
          </dl>
        </template>
        <h2>everywhere</h2>
        <dl>
          <template v-for="[k, l] in GLOBAL" :key="k"><dt>{{ k }}</dt><dd>{{ l }}</dd></template>
        </dl>
        <p class="dim">The console (:) takes mason commands, as in a terminal.</p>
      </div>
    </aside>
  </div>
</template>
