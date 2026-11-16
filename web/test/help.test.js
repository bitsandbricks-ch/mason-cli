// node --test (npm test): the keys sheet's rows, read from buttons.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { keysOf } from '../src/help.js'

test('one row per key, enabled buttons win, global keys and junk left out', () => {
  const rows = keysOf([
    { key: 'm', label: 'auto-merge   when checks pass', off: true },
    { key: 'M', label: 'merge now' },
    { key: 'm', label: 'auto-merge' }, // the toolbar's twin, enabled
    { key: 'r', label: 'reload' },
    { key: '', label: 'no key' },
    { key: 'y', label: '' },
    { key: 'esc', label: 'back' },
    { key: 'repo', label: 'not a key' },
    { key: 'y', label: 'mark ready', off: true },
  ])
  assert.deepEqual(rows, [
    { key: 'm', label: 'auto-merge', off: false },
    { key: 'M', label: 'merge now', off: false },
    { key: 'y', label: 'mark ready', off: true },
  ])
})
