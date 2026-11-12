<script setup>
// An error in plain words, with the raw message (what GitHub or the command said) behind "details".
import { computed, ref } from 'vue'
import { explain } from '../ui.js'

const props = defineProps({ error: { type: String, default: '' }, what: { type: String, default: '' } })
const open = ref(false)
const e = computed(() => explain(props.error, props.what))
</script>

<template>
  <div v-if="error" class="error-note" role="alert">
    <span class="bad">✗ {{ e.title }}</span>
    <button v-if="e.raw && e.raw !== e.title" class="link" :aria-expanded="open" @click="open = !open">{{ open ? 'hide' : 'details' }}</button>
    <pre v-if="open" class="text dim">{{ e.raw }}</pre>
  </div>
</template>
