// node --test (npm test): picking several rows of a list.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { alive, range, toggle, toggleAll } from '../src/pick.js'

test('toggle a row in and out', () => {
  assert.deepEqual(toggle([], 'a'), ['a'])
  assert.deepEqual(toggle(['a', 'b'], 'a'), ['b'])
})

test('the header box picks what the filter shows, and unpicks it again', () => {
  assert.deepEqual(toggleAll(['x'], ['a', 'b']), ['x', 'a', 'b'])
  assert.deepEqual(toggleAll(['x', 'a', 'b'], ['a', 'b']), ['x'])
  assert.deepEqual(toggleAll(['a'], ['a', 'b']), ['a', 'b'])
  assert.deepEqual(toggleAll([], []), [])
})

test('shift+click picks the span, either way round', () => {
  const order = ['a', 'b', 'c', 'd']
  assert.deepEqual(range([], order, 'b', 'd'), ['b', 'c', 'd'])
  assert.deepEqual(range(['a'], order, 'c', 'a'), ['a', 'b', 'c'])
  assert.deepEqual(range([], order, 'zz', 'c'), ['c'])
})

test('picks of rows that left the list go too', () => {
  assert.deepEqual(alive(['a', 'b', 'c'], ['c', 'a']), ['a', 'c'])
})
