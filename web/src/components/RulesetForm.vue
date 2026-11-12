<script setup>
// A GitHub ruleset (the JSON of .mason/rulesets, .github/rulesets or a defaults rulesets folder) as a form:
// what it applies to, who may bypass it, and its rules. It edits the JSON text in place (v-model), so the
// JSON editor next to it stays the whole truth: rules and settings the form doesn't know are kept as they are.
import { computed } from 'vue'

const props = defineProps({ modelValue: { type: String, required: true } })
const emit = defineEmits(['update:modelValue'])

const parsed = computed(() => { try { const v = JSON.parse(props.modelValue); return v && typeof v === 'object' ? v : null } catch { return null } })
function update(fn) {
  const rs = JSON.parse(JSON.stringify(parsed.value))
  fn(rs)
  emit('update:modelValue', `${JSON.stringify(rs, null, 2)}\n`)
}
const rule = (type) => (parsed.value?.rules || []).find((r) => r.type === type)
function toggle(type, on, parameters) {
  update((rs) => {
    rs.rules = (rs.rules || []).filter((r) => r.type !== type)
    if (on) rs.rules.push(parameters ? { type, parameters } : { type })
  })
}
function param(type, key, value) {
  update((rs) => {
    const r = (rs.rules || []).find((x) => x.type === type)
    if (r) r.parameters = { ...(r.parameters || {}), [key]: value }
  })
}
const list = (v) => String(v).split(',').map((x) => x.trim()).filter(Boolean)
const field = (key, value) => update((rs) => { rs[key] = value })
const refs = (which) => (parsed.value?.conditions?.ref_name?.[which] || []).join(', ')
function setRefs(which, text) {
  update((rs) => {
    rs.conditions = rs.conditions || {}
    rs.conditions.ref_name = { include: [], exclude: [], ...(rs.conditions.ref_name || {}) }
    rs.conditions.ref_name[which] = list(text).map((x) => (x.startsWith('~') || x.startsWith('refs/') ? x : `refs/${parsed.value?.target === 'tag' ? 'tags' : 'heads'}/${x}`))
  })
}
// "admins may bypass": the repository admin role (id 5), always
const ADMIN = { actor_id: 5, actor_type: 'RepositoryRole', bypass_mode: 'always' }
const isAdmin = (a) => a.actor_type === 'RepositoryRole' && a.actor_id === 5
const adminBypass = computed(() => (parsed.value?.bypass_actors || []).find(isAdmin)?.bypass_mode || '')
function setAdmin(mode) {
  update((rs) => {
    rs.bypass_actors = (rs.bypass_actors || []).filter((a) => !isAdmin(a))
    if (mode) rs.bypass_actors.push({ ...ADMIN, bypass_mode: mode })
  })
}
const others = computed(() => (parsed.value?.bypass_actors || []).filter((a) => !isAdmin(a)))
const SIMPLE = [['deletion', 'block deletion'], ['non_fast_forward', 'block force pushes'], ['creation', 'restrict creation'],
  ['update', 'restrict updates'], ['required_linear_history', 'linear history'], ['required_signatures', 'signed commits']]
const pr = computed(() => rule('pull_request'))
const checks = computed(() => rule('required_status_checks'))
const prDefaults = { required_approving_review_count: 1, dismiss_stale_reviews_on_push: false, require_code_owner_review: false,
  require_last_push_approval: false, required_review_thread_resolution: false }
const known = new Set([...SIMPLE.map(([t]) => t), 'pull_request', 'required_status_checks'])
const unknown = computed(() => (parsed.value?.rules || []).filter((r) => !known.has(r.type)).map((r) => r.type))
</script>

<template>
  <div v-if="!parsed" class="bad">The JSON doesn't parse: fix it in the JSON tab first.</div>
  <div v-else class="rs">
    <div class="line">
      <label>name <input :value="parsed.name || ''" @change="field('name', $event.target.value.trim())"></label>
      <label>applies to <select :value="parsed.target || 'branch'" @change="field('target', $event.target.value)">
        <option value="branch">branches</option><option value="tag">tags</option><option value="push">pushes</option></select></label>
      <label>enforcement <select :value="parsed.enforcement || 'active'" @change="field('enforcement', $event.target.value)">
        <option value="active">active</option><option value="evaluate">evaluate (report only)</option><option value="disabled">disabled</option></select></label>
    </div>
    <div class="line">
      <label>include <input :value="refs('include')" placeholder="~DEFAULT_BRANCH, release/*" style="min-width: 24ch" @change="setRefs('include', $event.target.value)"></label>
      <label>exclude <input :value="refs('exclude')" placeholder="none" @change="setRefs('exclude', $event.target.value)"></label>
    </div>
    <div class="line">
      <label>admins may bypass <select :value="adminBypass" @change="setAdmin($event.target.value)">
        <option value="">no</option><option value="always">always</option><option value="pull_request">on pull requests</option></select></label>
      <span v-if="others.length" class="dim">and {{ others.length }} more bypass actor{{ others.length === 1 ? '' : 's' }} (JSON tab)</span>
    </div>
    <div class="line">
      <label v-for="[t, label] in SIMPLE" :key="t"><input type="checkbox" :checked="!!rule(t)" @change="toggle(t, $event.target.checked)"> {{ label }}</label>
    </div>
    <div class="line">
      <label><input type="checkbox" :checked="!!pr" @change="toggle('pull_request', $event.target.checked, prDefaults)"> require a pull request</label>
      <template v-if="pr">
        <label>approvals <input type="number" min="0" max="10" style="width: 6ch" :value="pr.parameters?.required_approving_review_count ?? 0"
                                @change="param('pull_request', 'required_approving_review_count', Number($event.target.value) || 0)"></label>
        <label><input type="checkbox" :checked="!!pr.parameters?.dismiss_stale_reviews_on_push" @change="param('pull_request', 'dismiss_stale_reviews_on_push', $event.target.checked)"> dismiss stale</label>
        <label><input type="checkbox" :checked="!!pr.parameters?.require_code_owner_review" @change="param('pull_request', 'require_code_owner_review', $event.target.checked)"> code owners</label>
        <label><input type="checkbox" :checked="!!pr.parameters?.require_last_push_approval" @change="param('pull_request', 'require_last_push_approval', $event.target.checked)"> approve last push</label>
        <label><input type="checkbox" :checked="!!pr.parameters?.required_review_thread_resolution" @change="param('pull_request', 'required_review_thread_resolution', $event.target.checked)"> resolve threads</label>
      </template>
    </div>
    <div class="line">
      <label><input type="checkbox" :checked="!!checks" @change="toggle('required_status_checks', $event.target.checked, { strict_required_status_checks_policy: false, required_status_checks: [] })"> require checks</label>
      <template v-if="checks">
        <input :value="(checks.parameters?.required_status_checks || []).map((c) => c.context).join(', ')" placeholder="test, lint" style="min-width: 20ch"
               @change="param('required_status_checks', 'required_status_checks', list($event.target.value).map((context) => ({ context })))">
        <label><input type="checkbox" :checked="!!checks.parameters?.strict_required_status_checks_policy" @change="param('required_status_checks', 'strict_required_status_checks_policy', $event.target.checked)"> branch up to date</label>
      </template>
    </div>
    <div v-if="unknown.length" class="dim">also: {{ unknown.join(', ') }} (kept; edit them in the JSON tab)</div>
  </div>
</template>

<style scoped>
.rs { padding: 6px 0; }
.line { display: flex; flex-wrap: wrap; gap: 4px 2ch; align-items: center; margin: 6px 0; }
.line label { display: inline-flex; gap: .8ch; align-items: center; }
</style>
