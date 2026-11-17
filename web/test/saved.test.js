// node --test (npm test): saved views.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { MAX_VIEWS, addView, removeView, scopeFrom, suggestName, viewPath } from '../src/saved.js'

test('the link keeps the page, its query and the group filter', () => {
  assert.equal(viewPath({ path: '/prs', query: { show: 'mine' } }, { group: 'acme/', provider: 'all' }), '/prs?show=mine&group=acme%2F')
  assert.equal(viewPath({ path: '/', query: {} }, { group: '', provider: 'all' }), '/')
  assert.equal(viewPath({ path: '/runs', query: { group: 'old' } }, { group: '', provider: 'gitlab' }), '/runs?provider=gitlab')
})

test('one view per name and per link, newest last, up to the limit', () => {
  let l = addView([], 'mine', '/prs?show=mine')
  l = addView(l, 'acme', '/?group=acme%2F')
  l = addView(l, 'MINE', '/prs?show=mine&group=x') // same name: replaced
  assert.deepEqual(l.map((v) => v.name), ['acme', 'MINE'])
  l = addView(l, 'again', '/?group=acme%2F') // same link: renamed
  assert.deepEqual(l.map((v) => v.name), ['MINE', 'again'])
  assert.deepEqual(addView(l, '  ', '/x'), l)
  assert.deepEqual(removeView(l, '/?group=acme%2F').map((v) => v.name), ['MINE'])
  const many = Array.from({ length: MAX_VIEWS + 3 }, (_, i) => i).reduce((acc, i) => addView(acc, `v${i}`, `/p${i}`), [])
  assert.equal(many.length, MAX_VIEWS)
  assert.equal(many.at(-1).name, `v${MAX_VIEWS + 2}`)
})

test('a link may set the group and provider', () => {
  assert.deepEqual(scopeFrom({ group: 'acme/', provider: 'github' }), { group: 'acme/', provider: 'github' })
  assert.deepEqual(scopeFrom({ provider: 'nope' }), null)
  assert.equal(scopeFrom({}), null)
})

test('a suggested name says what the view shows', () => {
  assert.equal(suggestName('pull requests', { query: { show: 'mine' } }, { group: 'acme/' }), 'pull requests · mine · acme/')
})

test('the side panel is not part of a saved view', () => {
  assert.equal(viewPath({ path: '/prs', query: { show: 'mine', side: 'pr:acme/web#7' } }, {}), '/prs?show=mine')
})
