<script setup>
// The side panel (wide screens): a repo, PR, issue, run or release on the right, next to the list you
// opened it from, so the list stays where it was. ?side= in the URL holds it (see panel.js); Esc or ✕ closes
// it, "page" opens it as its own page, and the left edge drags it wider or narrower (kept on this device).
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { clampWidth, encodeSide } from '../panel.js'
import { SIDE, listKind, openAsPage, sideOpen, useSide } from '../side.js'

const PAGES = {
  repo: defineAsyncComponent(() => import('../views/RepoPage.vue')),
  pr: defineAsyncComponent(() => import('../views/PrPage.vue')),
  issue: defineAsyncComponent(() => import('../views/IssuePage.vue')),
  run: defineAsyncComponent(() => import('../views/RunPage.vue')),
  release: defineAsyncComponent(() => import('../views/ReleasePage.vue')),
}
const LABEL = { repo: 'repo', pr: 'pull request', issue: 'issue', run: 'run', release: 'releases' }

const side = useSide()
provide(SIDE, side)
const router = useRouter()
const target = side.target
const label = computed(() => target.value && encodeSide(target.value).replace(/^\w+:/, ''))
watch(target, (t) => { sideOpen.value = !!t }, { immediate: true })
onBeforeUnmount(() => { sideOpen.value = false })

// ‹ › step through the list beside the panel, as ↑↓ in it would (its order, filter and sort)
const steps = computed(() => !!target.value && (listKind.value === '*' || listKind.value === target.value.kind))
function step(key) {
  const list = document.querySelector('main table.table[tabindex]')
  list?.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }))
}

const KEY = 'mason-side-width'
function saved() { try { return Number(localStorage.getItem(KEY)) || NaN } catch { return NaN } }
const screen = ref(window.innerWidth)
const want = ref(saved())
const width = computed(() => clampWidth(want.value, screen.value))
const onResize = () => { screen.value = window.innerWidth }
onMounted(() => window.addEventListener('resize', onResize))
onBeforeUnmount(() => window.removeEventListener('resize', onResize))

const dragging = ref(false)
function drag(e) {
  if (e.button !== 0) return
  dragging.value = true
  e.currentTarget.setPointerCapture?.(e.pointerId)
  e.preventDefault()
}
function move(e) { if (dragging.value) want.value = clampWidth(screen.value - e.clientX, screen.value) }
const keep = () => { try { localStorage.setItem(KEY, String(width.value)) } catch { /* private mode */ } }
function drop() {
  if (!dragging.value) return
  dragging.value = false
  keep()
}
// ← → on the handle (it is focusable): narrower or wider by a step, for those without a mouse
function nudge(e) {
  const by = { ArrowLeft: 40, ArrowRight: -40 }[e.key]
  if (!by) return
  want.value = clampWidth(width.value + by, screen.value)
  keep()
  e.preventDefault()
  e.stopPropagation()
}
</script>

<template>
  <aside v-if="target" class="side-panel" :class="{ dragging }" :style="{ width: `${width}px` }" :aria-label="`${LABEL[target.kind]} ${label}`">
    <div class="side-grip" role="separator" aria-orientation="vertical" tabindex="0" :aria-valuenow="width"
         title="drag to resize (← → too)" @pointerdown="drag" @pointermove="move" @pointerup="drop" @pointercancel="drop" @keydown="nudge" />
    <div class="side-head">
      <span class="dim">{{ LABEL[target.kind] }}</span>
      <span class="side-title" :title="label">{{ label }}</span>
      <span class="spacer" />
      <template v-if="steps">
        <button title="the one above in the list (↑)" aria-label="previous in the list" @click="step('ArrowUp')">↑</button>
        <button title="the one below in the list (↓)" aria-label="next in the list" @click="step('ArrowDown')">↓</button>
      </template>
      <button title="open as its own page" @click="openAsPage(router, target)">⤢ page</button>
      <button title="close (esc)" aria-label="close the panel" @click="side.close()"><span class="k">esc</span> ✕</button>
    </div>
    <div class="side-body">
      <component :is="PAGES[target.kind]" :key="target.kind" />
    </div>
  </aside>
</template>
