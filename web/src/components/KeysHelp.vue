<script setup>
// ? on a desktop: every key in one place. It used to jump to the console and print a line that was cut off.
import { nextTick, ref, watch } from 'vue'
import { TABS } from '../router.js'

const props = defineProps({ open: Boolean })
const emit = defineEmits(['close'])
const box = ref(null)
watch(() => props.open, async (o) => { if (o) { await nextTick(); box.value?.focus() } })

const EVERYWHERE = [
  ['↑ ↓  j k', 'move in a list, scroll a page'], ['⏎', 'open what is selected'], ['/', 'filter the list'],
  ['r', 'reload'], ['.', 'the actions of the page'], ['esc', 'back, or close'], ['← →', 'the next view'],
  ['t', 'theme'], ['`', 'the log of what was done'], ['?', 'this help'],
]
function key(e) {
  if (e.key === 'Escape' || e.key === '?') { emit('close'); e.preventDefault(); e.stopPropagation() }
}
</script>

<template>
  <div v-if="open" class="modal" @click.self="emit('close')">
    <div ref="box" class="dialog keys-help" tabindex="0" role="dialog" aria-modal="true" aria-label="keys" @keydown="key">
      <div class="q">keys</div>
      <div class="cols">
        <section>
          <h2>views</h2>
          <div v-for="t in TABS" :key="t.name" class="line"><span class="k">{{ t.key }}</span><span>{{ t.label }}</span>
            <span class="dim">{{ t.hint }}</span></div>
        </section>
        <section>
          <h2>everywhere</h2>
          <div v-for="[k, what] in EVERYWHERE" :key="k" class="line"><span class="k">{{ k }}</span><span>{{ what }}</span></div>
          <p class="dim">On a page, the key in front of each action runs it, e.g. <span class="k">m</span> auto-merge.</p>
        </section>
      </div>
      <div class="row" style="margin-top: 12px"><button class="primary" @click="emit('close')"><span class="k">esc</span> close</button></div>
    </div>
  </div>
</template>
