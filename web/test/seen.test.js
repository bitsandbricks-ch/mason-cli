// node --test (npm test): "new since your last visit".
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { fresh, merged } from '../src/seen.js'

test('the first visit marks nothing', () => {
  assert.equal(fresh(null, ['a', 'b']).size, 0)
})

test('rows not seen before are new', () => {
  assert.deepEqual([...fresh(['a', 'b'], ['a', 'c', 'd'])], ['c', 'd'])
  assert.equal(fresh(['a'], []).size, 0)
})

test('a visit keeps its keys first, the older ones after, up to the limit', () => {
  assert.deepEqual(merged(['a', 'b'], ['c', 'a']), ['c', 'a', 'b'])
  assert.deepEqual(merged(null, ['x']), ['x'])
  assert.deepEqual(merged(['1', '2', '3'], ['4'], 2), ['4', '1'])
})
