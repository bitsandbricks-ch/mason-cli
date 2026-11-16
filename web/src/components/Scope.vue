<script setup>
// Which repos a list shows: GitHub, GitLab or both, and one group (of the defaults, or an org).
import { computed, watch } from 'vue'
import { state } from '../api.js'
import { scope } from '../scope.js'
import GroupSelect from './GroupSelect.vue'
defineProps({ groups: { type: Array, default: () => [] } })
// The provider menu only when both are connected: with one, it only offered a way to an empty list.
const both = computed(() => {
  const ids = new Set((state.me?.identities || []).map((i) => i.provider))
  return ids.has('github') && ids.has('gitlab')
})
// a saved "gitlab only" from before GitLab was disconnected would hide every repo, with no menu to undo it
watch(both, (b) => { if (!b && state.me?.user) scope.provider = 'all' }, { immediate: true })
</script>

<template>
  <span class="row">
    <select v-if="both" v-model="scope.provider" aria-label="provider">
      <option value="all">github + gitlab</option>
      <option value="github">github</option>
      <option value="gitlab">gitlab</option>
    </select>
    <GroupSelect :groups="groups" />
  </span>
</template>
