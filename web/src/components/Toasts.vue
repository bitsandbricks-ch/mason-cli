<script setup>
// The toasts (toast.js): what's under way and how the last changes ended. Bottom right on a wide screen, a row
// above the bottom bar on a phone. A finished one goes by itself (an error stays longer); click it to keep
// it and see the output, × to close it.
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { dismiss, toasts } from '../toast.js'

const route = useRoute()
const open = ref(0) // the toast whose output shows
const glyph = { busy: '●', ok: '✓', error: '✗', info: '•' }
const tone = { busy: 'warn', ok: 'ok', error: 'bad', info: '' }
</script>

<template>
  <div v-if="toasts.length" class="toasts" role="status" aria-live="polite">
    <div v-for="t in toasts" :key="t.id" class="toast" :class="[t.kind, { open: open === t.id }]">
      <div class="line">
        <span class="mark" :class="[tone[t.kind], { cursor: t.kind === 'busy' }]" aria-hidden="true">{{ t.kind === 'busy' ? '' : glyph[t.kind] }}</span>
        <span class="text" :class="t.kind === 'error' ? 'bad' : ''">{{ t.text }}</span>
        <button v-if="t.detail" class="link" :aria-expanded="open === t.id" @click="open = open === t.id ? 0 : t.id">{{ open === t.id ? 'hide' : 'output' }}</button>
        <router-link v-if="t.where && t.where !== route.fullPath && t.kind !== 'busy'" class="dim where" :to="t.where">go there</router-link>
        <button class="link close" :aria-label="`close: ${t.text}`" @click="dismiss(t.id)">×</button>
      </div>
      <pre v-if="open === t.id && t.detail" class="text out">{{ t.detail }}</pre>
    </div>
  </div>
</template>
