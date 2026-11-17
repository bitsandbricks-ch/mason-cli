import { test } from 'node:test'
import assert from 'node:assert/strict'
import { fromQuery, sameQuery, toQuery } from '../src/linkq.js'

const SPEC = {
  state: { def: 'open', ok: (v) => ['open', 'closed', 'all'].includes(v) },
  mine: { def: false },
  label: { def: '' },
  stale: { def: 0, ok: (v) => [0, 30, 90].includes(v) },
}

test('an empty link gives the defaults', () => {
  assert.deepEqual(fromQuery({}, SPEC), { state: 'open', mine: false, label: '', stale: 0 })
  assert.deepEqual(fromQuery(undefined, SPEC), { state: 'open', mine: false, label: '', stale: 0 })
})

test('a link sets each filter by its type', () => {
  assert.deepEqual(fromQuery({ state: 'closed', mine: '1', label: 'bug', stale: '30' }, SPEC),
    { state: 'closed', mine: true, label: 'bug', stale: 30 })
})

test('values the list does not offer fall back to the default', () => {
  assert.deepEqual(fromQuery({ state: 'weird', mine: 'yes', stale: '7', label: ['a', 'b'] }, SPEC),
    { state: 'open', mine: false, label: '', stale: 0 })
  assert.equal(fromQuery({ stale: 'abc' }, SPEC).stale, 0)
})

test('only filters off their default go in the link, other keys stay', () => {
  assert.deepEqual(toQuery({ state: 'open', mine: true, label: '', stale: 90 }, SPEC, { group: 'acme/', stale: '30' }),
    { group: 'acme/', mine: '1', stale: '90' })
  assert.deepEqual(toQuery({ state: 'open', mine: false, label: '', stale: 0 }, SPEC, { state: 'closed' }), {})
})

test('a round trip keeps the filters', () => {
  const v = { state: 'all', mine: true, label: 'help wanted', stale: 30 }
  assert.deepEqual(fromQuery(toQuery(v, SPEC), SPEC), v)
})

test('sameQuery ignores order and undefined keys', () => {
  assert.ok(sameQuery({ a: '1', b: 'x' }, { b: 'x', a: '1', c: undefined }))
  assert.ok(!sameQuery({ a: '1' }, { a: '2' }))
  assert.ok(!sameQuery({ a: '1' }, {}))
})
