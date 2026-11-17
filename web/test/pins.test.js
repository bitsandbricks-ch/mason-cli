// node --test (npm test): pinned repos first, the rest in their order.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { pinnedFirst } from '../src/pins.js'

test('pinned rows come first, both groups keep their order', () => {
  const rows = ['a/1', 'a/2', 'a/3', 'a/4'].map((repo) => ({ repo }))
  const got = pinnedFirst(rows, new Set(['a/4', 'a/2'])).map((r) => r.repo)
  assert.deepEqual(got, ['a/2', 'a/4', 'a/1', 'a/3'])
})

test('nothing pinned changes nothing, and the repo can come from elsewhere', () => {
  const rows = [{ r: 'x' }, { r: 'y' }]
  assert.deepEqual(pinnedFirst(rows, new Set()), rows)
  assert.deepEqual(pinnedFirst(rows, new Set(['y']), (x) => x.r).map((x) => x.r), ['y', 'x'])
})
