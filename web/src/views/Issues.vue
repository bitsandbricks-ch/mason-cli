<script setup>
// Issues across GitHub repos and GitLab projects: filter by state, label, mine and age; open, close,
// reopen and comment; n opens a new issue in any repo. Enter (or page) opens one as its own page.
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { get, log, post, qs, state } from '../api.js'
import { act, change, forget, useLoad } from '../load.js'
import { alive } from '../pick.js'
import { useKeys } from '../keys.js'
import { loadGroups, scope, scopedRepos } from '../scope.js'
import { ago, ask, openDetail } from '../ui.js'
import EventLog from '../components/EventLog.vue'
import DataTable from '../components/DataTable.vue'
import Scope from '../components/Scope.vue'
import TextPane from '../components/TextPane.vue'
import { sideOpen, useSide, useTrack } from '../side.js'
import { openOut } from '../links.js'
import { useUnsaved } from '../unsaved.js'

const STATES = { open: 'open', closed: 'closed', all: 'all' }
const f = reactive({ state: 'open', mine: false, label: '', stale: 0 })
function issuesUrl(q) {
  const extra = qs({ state: f.state, mine: f.mine, label: f.label, stale: f.stale || '' }).slice(1)
  return `/issues${q || (extra ? '?' : '')}${q && extra ? '&' : ''}${extra}`
}
const { data, error, loading, load } = useLoad((q) => issuesUrl(q))
watch(f, () => load())
loadGroups()
const sel = ref(null)
const detail = ref('')
const keyOf = (i) => `${i.repo}#${i.number}`
const rows = computed(() => (data.value?.issues || []).map((i) => ({
  ...i, tags: i.labels.join(', '), who: i.assignees.map((a) => `@${a}`).join(' '), when: ago(i.updated),
})))
const columns = [
  { key: 'repo', label: 'repo', cls: (r) => (r.provider === 'gitlab' ? 'warn' : '') },
  { key: 'number', label: '#', right: true, fmt: (v) => `#${v}`, card: 'head' },
  { key: 'title', label: 'title', cls: () => '', card: 'main' },
  { key: 'tags', label: 'labels', cls: () => 'accent' },
  { key: 'who', label: 'assigned', cls: () => 'dim' },
  { key: 'state', label: 'state', cls: (r) => (r.state === 'open' ? 'ok' : 'dim') },
  { key: 'when', label: 'updated', cls: () => 'dim' },
]
const current = computed(() => rows.value.find((i) => keyOf(i) === sel.value))

async function show() {
  const i = current.value
  if (!i || form.open) return
  detail.value = '…'
  // the side panel shows it (and the preview is hidden): don't ask twice; shown again when the panel closes
  if (sideOpen.value) { detail.value = ''; return }
  try {
    const text = (await get(`/issue${qs({ repo: i.repo, number: i.number })}`)).text
    if (current.value === i) detail.value = text // an older answer after you moved on is dropped
  } catch (e) { if (current.value === i) detail.value = `error: ${e.message}` }
}
watch([sel, sideOpen], show)

// several issues at once: space or the boxes pick them, and c / u close or reopen the picked ones
const picked = ref([])
watch(rows, (list) => { picked.value = alive(picked.value, list.map(keyOf)) })
const pickedRows = computed(() => rows.value.filter((i) => picked.value.includes(keyOf(i))))
async function setPicked(close) {
  const list = pickedRows.value.filter((i) => (close ? i.state === 'open' : i.state !== 'open'))
  if (!list.length) { log(`none of the picked issues is ${close ? 'open' : 'closed'}`, 'warn'); return }
  const verb = close ? 'Close' : 'Reopen'
  const a = await ask(`${verb} ${list.length} issue${list.length === 1 ? '' : 's'}?`, {
    detail: [state.dryRun ? 'dry run is on: nothing changes\n' : '', ...list.map((i) => `${keyOf(i)} ${i.title}`)].join('\n').trim() })
  if (!a) return
  const dry = a === 'dry'
  const out = []
  let failed = 0
  for (const i of list) { // one at a time: each is its own call, and one that fails doesn't stop the rest
    try { out.push((await post('/issue', { repo: i.repo, number: i.number, action: close ? 'close' : 'reopen', dry_run: dry })).text) } catch (e) { failed++; out.push(`${keyOf(i)}: error: ${e.message}`) }
  }
  detail.value = out.join('\n')
  log(`${dry ? '[dry-run] ' : ''}${verb} ${list.length} issues: ${failed ? `${failed} failed` : 'done'}`, failed ? 'error' : 'ok', { detail: detail.value })
  if (!dry) { picked.value = []; forget('/issues'); load(true) }
}

async function setState(close) {
  if (picked.value.length) return setPicked(close)
  const i = current.value
  if (!i || (close ? i.state !== 'open' : i.state === 'open')) return
  const text = await act(`${close ? 'Close' : 'Reopen'} ${keyOf(i)} ${i.title}?`, '/issue', { repo: i.repo, number: i.number, action: close ? 'close' : 'reopen' })
  if (text !== null) { detail.value = text; load(true) }
}
async function comment() {
  const i = current.value
  if (!i) return
  const said = await ask(`Comment on ${keyOf(i)}`, { input: { placeholder: 'your comment' }, allowDry: false })
  if (!said?.trim()) return
  const text = await act(`Post the comment on ${keyOf(i)}?`, '/issue', { repo: i.repo, number: i.number, action: 'comment', text: said }, { detail: said })
  if (text !== null) { detail.value = text; show() }
}

