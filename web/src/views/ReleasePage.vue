<script setup>
// One repo's releases as a page (Enter on Releases or on a repo's page): every recent release on the
// left, the picked one in full on the right; n creates a release, Esc goes back. After a release, a tag or a bump,
// and while a release run is going, the page reads the repo again by itself until the run is done.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { qs } from '../api.js'
import { cached, useFollow } from '../load.js'
import { useKeys } from '../keys.js'
import DataTable from '../components/DataTable.vue'
import ReleaseForm from '../components/ReleaseForm.vue'
import TextPane from '../components/TextPane.vue'
import VersionBar from '../components/VersionBar.vue'
import { openDetail } from '../ui.js'

const route = useRoute()
const router = useRouter()
const repo = computed(() => String(route.query.repo || ''))
const page = ref(null)
const text = ref('')
const sel = ref(null)
const output = ref('')
const form = ref('') // '', 'release' or 'tag'
const loading = ref(false)
let waitFor = '' // a tag just made: picked once its release shows (see refresh)

async function load(tag = '', fresh = false) {
  if (!repo.value) return
  loading.value = true
  try {
    const got = await cached(`/release${qs({ repo: repo.value, tag, fresh })}`, fresh)
    if (!tag) page.value = got
    text.value = got.text
    sel.value = got.selected || null
  } catch (e) { text.value = `error: ${e.message}` } finally { loading.value = false }
}
watch(repo, () => { page.value = null; form.value = ''; output.value = ''; waitFor = ''; load(String(route.query.tag || '')) }, { immediate: true })
watch(sel, (tag, before) => { if (tag && before && tag !== before) { router.replace({ query: { ...route.query, tag } }); load(tag) } })

const rows = computed(() => page.value?.releases || [])
const columns = [
  { key: 'tag', label: 'tag', cls: () => 'accent' }, { key: 'title', label: 'title', cls: () => '' },
  { key: 'state', label: 'state' }, { key: 'when', label: 'when', cls: () => 'dim' },
  { key: 'assets', label: 'assets', right: true },
]
const current = computed(() => rows.value.find((r) => r.tag === sel.value))
const open = () => { const url = current.value?.url || page.value?.url; if (url) window.open(url, '_blank', 'noopener') }
const back = () => (window.history.state?.back ? router.back() : router.push('/releases'))

// A follow-up: the list, the version and whether a release run is going; the text when it is the shown release's.
async function refresh() {
  const name = repo.value
  const got = await cached(`/release${qs({ repo: name, fresh: true })}`, true, { quiet: true })
  if (name !== repo.value) return
  page.value = got
  if (waitFor && got.releases?.some((r) => r.tag === waitFor)) {
    const tag = waitFor
    waitFor = ''
    if (tag === got.selected) { sel.value = tag; text.value = got.text } else sel.value = tag
  } else if (!sel.value || sel.value === got.selected) {
    sel.value = got.selected || null
    text.value = got.text
  }
}
const follow = useFollow({ pending: () => (page.value?.busy || waitFor ? [repo.value] : []), refresh })
function done({ text: t, tag, ok }) {
  output.value = t
  if (!ok) return
  form.value = ''
  waitFor = tag || ''
  follow.now([repo.value])
}
useKeys({ Escape: () => (form.value ? (form.value = '') : back()), Backspace: back, n: () => { form.value = 'release' }, T: () => { form.value = 'tag' },
  o: open, r: () => load(sel.value || '', true) })
</script>

<template>
  <div class="view">
    <div class="toolbar">
      <button class="hide-xs" @click="back"><span class="k">esc</span> back</button>
      <span class="accent hide-xs">releases › {{ repo }}</span>
      <span class="spacer" />
      <button class="any" @click="load(sel || '', true)"><span class="k">r</span> reload</button>
      <button class="primary any" @click="form = 'release'; openDetail()"><span class="k">n</span> new release</button>
      <button class="any" @click="form = 'tag'; openDetail()"><span class="k">T</span> new tag</button>
      <button :disabled="!page" @click="open"><span class="k">o</span> open</button>
      <router-link class="chip any" :to="{ path: '/repo', query: { repo } }">repo page</router-link>
    </div>
    <div class="split ld">
      <div><DataTable v-model="sel" :columns="columns" :rows="rows" :row-key="(r) => r.tag"
                      :empty="loading ? 'loading…' : 'no releases yet: n creates the first'" @activate="open" /></div>
      <div class="pad">
        <VersionBar v-if="page?.version" :repo="repo" :version="page.version" @done="done" />
        <ReleaseForm v-if="form" :key="form" :mode="form" :repo="repo" :suggest="page?.suggest" :publishes="page?.publishes"
                     @done="done" @cancel="form = ''" />
        <template v-if="output"><h2>output</h2><TextPane :text="output" /></template>
        <TextPane v-if="!form" :text="text" :placeholder="loading ? 'loading…' : 'pick a release'" />
      </div>
    </div>
  </div>
</template>
