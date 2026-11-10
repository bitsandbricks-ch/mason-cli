<script setup>
// Each repo's latest release, its assets, missing assets and the last release run, and its version file against
// that release: "0.4.0 unreleased" when the version changed but nothing is released yet (u lists only those).
// Enter opens the repo's releases as a page; n creates a release; b bumps the selected repo in a PR, R releases it.
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { get, log } from '../api.js'
import { useLoad } from '../load.js'
import { useKeys } from '../keys.js'
import { loadGroups, scope } from '../scope.js'
import DataTable from '../components/DataTable.vue'
import ReleaseForm from '../components/ReleaseForm.vue'
import Scope from '../components/Scope.vue'
import TextPane from '../components/TextPane.vue'
import VersionBar from '../components/VersionBar.vue'
import { openDetail } from '../ui.js'

const router = useRouter()
const problems = ref(false)
const unreleased = ref(false)
const { data, loading, load } = useLoad((q) => {
  const extra = [problems.value && 'problems=1', unreleased.value && 'unreleased=1'].filter(Boolean).join('&')
  return `/releases${q}${extra ? (q ? '&' : '?') + extra : ''}`
})
loadGroups()
const sel = ref(null)
const form = ref('') // '', 'release' or 'tag'
const output = ref('')
const repoNames = ref([])
const rows = computed(() => (data.value?.releases || []).map((r) => ({ ...r, issues: r.problems.join('; ') || 'ok' })))
const columns = [
  { key: 'repo', label: 'repo', cls: (r) => (r.provider === 'gitlab' ? 'warn' : '') },
  { key: 'release', label: 'release', cls: () => '' },
  { key: 'pending', label: 'version', cls: (r) => (r.version?.todo ? 'warn' : r.version?.pr ? 'accent' : 'dim') }, { key: 'when', label: 'when', cls: () => 'dim' },
  { key: 'assets', label: 'assets' }, { key: 'run', label: 'release run' }, { key: 'issues', label: 'problems' },
]
const current = computed(() => rows.value.find((r) => r.repo === sel.value))
const toggle = () => { problems.value = !problems.value; load() }
const toggleUnreleased = () => { unreleased.value = !unreleased.value; load() }
const page = (r) => { const repo = r?.repo || sel.value; if (repo) router.push({ path: '/release', query: { repo } }) }
async function newRelease(mode = 'release') {
  form.value = mode
  openDetail()
  output.value = ''
  if (!repoNames.value.length) {
    try { repoNames.value = (await get('/repos')).repos.map((r) => r.repo) } catch (e) { log(e.message, 'error') }
  }
}
function done({ text, ok }) { output.value = text; if (ok) { form.value = ''; load(true) } }
useKeys({ r: () => load(true), p: toggle, u: toggleUnreleased, n: () => newRelease('release'), T: () => newRelease('tag'), Escape: () => { form.value = '' },
  o: () => current.value?.url && window.open(current.value.url, '_blank', 'noopener') })
</script>

<template>
  <div class="view">
    <div class="toolbar">
      <Scope :groups="scope.groups" />
      <label class="check"><input :checked="problems" type="checkbox" @change="toggle"> only problems <span class="dim k">(p)</span></label>
      <label class="check"><input :checked="unreleased" type="checkbox" @change="toggleUnreleased"> only unreleased
        <span class="dim k">(u)</span><span v-if="data?.unreleased" class="warn"> {{ data.unreleased }}</span></label>
      <span class="spacer" />
      <button class="primary any" @click="newRelease('release')"><span class="k">n</span> new release</button>
      <button class="any" @click="newRelease('tag')"><span class="k">T</span> new tag</button>
      <button :disabled="!sel" @click="page()"><span class="k">⏎</span> releases of the repo</button>
    </div>
    <div class="split ld">
      <div><DataTable v-model="sel" :columns="columns" :rows="rows" :row-key="(r) => r.repo" :empty="loading ? 'loading…' : 'no releases'" @activate="page" /></div>
      <div class="pad">
        <VersionBar v-if="current?.version && !form" :key="current.repo" :repo="current.repo" :version="current.version" @done="done" />
        <ReleaseForm v-if="form" :key="form" :mode="form" :repo="sel || ''" :repos="repoNames" @done="done" @cancel="form = ''" />
        <template v-if="output"><h2>output</h2><TextPane :text="output" /></template>
        <TextPane v-if="!form" :text="current?.text" placeholder="pick a repo; Enter shows all its releases" />
      </div>
    </div>
  </div>
</template>
