<script setup>
// A repo's branches: the default first, then the newest commit first. Each says how far it is ahead of and behind
// the default branch, whether it is merged, what protects it, and the newest PR (or MR) from it. A branch that
// isn't the default or protected can be deleted (asked first; a dry run says what would go); "delete the merged
// ones" takes every merged branch that may go. A branch with an open PR may go too: the question says the PR closes.
import { computed, ref, watch } from 'vue'
import { get, qs, state as app } from '../api.js'
import { change } from '../load.js'
import { stateClass } from '../ui.js'
import ErrorNote from './ErrorNote.vue'

const props = defineProps({ repo: { type: String, required: true } })
const emit = defineEmits(['done'])
const data = ref(null)
const error = ref('')
const filter = ref('')
const all = ref(false)
const busy = ref(false)
const SHOWN = 12

const gitlab = computed(() => props.repo.startsWith('gitlab:'))
const mark = computed(() => (gitlab.value ? '!' : '#'))
async function load() {
  error.value = ''
  try { data.value = await get(`/repo/branches${qs({ repo: props.repo })}`) } catch (e) { error.value = e.message; data.value = null }
}
watch(() => props.repo, () => { data.value = null; filter.value = ''; all.value = false; load() }, { immediate: true })

const rows = computed(() => data.value?.branches || [])
const q = computed(() => filter.value.trim().toLowerCase())
const found = computed(() => rows.value.filter((r) => !q.value || `${r.name} ${r.author} ${r.pr?.title || ''}`.toLowerCase().includes(q.value)))
const shown = computed(() => (all.value || q.value ? found.value : found.value.slice(0, SHOWN)))
const merged = computed(() => rows.value.filter((r) => r.merged && r.deletable))
const open = (r) => r.pr && (r.pr.state === 'open' || r.pr.state === 'draft')

function state(r) {
  if (r.default) return { text: 'default', cls: 'chip on' }
  if (r.merged) return { text: 'merged', cls: 'ok' }
  if (r.ahead === null || r.ahead === undefined) return { text: '', cls: '' }
  return { text: `+${r.ahead} −${r.behind}`, cls: 'dim', title: `${r.ahead} commit${r.ahead === 1 ? '' : 's'} not in ${data.value.default}, ${r.behind} behind it` }
}

async function remove(list, merging = false) {
  const names = list.map((r) => r.name)
  const closing = list.filter(open).map((r) => `${r.name}: its open ${gitlab.value ? 'MR' : 'PR'} ${mark.value}${r.pr.number} closes`)
  const what = merging ? `the ${names.length} merged branch${names.length === 1 ? '' : 'es'}` : names.length === 1 ? `the branch ${names[0]}` : `${names.length} branches`
  busy.value = true
  try {
    const got = await change(`Delete ${what} of ${props.repo}?`, '/repo/branches/delete',
      { repo: props.repo, branches: merging ? [] : names, merged: merging },
      { detail: [app.dryRun ? 'dry run is on: nothing changes' : '', merging ? names.join('\n') : '', ...closing,
        gitlab.value ? 'A deleted branch comes back only from a clone that still has it.'
          : 'GitHub can restore a deleted branch from its closed PR; otherwise only a clone that still has it can.']
        .filter(Boolean).join('\n\n') })
    if (got === null) return
    emit('done', got)
    if (!got.dry) await load()
  } finally { busy.value = false }
}
defineExpose({ load })
</script>

<template>
  <div class="branches">
    <h2 style="margin-top: 16px">branches <span v-if="data" class="dim">({{ data.total }})</span></h2>
    <ErrorNote v-if="error" :error="error.replace(/^couldn't read the branches:\s*/i, '')" what="couldn't read the branches" />
    <div v-else-if="!data" class="dim">reading…</div>
    <template v-else>
      <div class="row">
        <input v-model="filter" placeholder="find a branch" aria-label="find a branch" style="flex: 1; min-width: 14ch">
        <button v-if="merged.length" class="danger" :disabled="busy" :title="merged.map((r) => r.name).join(', ')" @click="remove(merged, true)">
          delete the merged ones ({{ merged.length }})</button>
        <a v-if="data.url" :href="data.url" target="_blank" rel="noopener" class="dim hide-xs">on {{ gitlab ? 'GitLab' : 'GitHub' }} ↗</a>
      </div>
      <div v-if="!found.length" class="empty dim">{{ q ? 'no branch matches' : 'no branches' }}</div>
      <div v-for="r in shown" :key="r.name" class="branch">
        <div class="name">
          <a v-if="r.url" :href="r.url" target="_blank" rel="noopener">{{ r.name }}</a><span v-else>{{ r.name }}</span>
          <span v-if="state(r).text" :class="state(r).cls" :title="state(r).title">{{ state(r).text }}</span>
          <span v-if="r.protected.length" class="chip" :title="r.protected.join(', ')">protected</span>
        </div>
        <div class="meta dim">
          <span :title="r.date">{{ r.ago || '-' }}</span>
          <span v-if="r.author">{{ r.author }}</span>
          <span v-if="r.message" class="msg" :title="r.message">{{ r.message }}</span>
        </div>
        <div class="side">
          <router-link v-if="r.pr" :to="{ path: '/pr', query: { repo, number: r.pr.number } }" :title="r.pr.title">
            <span class="dim">{{ mark }}{{ r.pr.number }}</span> <span :class="stateClass(r.pr.state)">{{ r.pr.state }}</span></router-link>
          <button v-if="r.deletable" class="danger" :disabled="busy" :aria-label="`delete ${r.name}`" @click="remove([r])">delete</button>
          <span v-else class="dim" :title="r.default ? 'the default branch stays' : `protected: ${r.protected.join(', ')}`">kept</span>
        </div>
      </div>
      <button v-if="!q && found.length > SHOWN" class="more" @click="all = !all">{{ all ? 'show fewer' : `show all ${found.length}` }}</button>
      <div v-if="data.total > rows.length" class="dim">and {{ data.total - rows.length }} more on {{ gitlab ? 'GitLab' : 'GitHub' }}</div>
    </template>
  </div>
</template>

<style scoped>
.branch { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0 1.5ch; padding: 4px 0; border-bottom: 1px dotted var(--bg3); }
.name { display: flex; gap: 1ch; align-items: center; flex-wrap: wrap; overflow-wrap: anywhere; }
.meta { grid-column: 1; display: flex; gap: 1.5ch; min-width: 0; }
.meta > span:not(.msg) { white-space: nowrap; }
.msg { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.side { grid-column: 2; grid-row: 1 / span 2; display: flex; gap: 1ch; align-items: center; justify-content: flex-end; white-space: nowrap; }
.more { margin-top: 6px; }
.empty { padding: 4px 0; }
</style>
