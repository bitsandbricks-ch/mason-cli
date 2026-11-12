<script setup>
// The top of a detail page (a repo, a PR, an issue, a run): its name once, as a link, the few states that
// matter as badges, and what to do next, in words and as a button. blockers: why it can't go on (a PR that
// can't merge: which check fails, which review is missing).
import { shortLink, stateClass, glyph } from '../ui.js'

defineProps({
  title: { type: String, default: '' },
  sub: { type: String, default: '' }, // a second line: "acme/web#7" under a PR's title
  url: { type: String, default: '' },
  badges: { type: Array, default: () => [] }, // [{label, value, cls?, to?, href?}]
  blockers: { type: Array, default: () => [] }, // [string]
  next: { type: Object, default: null }, // {text, label?, key?, fn?, cls?}
})
const tone = (b) => b.cls ?? stateClass(b.value)
</script>

<template>
  <header class="status-head">
    <div class="name">
      <a v-if="url" :href="url" target="_blank" rel="noopener noreferrer" :title="url">{{ title || shortLink(url) }} <span class="dim">↗</span></a>
      <span v-else>{{ title }}</span>
      <span v-if="sub" class="dim sub">{{ sub }}</span>
    </div>
    <div v-if="badges.length" class="badges">
      <template v-for="b in badges" :key="b.label">
        <component :is="b.to ? 'router-link' : b.href ? 'a' : 'span'" :to="b.to" :href="b.href" :target="b.href ? '_blank' : undefined"
                   :rel="b.href ? 'noopener noreferrer' : undefined" class="badge" :class="tone(b)">
          <span class="l">{{ b.label }}</span>
          <span class="v" :class="tone(b)"><span v-if="glyph(tone(b))" class="mark" aria-hidden="true">{{ glyph(tone(b)) }}</span>{{ b.value }}</span>
        </component>
      </template>
    </div>
    <ul v-if="blockers.length" class="blockers">
      <li v-for="x in blockers" :key="x" class="bad">✗ {{ x }}</li>
    </ul>
    <div v-if="next" class="next">
      <span class="dim">next:</span> <span :class="next.cls || ''">{{ next.text }}</span>
      <button v-if="next.fn" class="primary" @click="next.fn"><span v-if="next.key" class="k">{{ next.key }}</span> {{ next.label }}</button>
    </div>
  </header>
</template>
