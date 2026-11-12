<script setup>
// A repo's branch rules and its own mason files. Where its rules come from, layer by layer (your defaults,
// the org's .mason, its own .mason.toml or .mason/ folder), what protects its default branch now, and editors
// that write the files back: the protect form, the files themselves (.mason/mason.toml, .mason/rulesets/*.json),
// and "keep the live rulesets" (.mason/rulesets from what GitHub has). Saving opens a PR, or pushes straight to
// the default branch when the repo has auto_push (or you pick "commit"). An org's .mason repo shows its
// mason.toml and rulesets folder instead.
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { forget } from '../load.js'
import { get, log, post, put, qs, state } from '../api.js'
import { ask } from '../ui.js'
import ErrorNote from './ErrorNote.vue'
import RulesetForm from './RulesetForm.vue'

const props = defineProps({ repo: { type: String, required: true } })
const emit = defineEmits(['done'])
const data = ref(null)
const error = ref('')
const mode = ref('auto')
const editing = ref(false) // the protect form
const form = ref({})
const file = ref(null) // {path, text, original, problems, editable, isNew}
const BOOLS = [['signed_commits', 'signed commits'], ['linear_history', 'linear history'], ['code_owners', 'code owner review'],
  ['resolve_threads', 'resolve threads'], ['dismiss_stale', 'dismiss stale reviews'], ['up_to_date', 'branch up to date'],
  ['last_push_approval', 'approve the last push'], ['merge_queue', 'merge queue']]

async function load() {
  error.value = ''
  try { data.value = await get(`/mason${qs({ repo: props.repo })}`) } catch (e) { error.value = e.message; data.value = null }
}
watch(() => props.repo, () => { data.value = null; editing.value = false; file.value = null; load() }, { immediate: true })

const org = computed(() => data.value?.kind === 'org')
const github = computed(() => data.value?.provider === 'github')
function summary(p) {
  if (p === null || p === undefined) return '—'
  if (p === false || p?.enabled === false) return 'off'
  const parts = Object.entries(p).filter(([k]) => k !== 'enabled').map(([k, v]) =>
    v === true ? k.replace(/_/g, ' ') : `${k.replace(/_/g, ' ')} ${Array.isArray(v) ? v.join(', ') : typeof v === 'object' ? 'custom' : v}`)
  return parts.join(' · ') || 'on (no extra rules)'
}
const status = computed(() => {
  const d = data.value
  if (!d || org.value || !github.value) return null
  if (d.live_error) return { cls: 'dim', text: `couldn't read the live rules: ${d.live_error}` }
  if (d.protected_by?.length) return { cls: 'ok', text: `✓ ${d.default_branch} is protected (${d.protected_by.join(', ')})` }
  return { cls: 'bad', text: `✗ ${d.default_branch} isn't protected` }
})
const where = computed(() => (mode.value === 'auto' ? (data.value?.auto_push ? 'straight to the default branch (auto_push)' : 'in a pull request')
  : mode.value === 'pr' ? 'in a pull request' : 'straight to the default branch'))

// a write: ask (y / d dry run / n), then send it with dry_run
async function send(question, method, path, body) {
  const a = await ask(question, { detail: state.dryRun ? 'dry run is on: nothing changes' : `Writes ${where.value}.` })
  if (!a) return null
  const dry = a === 'dry'
  try {
    const got = await method(path, { ...body, mode: mode.value, dry_run: dry })
    if (!dry) { forget('/doctor'); forget('/repo') }
    log(`${dry ? '[dry-run] ' : ''}${question.replace(/\?$/, '')}: done`, 'ok', { detail: got.text })
    emit('done', { text: got.text, ok: true })
    if (!dry) await load()
    return got
  } catch (e) {
    const text = e.message
    log(`${question.replace(/\?$/, '')}: ${text}`, 'error')
    emit('done', { text: `error: ${text}`, ok: false })
    return null
  }
}

// ── protect ──
function editProtect() {
  const own = data.value?.own?.protect
  const base = own && typeof own === 'object' ? own : data.value?.protect || {}
  form.value = { reviews: base.reviews ?? '', checks: (base.checks || []).join?.(', ') ?? base.checks ?? '',
    branches: (base.branches || []).join?.(', ') ?? base.branches ?? '' }
  for (const [k] of BOOLS) form.value[k] = !!base[k]
  editing.value = true
}
async function saveProtect(value) {
  const what = value === false ? `Turn branch protection off in ${props.repo}?` : value === null
    ? `Drop ${props.repo}'s own protect (the groups decide)?` : `Set ${props.repo}'s branch protection?`
  const got = await send(what, post, '/mason/protect', { repo: props.repo, protect: value })
  if (got) editing.value = false
}
const formValue = () => Object.fromEntries(Object.entries(form.value).filter(([, v]) => v !== '' && v !== false))

