<script setup>
// One repo as a page (Enter on Repos): its whole detail, what you can do with it, and what that printed;
// its drift against the defaults (doctor, checked when the page opens), its open PRs as links to their
// pages, and its event log at the bottom. After a change, and while a release run is going, the page reads
// the repo again by itself (see useFollow).
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { qs } from '../api.js'
import { act, cached, forget, useFollow } from '../load.js'
import { useKeys } from '../keys.js'
import DoctorPanel from '../components/DoctorPanel.vue'
import EventLog from '../components/EventLog.vue'
import ReleaseForm from '../components/ReleaseForm.vue'
import SecretsPanel from '../components/SecretsPanel.vue'
import TextPane from '../components/TextPane.vue'
import VersionBar from '../components/VersionBar.vue'

const route = useRoute()
const router = useRouter()
const repo = computed(() => String(route.query.repo || ''))
const gitlab = computed(() => repo.value.startsWith('gitlab:'))
const detail = ref('')
const output = ref('')
const form = ref('') // '', 'release' or 'tag'
const suggest = ref('')
const publishes = ref('')
const version = ref(null)
const busy = ref(false) // a release run is going
const checked = ref(0) // bumped after c or f: the doctor panel shows the new result

async function load(fresh = false) {
  if (!repo.value) return
  if (!detail.value) detail.value = '…'
  try { detail.value = (await cached(`/repo${qs({ repo: repo.value, fresh })}`, fresh)).text } catch (e) { detail.value = `error: ${e.message}` }
}

// the open PRs (and MRs) the detail lists, as links to their pages
const pulls = computed(() => detail.value.split('\n').map((l) => l.match(/^\s+[#!](\d+) (.*?)\s{2}https?:\S+$/))
  .filter(Boolean).map((m) => ({ number: Number(m[1]), title: m[2] })))
const log = ref(null)

async function run(q, path, body) {
  const t = await act(q, path, body)
  if (t === null) return
  output.value = t
  forget('/status'); forget('/repo'); forget('/release')
  if (path === '/doctor') checked.value++
  load(true)
  follow.now([repo.value])
  log.value?.burst()
}
const r = () => [repo.value]
const actions = computed(() => [
  { k: 'c', label: 'check against the defaults', fn: () => run(`Check ${repo.value} against the defaults?`, '/doctor', { repos: r() }) },
  { k: 'f', label: 'fix the drift', fn: () => run(`Fix the drift of ${repo.value} (settings, security, rulesets)?`, '/doctor', { repos: r(), fix: true }) },
  { k: 's', label: 'sync the shared files (PR)', fn: () => run(`Open a PR that syncs the shared files into ${repo.value}?`, '/sync', { repos: r() }) },
  { k: 'm', label: 'auto-merge its ready PRs', fn: () => run(`Auto-merge the ready PRs of ${repo.value}?`, '/merge', { targets: r() }) },
  { k: 'M', label: 'merge its ready PRs now', fn: () => run(`Merge the ready PRs of ${repo.value} now?`, '/merge', { targets: r(), now: true }) },
  { k: 'n', label: 'create a release', fn: () => newRelease('release') },
  { k: 'T', label: 'push a tag (its workflow releases)', fn: () => newRelease('tag') },
  { k: 'l', label: 'its releases', fn: () => router.push({ path: '/release', query: { repo: repo.value } }) },
  { k: 'o', label: `open on ${gitlab.value ? 'GitLab' : 'GitHub'}`, fn: open },
])
async function loadReleases(fresh = false, quiet = false) {
  try {
    const p = await cached(`/release${qs({ repo: repo.value, fresh })}`, fresh, { quiet })
    suggest.value = p.suggest; publishes.value = p.publishes || ''; version.value = p.version || null; busy.value = !!p.busy
  } catch { suggest.value = suggest.value || 'v0.1.0' }
}
async function refresh() {
  const name = repo.value
  const got = await cached(`/repo${qs({ repo: name, fresh: true })}`, true, { quiet: true })
  if (name === repo.value) detail.value = got.text
  await loadReleases(true, true)
}
const follow = useFollow({ pending: () => (busy.value ? [repo.value] : []), refresh })
async function newRelease(mode) {
  form.value = mode
  if (!suggest.value) await loadReleases()
}
function done({ text, ok }) { output.value = text; if (ok) { form.value = ''; forget('/release'); forget('/releases'); follow.now([repo.value]); log.value?.burst() } }
const open = () => { const url = detail.value.split('\n')[1]; if (url?.startsWith('http')) window.open(url, '_blank', 'noopener') }
const back = () => (window.history.state?.back ? router.back() : router.push('/'))
const keys = { Escape: () => (form.value ? (form.value = '') : back()), Backspace: back, r: () => { load(true); log.value?.refresh(); checked.value++ } }
watch(actions, (list) => list.forEach((a) => { keys[a.k] = a.fn }), { immediate: true })
useKeys(keys)
// last: the immediate watch uses everything above
watch(repo, () => { detail.value = ''; output.value = ''; form.value = ''; version.value = null; suggest.value = ''; load(); loadReleases() }, { immediate: true })
</script>

<template>
  <div class="view">
    <div class="toolbar">
      <button class="hide-xs" @click="back"><span class="k">esc</span> back</button>
      <span class="accent hide-xs">repos › {{ repo }}</span>
      <span class="spacer" />
      <button @click="load(true); log?.refresh(); checked++"><span class="k">r</span> reload</button>
    </div>
    <div class="split page">
      <div class="pad">
        <h2>actions</h2>
        <div class="actions">
          <button v-for="a in actions" :key="a.k" :class="{ primary: a.k === 'n' }" @click="a.fn"><span class="k">{{ a.k }}</span> {{ a.label }}</button>
        </div>
        <DoctorPanel :repo="repo" :stamp="checked" />
        <SecretsPanel v-if="!gitlab" :repo="repo" @done="({ text }) => (output = text)" />
        <template v-if="output"><h2 style="margin-top: 16px">output</h2><TextPane :text="output" /></template>
        <template v-if="pulls.length">
          <h2 style="margin-top: 16px">{{ gitlab ? 'merge requests' : 'pull requests' }}</h2>
          <div class="actions">
            <router-link v-for="p in pulls" :key="p.number" class="btn" :to="{ path: '/pr', query: { repo, number: p.number } }">
              <span class="dim">{{ gitlab ? '!' : '#' }}{{ p.number }}</span> {{ p.title }}</router-link>
          </div>
        </template>
      </div>
      <div class="pad">
        <VersionBar v-if="version" :repo="repo" :version="version" @done="done" />
        <ReleaseForm v-if="form" :key="form" :mode="form" :repo="repo" :suggest="suggest" :publishes="publishes"
                     @done="done" @cancel="form = ''" />
        <TextPane :text="detail" placeholder="loading…" />
        <EventLog ref="log" :repo="repo" kind="repo" />
      </div>
    </div>
  </div>
</template>
