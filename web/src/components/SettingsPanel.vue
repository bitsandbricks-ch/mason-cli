<script setup>
// Every GitHub (or GitLab) setting of the repo, by area: what the API reads, changed in place where the API
// writes it. Changes wait in a bar at the bottom: "apply" sends them to GitHub, "apply and keep" also writes the
// ones doctor knows into the repo's .mason.toml (a PR, or straight on with auto_push), so the repo is held to
// them. "kept" marks a setting the repo's own file names. Lists (webhooks, deploy keys, members, ...) are
// shown with a link to where they're managed.
import { computed, ref, watch } from 'vue'
import { get, log, post, qs, state } from '../api.js'
import { forget } from '../load.js'
import { ask } from '../ui.js'
import ErrorNote from './ErrorNote.vue'

const props = defineProps({ repo: { type: String, required: true } })
const emit = defineEmits(['done'])
const data = ref(null)
const error = ref('')
const edits = ref({}) // key -> new value
const filter = ref('')
const open = ref({}) // area name -> open
const busy = ref(false)

async function load() {
  error.value = ''
  try { data.value = await get(`/repo/settings${qs({ repo: props.repo })}`) } catch (e) { error.value = e.message; data.value = null }
}
watch(() => props.repo, () => { data.value = null; edits.value = {}; open.value = {}; load() }, { immediate: true })

const host = computed(() => (data.value?.provider === 'gitlab' ? 'GitLab' : 'GitHub'))
const show = (v) => (v === null || v === undefined ? '—' : v === true ? 'on' : v === false ? 'off' : Array.isArray(v) ? v.join(', ') || '(none)' : String(v))
const current = (r) => (r.key in edits.value ? edits.value[r.key] : r.value)
const keptAt = (r) => (r.keep && data.value?.kept && r.keep in data.value.kept ? data.value.kept[r.keep] : undefined)
function keptLabel(r) {
  const k = keptAt(r)
  if (k === undefined) return ''
  const want = r.keep.startsWith('security.') ? k === 'enabled' : k
  return JSON.stringify(want) === JSON.stringify(r.value) || (r.kind === 'list' && Array.isArray(k) && k.every((x) => (r.value || []).includes(x)))
    ? 'kept' : `kept as ${show(want)}`
}

const q = computed(() => filter.value.trim().toLowerCase())
const match = (r) => !q.value || `${r.label} ${r.key} ${show(r.value)}`.toLowerCase().includes(q.value)
const areas = computed(() => (data.value?.areas || []).map((a) => ({ ...a, shown: a.rows.filter(match) })).filter((a) => a.shown.length))
const lists = computed(() => (data.value?.lists || []).filter((l) => !q.value || `${l.label} ${l.items.map((i) => i.name).join(' ')}`.toLowerCase().includes(q.value)))
const isOpen = (name) => (q.value ? true : !!open.value[name])
const count = computed(() => (data.value?.areas || []).reduce((n, a) => n + a.rows.length, 0))
const editable = computed(() => (data.value?.areas || []).reduce((n, a) => n + a.rows.filter((r) => r.edit).length, 0))

function set(r, raw) {
  let v = raw
  if (r.kind === 'int') v = raw === '' ? null : Number(raw)
  if (r.kind === 'list') v = String(raw).split(',').map((x) => x.trim()).filter(Boolean)
  const same = JSON.stringify(v) === JSON.stringify(r.value) || (v === '' && r.value === null)
  const next = { ...edits.value }
  if (same || v === null) delete next[r.key]
  else next[r.key] = v
  edits.value = next
}
const pending = computed(() => {
  const rows = (data.value?.areas || []).flatMap((a) => a.rows)
  return Object.entries(edits.value).map(([key, value]) => ({ row: rows.find((r) => r.key === key), value })).filter((p) => p.row)
})
const keepable = computed(() => pending.value.filter((p) => p.row.keep).length)

async function apply(keep) {
  const list = pending.value.map((p) => `${p.row.label}: ${show(p.row.value)} → ${show(p.value)}`).join('\n')
  const extra = keep ? `\n\n${keepable.value} of them also go into ${data.value.file || '.mason/mason.toml'}, so doctor holds the repo to them.` : ''
  const a = await ask(`Change ${pending.value.length} setting${pending.value.length === 1 ? '' : 's'} of ${props.repo} on ${host.value}?`,
    { detail: (state.dryRun ? 'dry run is on: nothing changes\n\n' : '') + list + extra })
  if (!a) return
  busy.value = true
  const dry = a === 'dry'
  try {
    const got = await post('/repo/settings', { repo: props.repo, changes: edits.value, keep, dry_run: dry })
    log(`${dry ? '[dry-run] ' : ''}settings of ${props.repo}: done`, 'ok', { detail: got.text })
    emit('done', { text: got.text, ok: true })
    if (!dry) { edits.value = {}; forget('/doctor'); forget('/repo'); await load() }
  } catch (e) {
    const text = e.message
    log(`settings of ${props.repo}: ${text}`, 'error')
    emit('done', { text: `error: ${text}`, ok: false })
  } finally { busy.value = false }
}
const toggleAll = () => { const all = areas.value.every((a) => open.value[a.name]); open.value = Object.fromEntries(areas.value.map((a) => [a.name, !all])) }
defineExpose({ load })
</script>