// ── files ──
const view = ref('form') // a ruleset file: 'form' or 'json'
async function openFile(f) {
  file.value = { ...f, original: f.text, isNew: false }
  view.value = 'form'
}
// mason's own rules only: the repo's .github/rulesets files stop counting (skip = ["github_rulesets"])
async function ignoreGithub(on) {
  await send(on ? `Let ${props.repo} ignore its .github/rulesets files (mason's rules count)?`
    : `Check ${props.repo}'s .github/rulesets files again?`, post, '/mason/skip', { repo: props.repo, check: 'github_rulesets', on })
}
async function moveGithub(paths, remove) {
  const names = paths.map((p) => p.split('/').pop()).join(', ')
  const got = await send(remove ? `Remove ${names} from ${props.repo}'s .github/rulesets?`
    : `Move ${names} from .github/rulesets to .mason/rulesets in ${props.repo}?`, post, '/mason/move', { repo: props.repo, paths, remove })
  if (got && !got.dry && file.value && paths.includes(file.value.path)) file.value = null
}
const githubFiles = computed(() => (data.value?.files || []).filter((f) => f.path.startsWith('.github/')))
async function newFile(kind) {
  if (kind === 'settings') {
    file.value = { path: '.mason/mason.toml', text: '# this repo\'s own mason settings: they win over every group\n[protect]\nreviews = 1\n', original: '', problems: [], editable: true, isNew: true }
    return
  }
  const name = await ask('Name of the ruleset file', { input: { placeholder: 'main' }, allowDry: false })
  if (!name) return
  const slug = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'ruleset'
  const path = org.value ? `rulesets/default/${slug}.json` : `.mason/rulesets/${slug}.json`
  const rs = { name: name.trim(), target: 'branch', enforcement: 'active', conditions: { ref_name: { include: ['~DEFAULT_BRANCH'], exclude: [] } },
    rules: [{ type: 'deletion' }, { type: 'non_fast_forward' }, { type: 'pull_request', parameters: { required_approving_review_count: 1 } }] }
  file.value = { path, text: `${JSON.stringify(rs, null, 2)}\n`, original: '', problems: [], editable: true, isNew: true }
}
async function check() {
  if (!file.value) return
  try { file.value.problems = (await post('/mason/validate', { repo: props.repo, path: file.value.path, text: file.value.text })).problems } catch (e) { file.value.problems = [e.message] }
}
async function saveFile(remove = false) {
  const f = file.value
  if (!remove) {
    await check()
    if (f.problems.length && !(await ask(`${f.path} has problems. Save it anyway?`, { allowDry: false, detail: f.problems.join('\n') }))) return
  }
  const got = await send(`${remove ? 'Remove' : 'Save'} ${f.path} in ${props.repo}?`, put, '/mason/file',
    { repo: props.repo, path: f.path, text: f.text, delete: remove, force: true })
  if (got && !got.dry) file.value = null
}
async function keepLive() {
  await send(`Keep ${props.repo}'s live rulesets (${data.value.live_rulesets.join(', ')}) in .mason/rulesets?`, post, '/mason/save-live', { repo: props.repo })
}
function tab(e) {
  if (e.key !== 'Tab') return
  e.preventDefault()
  const el = e.target
  const [s, end] = [el.selectionStart, el.selectionEnd]
  file.value.text = file.value.text.slice(0, s) + '  ' + file.value.text.slice(end)
  requestAnimationFrame(() => { el.selectionStart = el.selectionEnd = s + 2 })
}
const link = (r) => ({ path: '/repo', query: { repo: r } })
defineExpose({ load })
</script>

