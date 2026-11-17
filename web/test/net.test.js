// node --test (npm test): how long the app waits before asking the server again.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { nextDelay } from '../src/net.js'

test('2s, then doubling, never over 30s', () => {
  assert.deepEqual([0, 1, 2, 3, 4, 5, 10].map(nextDelay), [2000, 4000, 8000, 16000, 30000, 30000, 30000])
  assert.equal(nextDelay(-1), 2000)
})
