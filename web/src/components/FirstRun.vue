<script setup>
// The first visit: no repos yet, because nothing says which ones. Three steps in place of "nothing here":
// an account, which repos (your own with one click, or orgs and GitLab groups), and optionally a defaults repo.
// Each step saves to your settings at once, and the list loads again.
import { computed, ref } from 'vue'
import { log, put, state } from '../api.js'

const emit = defineEmits(['saved'])
const me = computed(() => state.me || {})
const ids = computed(() => me.value.identities || [])
const gh = computed(() => ids.value.find((i) => i.provider === 'github'))
const gl = computed(() => ids.value.find((i) => i.provider === 'gitlab'))
const s = computed(() => me.value.settings || {})
const hasRepos = computed(() => !!((s.value.orgs || []).length || (s.value.repos || []).length || (s.value.gitlab_groups || []).length
  || (s.value.gitlab_repos || []).length || s.value.defaults))
const readOnly = computed(() => me.value.scope === 'read')
const orgs = ref('')
const groups = ref('')
const defaults = ref('')
const saving = ref(false)
const split = (v) => v.split(/[\s,]+/).map((x) => x.trim().replace(/^@/, '')).filter(Boolean)

async function save(patch, said) {
  saving.value = true
  try {
    state.me.settings = { ...state.me.settings, ...(await put('/settings', patch)) }
    log(said, 'ok')
    emit('saved')
  } catch (e) { log(e.message, 'error') } finally { saving.value = false }
}
const addOwn = () => save({ orgs: [...new Set([...(s.value.orgs || []), gh.value.login])] }, `added your own repos (${gh.value.login})`)
function addOrgs() {
  const o = split(orgs.value)
  const g = split(groups.value).map((x) => x.replace(/^gitlab:/, ''))
  if (!o.length && !g.length) return
  save({ orgs: [...new Set([...(s.value.orgs || []), ...o])], gitlab_groups: [...new Set([...(s.value.gitlab_groups || []), ...g])] },
    `added ${[...o, ...g.map((x) => `gitlab:${x}`)].join(', ')}`)
}
function setDefaults() {
  const d = defaults.value.trim()
  if (d) save({ defaults: d }, `defaults repo: ${d}`)
}
</script>

<template>
  <div class="first-run">
    <h2>get started</h2>
    <p class="dim">Mason lists the repos you tell it about. Three steps, and the list fills in.</p>
    <ol>
      <li :class="{ done: gh || gl }">
        <div class="step"><span class="mark">{{ gh || gl ? '✓' : '1' }}</span>connect an account</div>
        <div v-if="gh || gl" class="dim">signed in as {{ ids.map((i) => `${i.provider}:${i.login}`).join(', ') }}</div>
        <div v-else><router-link class="btn primary" to="/settings">connect GitHub or GitLab under settings ›</router-link></div>
      </li>
      <li :class="{ done: hasRepos }">
        <div class="step"><span class="mark">{{ hasRepos ? '✓' : '2' }}</span>pick your repos</div>
        <p v-if="readOnly" class="warn">this key can only read: change settings in a browser session</p>
        <template v-else>
          <div v-if="gh" class="row">
            <button class="primary" :disabled="saving || (s.orgs || []).includes(gh.login)" @click="addOwn">add my own repos ({{ gh.login }})</button>
          </div>
          <div class="form" style="margin-top: 8px">
            <label for="fr-orgs">GitHub orgs</label>
            <input id="fr-orgs" v-model="orgs" placeholder="acme, acme-labs" :disabled="!gh" @keydown.enter="addOrgs">
            <label for="fr-groups">GitLab groups</label>
            <input id="fr-groups" v-model="groups" placeholder="grp, grp/sub" :disabled="!gl" @keydown.enter="addOrgs">
          </div>
          <button style="margin-top: 6px" :disabled="saving || (!orgs.trim() && !groups.trim())" @click="addOrgs">add</button>
        </template>
      </li>
      <li :class="{ done: !!s.defaults }">
        <div class="step"><span class="mark">{{ s.defaults ? '✓' : '3' }}</span>shared defaults <span class="dim">(optional)</span></div>
        <p class="dim">A repo with a mason.toml says how your repos should be set up (branch rules, labels, files), so Mason can
          check them for drift. <span class="accent">mason init</span> makes one.</p>
        <div v-if="s.defaults" class="dim">using {{ s.defaults }}</div>
        <div v-else-if="!readOnly" class="row">
          <input v-model="defaults" placeholder="acme/defaults" aria-label="defaults repo" @keydown.enter="setDefaults">
          <button :disabled="saving || !defaults.trim()" @click="setDefaults">use it</button>
        </div>
      </li>
    </ol>
    <p class="dim">Everything here is also under <router-link to="/settings">setup › settings</router-link>.</p>
  </div>
</template>

<style scoped>
.first-run { padding: 12px; max-width: 80ch; }
.first-run h2 { margin-top: 0; }
.first-run ol { list-style: none; margin: 12px 0; padding: 0; display: grid; gap: 12px; }
.first-run li { border: 1px solid var(--line); padding: 10px 12px; background: var(--bg2); }
.first-run li.done { opacity: .75; }
.first-run .step { font-weight: 700; margin-bottom: 6px; }
.first-run .mark { display: inline-block; min-width: 2ch; color: var(--accent); }
.first-run li.done .mark { color: var(--ok); }
.first-run p { margin: 4px 0 8px; }
</style>