<template>
  <div class="mason">
    <h2 style="margin-top: 16px">{{ org ? 'org defaults (.mason)' : 'branch rules' }}</h2>
    <ErrorNote v-if="error" :error="error" what="couldn't read the mason files" />
    <div v-else-if="!data" class="dim">reading…</div>
    <template v-else>
      <div v-if="status" :class="status.cls">{{ status.text }}</div>
      <template v-if="!org">
        <div class="layers">
          <div class="dim">rules come from, least important first:</div>
          <div v-for="(l, i) in data.layers" :key="i" class="layer">
            <span class="src">
              <RouterLink v-if="l.repo && l.repo !== repo && l.repo.endsWith('/.mason')" :to="link(l.repo)">{{ l.source }}</RouterLink>
              <span v-else>{{ l.source }}</span>
              <span v-if="l.group && l.group !== '.mason.toml'" class="dim">({{ l.group }})</span>
              <span v-if="l.file" class="dim">{{ l.file }}</span>
            </span>
            <span :class="l.protect ? '' : 'dim'">protect: {{ summary(l.protect) }}</span>
            <span v-if="l.rulesets?.length" class="dim">rulesets: {{ l.rulesets.join(', ') }}</span>
            <span v-if="l.skip?.includes('protect')" class="warn">skips protect</span>
          </div>
        </div>
        <div class="row" style="margin-top: 6px">
          <span>in effect:</span>
          <span v-if="data.protect_skipped" class="warn">skipped</span>
          <span v-else :class="data.protect ? 'accent' : 'dim'">{{ data.protect ? summary(data.protect) : 'no protect' }}</span>
          <span v-if="data.protect_from && data.protect" class="dim">(last set by {{ data.protect_from }})</span>
        </div>
      </template>

      <div class="row" style="margin-top: 8px">
        <select v-model="mode" aria-label="how to write">
          <option value="auto">{{ data.auto_push ? 'push (auto_push)' : 'as a pull request' }}{{ org ? '' : ' — the repo decides' }}</option>
          <option value="pr">as a pull request</option>
          <option value="commit">commit directly</option>
        </select>
        <button v-if="!org && !editing" @click="editProtect">edit protection</button>
        <button v-if="!org" @click="newFile('settings')" :disabled="!!data.settings_file">new .mason/mason.toml</button>
        <button v-if="github || org" @click="newFile('ruleset')">new ruleset file</button>
        <button v-if="!org && github && data.live_rulesets?.length" @click="keepLive">keep live rulesets in .mason</button>
      </div>

      <div v-if="editing" class="box protect">
        <div class="dim">This repo's own protect, on top of its groups' (the repo wins key by key). Saved in
          {{ data.settings_file || '.mason/mason.toml' }}.</div>
        <label>reviews <input v-model="form.reviews" type="number" min="0" max="10" style="width: 6ch"></label>
        <label>checks <input v-model="form.checks" placeholder="test, lint"></label>
        <label v-if="github">branches <input v-model="form.branches" placeholder="default branch"></label>
        <div v-if="github" class="bools">
          <label v-for="[k, label] in BOOLS" :key="k"><input v-model="form[k]" type="checkbox"> {{ label }}</label>
        </div>
        <div class="row">
          <button class="primary" @click="saveProtect(formValue())">save</button>
          <button class="danger" @click="saveProtect(false)">off in this repo</button>
          <button v-if="data.own?.protect !== null && data.own?.protect !== undefined" @click="saveProtect(null)">use the groups'</button>
          <button @click="editing = false">cancel</button>
        </div>
      </div>

      <div class="files">
        <div class="dim">{{ org ? 'files' : 'its files' }}{{ data.files.length ? '' : ': none yet' }}</div>
        <div v-for="f in data.files" :key="f.path" class="row">
          <a href="#" @click.prevent="openFile(f)">{{ f.path }}</a>
          <span v-if="f.ignored" class="dim">(ignored: mason's rules count)</span>
          <template v-if="f.path.startsWith('.github/')">
            <button title="the same file in .mason/rulesets, and the .github one removed" @click="moveGithub([f.path], false)">move to .mason</button>
            <button class="danger" @click="moveGithub([f.path], true)">remove</button>
          </template>
          <span v-if="f.problems?.length" class="warn">{{ f.problems.length }} problem{{ f.problems.length === 1 ? '' : 's' }}</span>
        </div>
      </div>

      <div v-if="githubFiles.length > 1" class="row" style="margin-top: 6px">
        <button @click="moveGithub(githubFiles.map((f) => f.path), false)">move all of .github/rulesets to .mason</button>
      </div>
      <label v-if="!org && github && (githubFiles.length || data.github_rulesets_ignored)" class="check" style="margin-top: 6px">
        <input type="checkbox" :checked="data.github_rulesets_ignored" @change="ignoreGithub($event.target.checked)">
        ignore .github/rulesets: mason's rules (defaults, org .mason, .mason/rulesets) are the ones that count
      </label>

      <div v-if="file" class="box">
        <div class="row">
          <span class="accent">{{ file.path }}</span>
          <span v-if="file.text !== file.original" class="warn">[modified]</span>
          <span class="spacer" style="flex: 1" />
          <template v-if="file.editable">
            <button @click="check">validate</button>
            <button class="primary" @click="saveFile()">save</button>
            <button v-if="!file.isNew" class="danger" @click="saveFile(true)">remove</button>
          </template>
          <button @click="file = null">close</button>
        </div>
        <div v-if="file.path.endsWith('.json')" class="row tabs">
          <button :class="{ primary: view === 'form' }" @click="view = 'form'">form</button>
          <button :class="{ primary: view === 'json' }" @click="view = 'json'">JSON</button>
        </div>
        <RulesetForm v-if="file.path.endsWith('.json') && view === 'form'" v-model="file.text" />
        <textarea v-else v-model="file.text" class="editor" spellcheck="false" :readonly="!file.editable" :aria-label="file.path"
                  @keydown="tab" @blur="file.editable && check()" />
        <div v-for="(p, i) in file.problems" :key="i" class="bad">- {{ p }}</div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.layer { display: flex; gap: 1.5ch; flex-wrap: wrap; margin: 2px 0 2px 2ch; overflow-wrap: anywhere; }
.layer .src { min-width: 18ch; }
.protect label { display: inline-flex; gap: .8ch; align-items: center; margin: 6px 2ch 0 0; }
.protect input:not([type="checkbox"]) { min-width: 6ch; }
.protect .bools { margin: 4px 0 8px; }
.protect .row { margin-top: 8px; }
.layer .src > * + * { margin-left: 1ch; }
.files { margin-top: 8px; }
.box { margin-top: 8px; }
.box textarea.editor { min-height: 30vh; }
.tabs { margin-top: 6px; }
</style>
