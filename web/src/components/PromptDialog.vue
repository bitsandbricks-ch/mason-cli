<script setup>
// The y/N prompt every change goes through; "d" runs it as a dry run.
import { nextTick, ref, watch } from 'vue'
import { answer, prompt } from '../ui.js'
import { state } from '../api.js'

const box = ref(null)
const field = ref(null)
const text = ref('')
// The dialog takes the focus while it is open. When it closes, the focus goes back where the keys work again:
// to a field the user was typing in, or else to the view's list, so ↑/↓ keep moving without another click.
let opener = null
watch(() => prompt.open, (open) => {
  if (open) {
    opener = document.activeElement
    text.value = ''
    nextTick(() => (field.value || box.value)?.focus())
  } else {
    const was = opener
    opener = null
    nextTick(() => restoreFocus(was))
  }
})
function restoreFocus(was) {
  if (prompt.open) return // another prompt followed straight away (ask, then ask again)
  const now = document.activeElement
  if (now && now !== document.body && !box.value?.contains(now)) return // something else took the focus already
  const alive = was && was !== document.body && was.isConnected
  if (alive && was.matches('input, textarea, select, [contenteditable], table.table')) { was.focus(); return }
  const list = document.querySelector('table.table[tabindex]')
  if (list) list.focus({ preventScroll: true })
  else if (alive) was.focus()
}
function key(e) {
  if (prompt.notice) { if (['Enter', 'Escape', 'y', 'n'].includes(e.key)) answer('ok'); return }
  if (prompt.choices) {
    const c = prompt.choices.find((x) => x.key === e.key)
    if (c) answer(c.value)
    else if (e.key === 'Escape' || e.key === 'n') answer(null)
    return
  }
  if (e.target.tagName === 'INPUT') { if (e.key === 'Enter') answer(text.value || null); if (e.key === 'Escape') answer(null); return }
  if (e.key === 'y' || e.key === 'Enter') answer(state.dryRun ? 'dry' : 'yes')
  else if (e.key === 'd' && prompt.allowDry) answer('dry')
  else if (e.key === 'n' || e.key === 'Escape') answer(null)
}
</script>

<template>
  <div v-if="prompt.open" class="modal" @click.self="answer(null)">
    <div ref="box" class="dialog" tabindex="0" role="dialog" aria-modal="true" @keydown="key">
      <div class="q">{{ prompt.question }}</div>
      <pre v-if="prompt.detail" class="text dim" style="margin-top: 8px">{{ prompt.detail }}</pre>
      <div v-for="l in prompt.links" :key="l.href" style="margin-top: 6px">
        <a class="accent" :href="l.href" target="_blank" rel="noopener">{{ l.label }}</a>
      </div>
      <div v-if="prompt.input" style="margin-top: 10px">
        <input ref="field" v-model="text" :type="prompt.input.password ? 'password' : 'text'" :placeholder="prompt.input.placeholder"
               style="width: 100%" autofocus>
      </div>
      <div class="row" style="margin-top: 12px">
        <template v-if="prompt.choices">
          <div class="choices">
            <button v-for="(c, i) in prompt.choices" :key="c.value" :class="{ primary: i === 0 }" @click="answer(c.value)">
              <span class="k">{{ c.key }}</span> {{ c.label }}<span v-if="c.hint" class="dim"> · {{ c.hint }}</span></button>
            <button @click="answer(null)"><span class="k">esc</span> cancel</button>
          </div>
        </template>
        <template v-else-if="prompt.notice">
          <button class="primary" @click="answer('ok')">ok</button>
        </template>
        <template v-else-if="prompt.input">
          <button class="primary" @click="answer(text || null)">ok</button>
          <button @click="answer(null)">cancel</button>
        </template>
        <template v-else>
          <button class="primary" @click="answer(state.dryRun ? 'dry' : 'yes')">
            <span class="k">y</span> {{ state.dryRun ? 'yes (dry run is on)' : 'yes' }}</button>
          <button v-if="prompt.allowDry" @click="answer('dry')"><span class="k">d</span> dry run</button>
          <button @click="answer(null)"><span class="k">n</span> no</button>
        </template>
      </div>
    </div>
  </div>
</template>
