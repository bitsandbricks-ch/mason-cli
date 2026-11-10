<script setup>
// A repo's Actions secrets: the names its defaults ask for (the group, the org's .mason, its own .mason.toml),
// set or missing, plus the ones set besides. Typing a value and pressing set sends it once: the server
// encrypts it with the repo's public key for GitHub and keeps nothing. "also in" sends the same value to
// more repos (a token every plugin needs).
import { ref, watch } from 'vue'
import { get, qs } from '../api.js'
import { act } from '../load.js'

const props = defineProps({ repo: { type: String, required: true } })
const emit = defineEmits(['done'])
const rows = ref([])
const error = ref('')
const values = ref({})
const also = ref({})

const id = (r) => `${r.env || ''}/${r.name}`
async function load() {
  error.value = ''
  try { rows.value = (await get(`/repo/secrets${qs({ repo: props.repo })}`)).secrets || [] } catch (e) { error.value = e.message; rows.value = [] }
}
watch(() => props.repo, () => { values.value = {}; also.value = {}; load() }, { immediate: true })

async function save(r) {
  const value = values.value[id(r)] || ''
  if (!value) return
  const more = (also.value[id(r)] || '').split(/[\s,]+/).filter(Boolean)
  const repos = [props.repo, ...more]
  const where = r.env ? `${r.name} (environment ${r.env})` : r.name
  const text = await act(`Set the secret ${where} in ${repos.join(', ')}?`, '/repo/secrets', { repos, name: r.name, env: r.env || undefined, value },
    { detail: 'Encrypted for GitHub with each repo\'s public key. Mason doesn\'t keep it; the audit log names the secret, never its value.' })
  if (text === null) return
  values.value[id(r)] = ''
  emit('done', { text, ok: !text.startsWith('error') })
  load()
}
</script>

<template>
  <div v-if="rows.length || error" class="secrets">
    <h2 style="margin-top: 16px">secrets</h2>
    <div v-if="error" class="bad">{{ error }}</div>
    <div v-for="r in rows" :key="id(r)" class="secret">
      <span :class="r.set ? 'ok' : 'bad'">{{ r.set ? 'set' : 'missing' }}</span>
      <span>{{ r.env ? `${r.env}: ` : '' }}{{ r.name }}<span v-if="!r.wanted" class="dim"> (not in the defaults)</span></span>
      <input v-model="values[id(r)]" type="password" autocomplete="off" :placeholder="r.set ? 'new value' : 'value'" @keydown.enter="save(r)">
      <input v-model="also[id(r)]" class="hide-xs" placeholder="also in: api web" style="min-width: 14ch">
      <button :disabled="!values[id(r)]" @click="save(r)">set</button>
    </div>
  </div>
</template>

<style scoped>
.secret { display: flex; gap: 1ch; align-items: center; flex-wrap: wrap; margin: 4px 0; }
.secret > span:first-child { min-width: 8ch; }
.secret input[type="password"] { flex: 1; min-width: 16ch; }
</style>
