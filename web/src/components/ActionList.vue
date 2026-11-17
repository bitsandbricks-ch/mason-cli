<script setup>
// What you can do with the thing a page or a selected row shows, grouped. On a wide screen: the buttons, one
// group under the other (keys still do the same). On a phone, or with compact: one "actions" button that opens
// them as a sheet (the prompt's choices), so they don't fill the screen.
import { computed } from 'vue'
import { choose, phone } from '../ui.js'

const props = defineProps({
  actions: { type: Array, required: true }, // [{k, label, fn, off?, group?, primary?}]
  title: { type: String, default: 'actions' },
  compact: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  running: { type: String, default: '' }, // the key of the action under way: its button says so and waits
  ended: { type: Object, default: () => ({}) }, // {key: 'ok' | 'bad'}: how an action just ended (a few seconds)
})
const groups = computed(() => {
  const out = []
  for (const a of props.actions) {
    const g = a.group || ''
    let last = out[out.length - 1]
    if (!last || last.name !== g) { last = { name: g, list: [] }; out.push(last) }
    last.list.push(a)
  }
  return out
})
const sheet = computed(() => phone.value || props.compact)
async function pick() {
  const live = props.actions.filter((a) => !a.off)
  if (!live.length) return
  const k = await choose(props.title, live.map((a) => ({ key: a.k, value: a.k, label: a.label, group: a.group })))
  live.find((a) => a.k === k)?.fn()
}
defineExpose({ pick })
</script>

<template>
  <button v-if="sheet" class="action-sheet" :class="{ running: !!running }" :aria-busy="!!running"
          :disabled="disabled || !actions.some((a) => !a.off)" @click="pick">
    <span class="k">.</span> {{ running ? `${actions.find((a) => a.k === running)?.label || 'working'}` : 'actions ▾' }}</button>
  <div v-else class="action-groups">
    <section v-for="g in groups" :key="g.name">
      <h3 v-if="g.name">{{ g.name }}</h3>
      <div class="actions">
        <button v-for="a in g.list" :key="a.k" :disabled="a.off || running === a.k" :aria-busy="running === a.k"
                :class="{ primary: a.primary && !a.off, running: running === a.k, 'ended-ok': ended[a.k] === 'ok', 'ended-bad': ended[a.k] === 'bad' }"
                @click="a.fn">
          <span class="k">{{ a.k }}</span> {{ a.label }}<span v-if="ended[a.k]" class="ended" :class="ended[a.k]">{{ ended[a.k] === 'ok' ? '✓' : '✗' }}</span></button>
      </div>
    </section>
  </div>
</template>
