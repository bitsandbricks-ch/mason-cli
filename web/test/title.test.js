// node --test (npm test): the browser tab's title.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { markFor, pageTitle } from '../src/title.js'

const TABS = [{ name: 'repos', label: 'repos' }, { name: 'prs', label: 'pull requests' }]

test('a tab says its label', () => {
  assert.equal(pageTitle({ name: 'prs', query: {} }, TABS), 'pull requests · Mason')
})

test('a detail page says which one', () => {
  assert.equal(pageTitle({ name: 'pr', query: { repo: 'acme/web', number: '7' } }, TABS), 'acme/web#7 · pull requests · Mason')
  assert.equal(pageTitle({ name: 'repo', query: { repo: 'acme/web' } }, TABS), 'acme/web · repos · Mason')
  assert.equal(pageTitle({ name: 'run', query: { repo: 'acme/web', id: '42' } }, TABS), 'acme/web run 42 · runs · Mason')
  assert.equal(pageTitle({ name: 'release', query: { repo: 'acme/web', tag: 'v1.0.0' } }, TABS), 'acme/web v1.0.0 · releases · Mason')
  assert.equal(pageTitle({ name: 'release', query: {} }, TABS), 'releases · Mason')
})

test('sign-in and unknown pages stay plain', () => {
  assert.equal(pageTitle({ name: 'login', query: {} }, TABS), 'Mason')
  assert.equal(pageTitle(null, TABS), 'Mason')
  assert.equal(pageTitle({ name: 'plugin-tab', query: {}, params: { plugin: 'hubra' } }, TABS), 'hubra · Mason')
})

test('an error wins over a success', () => {
  assert.equal(markFor(['ok', 'error']), '✗')
  assert.equal(markFor(['info', 'ok']), '✓')
  assert.equal(markFor(['info']), '')
})

test('a notification only for a finished change, in the background, when asked for and allowed', async () => {
  const { shouldNotify, notifyText } = await import('../src/title.js')
  const ok = { kind: 'ok', text: 'Merge acme/web#7: done' }
  const on = { on: true, hidden: true, permission: 'granted' }
  assert.equal(shouldNotify(ok, on), true)
  assert.equal(shouldNotify({ kind: 'error', text: 'x' }, on), true)
  assert.equal(shouldNotify({ kind: 'info', text: 'loaded' }, on), false)
  assert.equal(shouldNotify(ok, { ...on, on: false }), false)
  assert.equal(shouldNotify(ok, { ...on, hidden: false }), false)
  assert.equal(shouldNotify(ok, { ...on, permission: 'default' }), false)
  assert.deepEqual(notifyText(ok), { title: '✓ Mason: done', body: 'Merge acme/web#7: done' })
  assert.deepEqual(notifyText({ kind: 'error', text: '[dry-run] Merge: had errors' }), { title: '✗ Mason: something failed', body: 'dry run: Merge: had errors' })
})
