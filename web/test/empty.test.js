import { test } from 'node:test'
import assert from 'node:assert/strict'
import { emptyText } from '../src/empty.js'

test('nothing narrows the list: its own words', () => {
  assert.equal(emptyText('no runs yet: repos with CI show theirs here'), 'no runs yet: repos with CI show theirs here')
  assert.equal(emptyText('no open issues', [false, '', 0]), 'no open issues')
})

test('a group: named, and the setup hint left out', () => {
  assert.equal(emptyText('no runs yet: repos with CI show theirs here', [], 'in org acme'), 'no runs yet in org acme')
  assert.equal(emptyText('✓ no open security alerts', [], 'on gitlab'), '✓ no open security alerts on gitlab')
})

test('filters on: named', () => {
  assert.equal(emptyText('no open issues', ['state closed', false, 'label bug']),
    'nothing matches state closed · label bug: change or clear the filter')
  assert.equal(emptyText('no open issues', ['mine'], 'in group plugins'),
    'nothing matches mine in group plugins: change or clear the filter')
})
