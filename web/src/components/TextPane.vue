<script setup>
// Command output and details: plain text with clickable links (no v-html anywhere). An answer that is only an
// error shows in plain words (ErrorNote); skip drops the first lines when a status header already shows them
// (a detail's name and link).
import { computed } from 'vue'
import { linkify } from '../ui.js'
import ErrorNote from './ErrorNote.vue'

const props = defineProps({
  text: { type: String, default: '' },
  placeholder: { type: String, default: '' },
  skip: { type: Number, default: 0 },
})
const isError = computed(() => /^error:/i.test(String(props.text || '').trim()))
const lines = computed(() => {
  const all = String(props.text || '').split('\n').slice(props.skip)
  while (all.length && !all[0].trim()) all.shift()
  return all.map((l) => ({
    parts: linkify(l),
    cls: /^\s*(error|.*\bnot merged\b)/i.test(l) ? 'bad' : /^\s*-\s/.test(l) ? 'warn' : /^==/.test(l) ? 'accent'
      : /\[dry-run\]/.test(l) ? 'dim' : '',
  }))
})
</script>

<template>
  <ErrorNote v-if="isError" :error="text" />
  <pre v-else-if="text && text !== '…'" class="text"><template v-for="(l, i) in lines" :key="i"><span :class="l.cls"><template
    v-for="(p, j) in l.parts" :key="j"><a v-if="p.href" :href="p.href" target="_blank" rel="noopener noreferrer"
    :title="p.href">{{ p.label }}</a><template v-else>{{ p.text }}</template></template></span>
</template></pre>
  <div v-else class="empty">{{ text === '…' ? 'loading…' : placeholder }}</div>
</template>
