// node --test (npm test): the hidden tab's mark and notifications.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { markFor } from '../src/title.js'

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