// the new-issue form
const form = reactive({ open: false, repo: '', title: '', body: '', labels: '', assignees: '' })
const typed = () => form.open && !!(form.title.trim() || form.body.trim())
useUnsaved(typed, 'the new issue')
async function cancelNew() {
  if (typed() && !(await ask('Drop the new issue?', { allowDry: false }))) return
  Object.assign(form, { open: false, title: '', body: '' })
  show()
}
const repoNames = ref([]) // the picker's repos: those of the filter, read again when it changes
watch(() => [scope.provider, scope.group], () => { repoNames.value = [] })
const side = useSide()
async function newIssue() {
  form.open = true
  side.close() // the form shows where the panel would cover it
  openDetail()
  if (!form.repo && current.value) form.repo = current.value.repo
  if (!repoNames.value.length) {
    try { repoNames.value = await scopedRepos() } catch (e) { log(e.message, 'error') }
  }
}
const split = (s) => s.split(',').map((x) => x.trim()).filter(Boolean)
async function submit() {
  if (!form.repo || !form.title.trim()) { log('a repo and a title, please', 'warn'); return }
  const got = await change(`Open an issue in ${form.repo}: ${form.title}?`, '/issues', {
    repo: form.repo, title: form.title, body: form.body, labels: split(form.labels), assignees: split(form.assignees),
  })
  if (!got) return
  detail.value = got.text
  // a dry run keeps what was typed
  if (got.ok && !got.dry) { Object.assign(form, { open: false, title: '', body: '', labels: '', assignees: '' }); load(true) }
}
const open = () => openOut(current.value?.url)
const router = useRouter()
useTrack(() => current.value && { kind: 'issue', repo: current.value.repo, number: current.value.number },
  { sel, kind: 'issue', key: (t) => (t.kind === 'issue' ? `${t.repo}#${t.number}` : null) })
const page = (i) => { const r = i || current.value; if (r) router.push({ path: '/issue', query: { repo: r.repo, number: r.number } }) }
const cycle = () => { const k = Object.keys(STATES); f.state = k[(k.indexOf(f.state) + 1) % k.length] }
useKeys({ r: () => load(true), n: newIssue, c: () => setState(true), u: () => setState(false), m: comment, o: open, p: () => page(), v: cycle, i: () => { f.mine = !f.mine } })
</script>

<template>
  <div class="view">
    <div class="toolbar">
      <Scope :groups="scope.groups" />
      <span class="row"><button v-for="(l, k) in STATES" :key="k" class="chip" :class="{ on: f.state === k }" @click="f.state = k">{{ l }}</button></span>
      <button class="chip" :class="{ on: f.mine }" @click="f.mine = !f.mine"><span class="k">i</span> mine</button>
      <select v-model="f.label" aria-label="label"><option value="">any label</option><option v-for="l in data?.labels || []" :key="l" :value="l">{{ l }}</option></select>
      <select v-model.number="f.stale" aria-label="age"><option :value="0">any age</option><option :value="30">untouched 30d</option><option :value="90">untouched 90d</option></select>
      <span class="spacer" />
      <button class="primary any" @click="newIssue"><span class="k">n</span> new</button>
      <button :disabled="!current" @click="comment"><span class="k">m</span> comment</button>
      <button :disabled="!picked.length && current?.state !== 'open'" @click="setState(true)"><span class="k">c</span> close</button>
      <button :disabled="!picked.length && (!current || current.state === 'open')" @click="setState(false)"><span class="k">u</span> reopen</button>
      <button :disabled="!current" @click="open"><span class="k">o</span> open</button>
      <button class="any" :disabled="!current" @click="page()"><span class="k">p</span> page</button>
    </div>
    <div v-if="picked.length" class="picked-bar" role="status">
      <span><b>{{ picked.length }}</b> picked</span>
      <button @click="setPicked(true)"><span class="k">c</span> close them</button>
      <button @click="setPicked(false)"><span class="k">u</span> reopen them</button>
      <button @click="picked = []">clear</button>
      <span class="dim hide-xs">space picks the selected row, shift+click a span</span>
    </div>
    <div class="split ld">
      <div>
        <details v-if="data?.failed?.length" class="pad warn"><summary>{{ data.failed.length }} repo{{ data.failed.length === 1 ? '' : 's' }} couldn't be read</summary>
          <div v-for="x in data.failed" :key="x" class="dim">{{ x }}</div></details>
        <DataTable v-model="sel" :picked="picked" @update:picked="(v) => (picked = v)" :error="error" :columns="columns" :rows="rows" :row-key="keyOf" :empty="loading ? 'loading…' : 'no open issues'" @activate="page" />
      </div>
      <div class="pad">
        <div v-if="form.open" class="box">
          <div class="form">
            <label>repo</label>
            <input v-model="form.repo" list="issue-repos" placeholder="owner/name or gitlab:group/project">
            <label>title</label><input v-model="form.title" placeholder="what's wrong, or what's wanted" @keydown.enter="submit">
            <label>labels</label><input v-model="form.labels" placeholder="bug, docs">
            <label>assignees</label><input v-model="form.assignees" placeholder="login, login (GitHub)">
          </div>
          <datalist id="issue-repos"><option v-for="r in repoNames" :key="r" :value="r" /></datalist>
          <textarea v-model="form.body" rows="10" placeholder="details (Markdown)" style="margin-top: 8px" />
          <div class="row" style="margin-top: 8px">
            <button class="primary" @click="submit">open issue</button>
            <button @click="cancelNew">cancel</button>
          </div>
        </div>
        <TextPane v-else :text="detail" placeholder="pick an issue; n opens a new one" />
      </div>
    </div>
    <EventLog band :repo="current?.repo || ''" kind="issue" :number="current?.number || ''" :title="current ? `${current.repo}#${current.number} ${current.title}` : ''" />
  </div>
</template>