<template>
  <div class="settings">
    <h2 style="margin-top: 16px">{{ host === 'GitLab' ? 'project' : 'repo' }} settings
      <span v-if="data" class="dim">({{ editable }} of {{ count }} editable)</span></h2>
    <ErrorNote v-if="error" :error="error" what="couldn't read the settings" />
    <div v-else-if="!data" class="dim">reading…</div>
    <template v-else>
      <div class="row">
        <input v-model="filter" placeholder="find a setting: wiki, squash, pages…" aria-label="find a setting" style="flex: 1; min-width: 18ch">
        <button @click="toggleAll">{{ areas.every((a) => open[a.name]) ? 'fold all' : 'open all' }}</button>
        <a v-if="data.settings_url" :href="data.settings_url" target="_blank" rel="noopener" class="dim hide-xs">on {{ host }} ↗</a>
      </div>
      <div v-for="a in areas" :key="a.name" class="area">
        <button class="head" :aria-expanded="isOpen(a.name)" @click="open[a.name] = !open[a.name]">
          <span class="dim">{{ isOpen(a.name) ? '▾' : '▸' }}</span> {{ a.name }}
          <span class="dim">({{ a.shown.length }})</span>
          <span v-if="a.rows.some((r) => r.key in edits)" class="warn">changed</span>
        </button>
        <div v-if="isOpen(a.name)" class="rows">
          <div v-for="r in a.shown" :key="r.key" class="setting" :class="{ changed: r.key in edits }">
            <label :for="`s-${r.key}`" :title="r.key">{{ r.label }}</label>
            <span class="control">
              <template v-if="!r.edit">
                <span :class="r.fact ? '' : 'dim'" :title="r.why">{{ show(r.value) }}</span>
              </template>
              <input v-else-if="r.kind === 'bool'" :id="`s-${r.key}`" type="checkbox" :checked="!!current(r)" @change="set(r, $event.target.checked)">
              <select v-else-if="r.kind === 'choice'" :id="`s-${r.key}`" :value="current(r) ?? ''" @change="set(r, $event.target.value)">
                <option v-if="current(r) === null || current(r) === undefined" value="">—</option>
                <option v-for="c in r.choices" :key="c" :value="c">{{ c.replace(/_/g, ' ') }}</option>
              </select>
              <input v-else-if="r.kind === 'int'" :id="`s-${r.key}`" type="number" min="0" :value="current(r) ?? ''" style="width: 10ch" @change="set(r, $event.target.value)">
              <input v-else :id="`s-${r.key}`" :value="r.kind === 'list' ? (current(r) || []).join(', ') : (current(r) ?? '')"
                     :placeholder="r.kind === 'list' ? 'a, b, c' : ''" @change="set(r, $event.target.value)">
            </span>
            <span class="marks">
              <span v-if="keptLabel(r)" class="chip" :class="keptLabel(r) === 'kept' ? 'on' : 'warn'" :title="`${data.file || '.mason.toml'}: ${r.keep}`">{{ keptLabel(r) }}</span>
              <span v-if="!r.edit && !r.fact && r.why" class="dim why">{{ r.why }}</span>
              <span v-else-if="r.note && isOpen(a.name)" class="dim why">{{ r.note }}</span>
            </span>
          </div>
        </div>
      </div>
      <div v-for="l in lists" :key="l.key" class="area">
        <button class="head" :aria-expanded="isOpen(`list:${l.key}`)" @click="open[`list:${l.key}`] = !open[`list:${l.key}`]">
          <span class="dim">{{ isOpen(`list:${l.key}`) ? '▾' : '▸' }}</span> {{ l.label }}
          <span class="dim">({{ l.error ? '?' : l.items.length }})</span>
        </button>
        <div v-if="isOpen(`list:${l.key}`)" class="rows">
          <div v-if="l.error" class="dim">couldn't read: {{ l.error }}</div>
          <div v-else-if="!l.items.length" class="dim">none</div>
          <div v-for="(it, i) in l.items" :key="i" class="item"><span>{{ it.name }}</span> <span class="dim">{{ it.detail }}</span></div>
          <div class="dim note">
            <a v-if="l.manage" :href="l.manage" target="_blank" rel="noopener">manage on {{ host }} ↗</a>
            <span v-if="l.keep"> · .mason.toml key: <code>{{ l.keep }}</code></span>
            <span v-if="l.note"> · {{ l.note }}</span>
          </div>
        </div>
      </div>
      <div v-if="pending.length" class="pending box">
        <div><span class="warn">{{ pending.length }} change{{ pending.length === 1 ? '' : 's' }}</span>
          <span class="dim">: {{ pending.map((p) => `${p.row.label} → ${show(p.value)}`).join(' · ') }}</span></div>
        <div class="row" style="margin-top: 6px">
          <button class="primary" :disabled="busy" @click="apply(false)">apply on {{ host }}</button>
          <button :disabled="busy || !keepable" :title="keepable ? '' : 'doctor has no key for these'" @click="apply(true)">apply and keep in .mason.toml</button>
          <button :disabled="busy" @click="edits = {}">undo</button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.area { border-bottom: 1px dotted var(--bg3); }
.area .head { border: 0; padding: 4px 0; width: 100%; text-align: left; display: flex; gap: 1ch; align-items: center; }
.rows { padding: 0 0 8px 2ch; }
.setting { display: grid; grid-template-columns: minmax(16ch, 34ch) minmax(10ch, auto) 1fr; gap: 4px 1.5ch; align-items: center; padding: 2px 0; }
.setting.changed label { color: var(--warn); }
.setting .control input:not([type="checkbox"]), .setting .control select { width: 100%; max-width: 32ch; }
.marks { display: flex; gap: 1ch; align-items: center; min-width: 0; }
.why { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chip.warn { border-color: var(--warn); color: var(--warn); }
.item { overflow-wrap: anywhere; padding: 1px 0; }
.note { margin-top: 4px; }
.pending { position: sticky; bottom: 0; margin-top: 8px; z-index: 2; }
@media (max-width: 700px) {
  .setting { grid-template-columns: 1fr auto; }
  .marks { grid-column: 1 / -1; }
  .marks:empty { display: none; }
}
</style>
