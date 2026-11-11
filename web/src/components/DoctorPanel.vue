<script setup>
// A repo against its defaults (mason doctor), kept: the last check shows when the page opens and is checked
// on the spot when there is none. "check again" asks GitHub/GitLab again; c and f on the page refresh it too.
// Each fix it suggests is a button (fix the drift, open a sync PR): the page runs it (emit run: 'fix' | 'sync'),
// the command stays as the button's title for the CLI.
import { ref, watch } from 'vue'
import { get, qs } from '../api.js'
import ErrorNote from './ErrorNote.vue'

const emit = defineEmits(['run', 'result'])
const props = defineProps({
  repo: { type: String, required: true },
  stamp: { type: Number, default: 0 }, // bumped by the page after it ran doctor (c, f): show the kept result
})
const result = ref(null)
const error = ref('')
const busy = ref(false)

async function load(fresh = false) {
  busy.value = true
  error.value = ''
  try { result.value = await get(`/doctor${qs({ repo: props.repo, fresh })}`); emit('result', result.value) } catch (e) { error.value = e.message }
  finally { busy.value = false }
}
watch(() => props.repo, () => { result.value = null; load() }, { immediate: true })
watch(() => props.stamp, () => load())

function ago(t) {
  const s = Math.max(0, Math.round(Date.now() / 1000 - t))
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  return `${Math.round(s / 3600)} h ago`
}
// a suggested command -> what the button does (null: no button, show the command)
function fixOf(cmd) {
  if (/doctor --fix/.test(cmd)) return { kind: 'fix', label: 'fix the drift', k: 'f' }
  if (/\bsync\b/.test(cmd)) return { kind: 'sync', label: 'open a PR with the shared files', k: 's' }
  return null
}
defineExpose({ load })
</script>

<template>
  <div class="doctor">
    <h2 style="margin-top: 16px">defaults</h2>
    <ErrorNote v-if="error" :error="error" what="couldn't check this repo" />
    <div v-else-if="!result" class="dim">checking…</div>
    <template v-else>
      <div class="head">
        <span v-if="result.error" />
        <span v-else-if="result.ok" class="ok">✓ matches the defaults</span>
        <span v-else class="warn">● {{ result.problems.length }} issue{{ result.problems.length === 1 ? '' : 's' }}</span>
        <span v-if="result.where" class="dim">{{ result.where }}</span>
        <span v-if="result.reference" class="dim">reference repo</span>
        <span class="spacer" />
        <span class="dim">checked {{ ago(result.checked) }}</span>
        <button :disabled="busy" @click="load(true)">{{ busy ? 'checking…' : 'check again' }}</button>
      </div>
      <ul v-if="result.problems.length" class="problems">
        <li v-for="p in result.problems" :key="p">{{ p }}</li>
      </ul>
      <ErrorNote v-if="result.error" :error="result.error" what="couldn't check this repo" />
      <div v-if="result.fixes?.length" class="row fixes">
        <template v-for="f in result.fixes" :key="f">
          <button v-if="fixOf(f)" :title="f" @click="emit('run', fixOf(f).kind)"><span class="k">{{ fixOf(f).k }}</span> {{ fixOf(f).label }}</button>
          <span v-else class="dim fix">{{ f }}</span>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
.head { display: flex; gap: 1.5ch; align-items: center; flex-wrap: wrap; }
.head .spacer { flex: 1; }
.problems { margin: 6px 0; padding-left: 2ch; }
.problems li { margin: 2px 0; overflow-wrap: anywhere; }
.fix { overflow-wrap: anywhere; }
.fixes { margin-top: 6px; }
</style>
