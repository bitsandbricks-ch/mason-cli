<script setup>
// The handbook the repo follows (mason handbook): its profile, the chapters to read, and what the profile asks
// for (files, labels, agent skills, which doctor and sync hold the repo to). "adopt" opens the one pull request
// that makes a repo follow it (mason adopt): .mason.toml [handbook], AGENTS.md, CLAUDE.md and the skills.
// Shown only when a handbook is named: nothing is built in.
import { ref, watch } from 'vue'
import { forget } from '../load.js'
import { get, log, post, qs, state } from '../api.js'
import { ask } from '../ui.js'
import { working } from '../toast.js'
import ErrorNote from './ErrorNote.vue'

const props = defineProps({ repo: { type: String, required: true } })
const emit = defineEmits(['done'])
const data = ref(null)
const error = ref('')
const adopting = ref(false)
const pick = ref({ profile: '', version: '' })

async function load() {
  error.value = ''
  const asked = props.repo
  try {
    const got = await get(`/mason/handbook${qs({ repo: asked })}`)
    if (asked === props.repo) data.value = got
  } catch (e) { if (asked === props.repo) { error.value = e.message; data.value = null } }
}
watch(() => props.repo, () => { data.value = null; adopting.value = false; load() }, { immediate: true })

function startAdopt() {
  pick.value = { profile: data.value?.profile || data.value?.profiles?.[0] || '', version: data.value?.version || '' }
  adopting.value = true
}
async function adopt() {
  const what = `Make ${props.repo} follow the handbook, profile ${pick.value.profile}?`
  const a = await ask(what, { detail: state.dryRun ? 'dry run is on: nothing changes'
    : 'Opens one pull request: .mason.toml, AGENTS.md, CLAUDE.md and the profile\'s skills.' })
  if (!a) return
  const dry = a === 'dry'
  const busy = working(`${dry ? '[dry-run] ' : ''}adopt the handbook`)
  try {
    const got = await post('/mason/handbook/adopt', { repo: props.repo, ...pick.value, dry_run: dry })
    if (!dry) { forget('/doctor'); forget('/repo') }
    log(`${dry ? '[dry-run] ' : ''}adopt the handbook: done`, 'ok', { detail: got.text, toast: busy.id })
    emit('done', { text: got.text + (got.missing?.length ? `\nstill missing for the profile: ${got.missing.join(', ')}` : ''), ok: true })
    if (!dry) adopting.value = false
  } catch (e) {
    log(`adopt the handbook: ${e.message}`, 'error', { toast: busy.id })
    emit('done', { text: `error: ${e.message}`, ok: false })
  }
}
defineExpose({ load })
</script>

<template>
  <div v-if="error || data?.handbook" class="handbook">
    <h2 style="margin-top: 16px">handbook</h2>
    <ErrorNote v-if="error" :error="error" what="couldn't read the handbook" />
    <template v-else>
      <p>
        <span class="dim">follows</span> {{ data.handbook }}<span v-if="data.version" class="dim"> {{ data.version }}</span>
        <template v-if="data.profile"><span class="dim">, profile</span> <b>{{ data.profile }}</b></template>
        <span v-else class="bad"> · no profile yet</span>
        <span class="dim"> (from {{ data.said }})</span>
      </p>
      <p v-if="data.note" class="dim">{{ data.note }}</p>
      <p v-if="data.description" class="dim">{{ data.description }}</p>
      <ul v-if="data.chapters?.length" class="chapters">
        <li v-for="c in data.chapters" :key="c.path">
          <a :href="c.link" target="_blank" rel="noopener">{{ c.title }}</a> <span class="dim">{{ c.part }}</span>
        </li>
      </ul>
      <p v-if="data.files?.length"><span class="dim">files</span> {{ data.files.join(', ') }}</p>
      <p v-if="data.labels && Object.keys(data.labels).length"><span class="dim">labels</span> {{ Object.keys(data.labels).join(', ') }}</p>
      <p v-if="data.skills?.length"><span class="dim">agent skills</span> {{ data.skills.join(', ') }}</p>
      <div class="row">
        <button v-if="!adopting" @click="startAdopt">{{ data.profile ? 'refresh the handbook files' : 'adopt the handbook' }}</button>
      </div>
      <div v-if="adopting" class="box">
        <label>profile
          <select v-model="pick.profile" aria-label="profile">
            <option v-for="p in data.profiles" :key="p" :value="p">{{ p }}</option>
          </select>
        </label>
        <label>version <input v-model="pick.version" placeholder="v1 (none: default branch)" aria-label="handbook version"></label>
        <div class="row">
          <button class="primary" :disabled="!pick.profile" @click="adopt">open the pull request</button>
          <button @click="adopting = false">cancel</button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.chapters { margin: 4px 0 8px; padding-left: 18px; }
.chapters li { margin: 2px 0; }
.handbook label { display: flex; gap: 8px; align-items: center; margin: 4px 0; }
</style>
