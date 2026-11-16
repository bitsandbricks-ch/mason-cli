// node --test (npm test): the console asks before a line that can change repos, and keeps the dry-run switch.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isDry, prepare } from '../src/consoleline.js'

const writes = new Set(['merge', 'doctor', 'sync'])
const plugins = new Set(['hubra'])

test('a writing command asks first, a dry run or a read does not', () => {
  assert.equal(prepare('mason merge web#8', { writes }).ask, true)
  assert.equal(prepare('merge --dry-run web#8', { writes }).ask, false)
  assert.equal(prepare('status', { writes }).ask, false)
  assert.equal(prepare('hubra deploy', { writes, plugins }).ask, true) // a plugin command may write
})

test('after --, --dry-run is only a name: the line still asks', () => {
  assert.equal(isDry(['merge', 'web#8', '--', '--dry-run']), false)
  assert.equal(prepare('merge web#8 -- --dry-run', { writes }).ask, true)
})

test('with the dry-run switch on, a writing line runs as a dry run without asking', () => {
  assert.deepEqual(prepare('merge web#8', { writes, dryRun: true }), { line: 'merge web#8 --dry-run', ask: false })
  assert.deepEqual(prepare('merge web#8 -- x', { writes, dryRun: true }), { line: 'merge web#8 --dry-run -- x', ask: false })
  assert.deepEqual(prepare('status', { writes, dryRun: true }), { line: 'status', ask: false })
})
