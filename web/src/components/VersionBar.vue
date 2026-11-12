<script setup>
// The version file against the latest release, with bump (b: pick patch, minor or major; a PR with the next
// version and its changelog section) and release (R: push v<version> once the bump is merged). Shown on a repo's
// and its releases' pages, and under the selected repo in Releases.
import { computed } from 'vue'
import { act } from '../load.js'
import { ask, choose } from '../ui.js'
import { useKeys } from '../keys.js'

const props = defineProps({ repo: { type: String, required: true }, version: { type: Object, default: null } })
const emit = defineEmits(['done'])
const v = computed(() => props.version)
const next = computed(() => v.value?.next || {})

async function bump() {
  if (!v.value) return
  const cur = v.value.version || '?'
  const open = v.value.pr ? `The bump PR #${v.value.pr.number} to ${v.value.pr.version} is still open.\n` : ''
  const unreleased = v.value.todo ? `${cur} isn't released yet (latest ${v.value.released || 'none'}); R releases it as it is.\n` : ''
  let level = await choose(`Bump ${props.repo}: ${v.value.file} says ${cur}`, [
    { key: 'p', value: 'patch', label: `patch → ${next.value.patch || '?'}`, hint: 'fixes' },
    { key: 'm', value: 'minor', label: `minor → ${next.value.minor || '?'}`, hint: 'new features' },
    { key: 'M', value: 'major', label: `major → ${next.value.major || '?'}`, hint: 'breaking changes' },
    { key: 'v', value: 'other', label: 'another version…' },
  ], { detail: (open + unreleased).trim() })
  if (level === 'other') {
    level = await ask(`Set ${props.repo} to which version?`, { input: { placeholder: 'e.g. 1.4.0' }, allowDry: false })
  }
  if (!level) return
  const lv = level.trim()
  const to = next.value[lv] || lv
  const text = await act(`Open a PR in ${props.repo} that sets ${v.value.file} to ${to} and adds the changelog section?`, '/bump',
    { repo: props.repo, level: lv }, { detail: `${cur} → ${to} (${lv}). After its merge, R pushes the tag and the repo's workflow releases it.` })
  if (text !== null) emit('done', { text, repo: props.repo, ok: !text.startsWith('error') && !text.includes('[dry-run]') })
}
async function release() {
  if (!v.value?.todo) return
  const text = await act(`Push the tag ${v.value.tag} on ${v.value.base} of ${props.repo}?`, '/release/version', { repo: props.repo },
    { detail: `${v.value.file} says ${v.value.version}, latest release ${v.value.released || 'none'}. The repo's release workflow takes it from there.` })
  if (text !== null) emit('done', { text, repo: props.repo, ok: !text.startsWith('error') && !text.includes('[dry-run]') })
}
useKeys({ b: bump, R: release })
defineExpose({ bump, release })
</script>

<template>
  <div v-if="v" class="box">
    <div class="row">
      <span class="dim">{{ v.file }}</span> <span class="accent">{{ v.version || '?' }}</span>
      <span class="dim">· released</span> <span>{{ v.released || 'none' }}</span>
      <span v-if="v.todo" class="warn">· {{ v.version }} isn't released yet: {{ v.tag }} is ready</span>
      <span v-else class="dim">· released; b bumps it</span>
      <span class="spacer" />
      <button @click="bump"><span class="k">b</span> bump</button>
      <button :disabled="!v.todo" :class="{ primary: v.todo }" @click="release"><span class="k">R</span> release {{ v.todo ? v.tag : '' }}</button>
    </div>
    <div v-if="v.pr" class="row" style="margin-top: 6px">
      <span class="dim">bump PR</span>
      <a class="accent" :href="v.pr.url" target="_blank" rel="noopener">#{{ v.pr.number }}</a>
      <span>to {{ v.pr.version }} is open; merge it, then R releases it</span>
    </div>
  </div>
</template>
