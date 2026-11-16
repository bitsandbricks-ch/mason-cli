// node --test (npm test): the finder's matching.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { remember, score, search } from '../src/palette.js'

test('a match at the start beats one at a word start, then inside a word, then letters in order', () => {
  const start = score('web', 'web-app')
  const word = score('web', 'acme/web')
  const inside = score('web', 'acme/cobweb')
  const letters = score('aw', 'acme/web')
  assert.ok(start > word && word > inside && inside > letters && letters > 0)
})

test('no match is 0, and case does not matter', () => {
  assert.equal(score('zz', 'acme/web'), 0)
  assert.ok(score('ACME', 'acme/web') > 90)
  assert.equal(score('x', ''), 0)
})

const ITEMS = [
  { kind: 'view', label: 'pull requests', hint: 'open pull and merge requests' },
  { kind: 'repo', label: 'acme/web', hint: 'group apps' },
  { kind: 'repo', label: 'acme/api', hint: 'group apps' },
  { kind: 'pr', label: 'acme/web#7 Fix the login page', hint: 'ann · checks failing' },
]

test('every word has to fit, the best fit comes first', () => {
  assert.deepEqual(search(ITEMS, 'web').map((x) => x.label), ['acme/web', 'acme/web#7 Fix the login page'])
  assert.deepEqual(search(ITEMS, 'web login').map((x) => x.label), ['acme/web#7 Fix the login page'])
  assert.deepEqual(search(ITEMS, 'nothing here'), [])
})

test('the hint counts, for less', () => {
  assert.deepEqual(search(ITEMS, 'apps').map((x) => x.label), ['acme/web', 'acme/api'])
  assert.equal(search(ITEMS, 'failing')[0].kind, 'pr')
})

test('an empty query keeps the order, up to the limit', () => {
  assert.deepEqual(search(ITEMS, '  ', 2), ITEMS.slice(0, 2))
})

test('remember puts the newest first, once', () => {
  assert.deepEqual(remember(['a', 'b', 'c'], 'b'), ['b', 'a', 'c'])
  assert.deepEqual(remember(undefined, 'a'), ['a'])
  assert.equal(remember(['1', '2', '3'], '4', 3).length, 3)
})
