<script setup>
// A new account knows no repos: every list was just empty. Until the settings name some, each work and health
// view says so once, with the way there.
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { state } from '../api.js'
import { sectionOf } from '../router.js'

const route = useRoute()
const KEYS = ['defaults', 'orgs', 'repos', 'gitlab_groups', 'gitlab_repos']
const empty = computed(() => {
  const s = state.me?.settings
  return !!s && KEYS.every((k) => !(Array.isArray(s[k]) ? s[k].length : s[k]))
})
const show = computed(() => empty.value && sectionOf(route.meta.tab || route.name) !== 'setup')
</script>

<template>
  <div v-if="show" class="setup-hint" role="status">
    <span>Mason doesn't know your repos yet: name your GitHub orgs, GitLab groups or a defaults repo.</span>
    <router-link class="btn primary" to="/settings">set up repos ›</router-link>
  </div>
</template>
