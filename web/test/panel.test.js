// node --test (npm test): the side panel's URL (?side=), when a navigation opens it, following the list, its width.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { clampWidth, decodeSide, encodeSide, follow, listens, pageRoute, sideFor, targetOf, withSide } from '../src/panel.js'

test('targets round-trip through ?side=', () => {
  const cases = [
    [{ kind: 'repo', repo: 'acme/web' }, 'repo:acme/web'],
    [{ kind: 'pr', repo: 'acme/web', number: 7 }, 'pr:acme/web#7'],
    [{ kind: 'issue', repo: 'gitlab:grp/sub/app', number: 12 }, 'issue:gitlab:grp/sub/app#12'],
    [{ kind: 'run', repo: 'acme/web', id: 123456789 }, 'run:acme/web@123456789'],
    [{ kind: 'release', repo: 'acme/web', tag: 'v1.2.0' }, 'release:acme/web@v1.2.0'],
    [{ kind: 'release', repo: 'acme/web' }, 'release:acme/web'],
  ]
  for (const [t, s] of cases) {
    assert.equal(encodeSide(t), s)
    assert.deepEqual(decodeSide(s), t)
  }
})

test('junk in ?side= is no panel', () => {
  for (const s of ['', 'pr', 'nope:acme/web', 'pr:acme/web', 'pr:acme/web#x', 'pr:acme/web#-1', 'run:acme/web@', 'pr:#7', 'repo:a b', null, undefined]) {
    assert.equal(decodeSide(s), null, String(s))
  }
  assert.equal(encodeSide({ kind: 'pr', repo: 'acme/web' }), '')
  assert.equal(encodeSide({ kind: 'nope', repo: 'acme/web' }), '')
  assert.equal(encodeSide(null), '')
})

test('detail routes are targets, and back', () => {
  assert.deepEqual(targetOf({ path: '/pr', query: { repo: 'acme/web', number: '7' } }), { kind: 'pr', repo: 'acme/web', number: 7 })
  assert.deepEqual(targetOf({ path: '/run', query: { repo: 'acme/web', id: '99' } }), { kind: 'run', repo: 'acme/web', id: 99 })
  assert.deepEqual(targetOf({ path: '/release', query: { repo: 'acme/web', tag: 'v2' } }), { kind: 'release', repo: 'acme/web', tag: 'v2' })
  assert.equal(targetOf({ path: '/prs', query: {} }), null)
  assert.equal(targetOf({ path: '/pr', query: { repo: 'acme/web' } }), null)
  assert.deepEqual(pageRoute({ kind: 'issue', repo: 'acme/web', number: 3 }), { path: '/issue', query: { repo: 'acme/web', number: '3' } })
  assert.deepEqual(pageRoute({ kind: 'release', repo: 'acme/web' }), { path: '/release', query: { repo: 'acme/web' } })
})

test('the panel keeps the rest of the URL', () => {
  const from = { path: '/prs', query: { group: 'acme/' }, hash: '' }
  assert.deepEqual(withSide(from, { kind: 'pr', repo: 'acme/web', number: 7 }), { path: '/prs', query: { group: 'acme/', side: 'pr:acme/web#7' }, hash: '' })
  assert.deepEqual(withSide({ ...from, query: { group: 'acme/', side: 'pr:acme/web#7' } }, null), from)
})

const pr = { path: '/pr', query: { repo: 'acme/web', number: '7' } }
const list = { path: '/prs', query: {}, hash: '' }
const wide = { wide: true, first: false, asPage: false, popping: false }

test('a detail page opens in the panel of the page you are on', () => {
  assert.deepEqual(sideFor(pr, list, wide), { path: '/prs', query: { side: 'pr:acme/web#7' }, hash: '' })
  // from a repo's page: its PR on the right of it
  const repoPage = { path: '/repo', query: { repo: 'acme/web' }, hash: '' }
  assert.deepEqual(sideFor(pr, repoPage, wide).query, { repo: 'acme/web', side: 'pr:acme/web#7' })
  // from a panel: the panel shows the new one
  assert.equal(sideFor(pr, { ...list, query: { side: 'repo:acme/web' } }, wide).query.side, 'pr:acme/web#7')
})

test('…but as a page: on a phone, on the first page, when asked, on back/forward, to itself', () => {
  assert.equal(sideFor(pr, list, { ...wide, wide: false }), null)
  assert.equal(sideFor(pr, list, { ...wide, first: true }), null)
  assert.equal(sideFor(pr, list, { ...wide, asPage: true }), null)
  assert.equal(sideFor(pr, list, { ...wide, popping: true }), null)
  assert.equal(sideFor(pr, { ...pr, hash: '' }, wide), null)
  assert.equal(sideFor(pr, { path: '/login', query: {} }, wide), null)
  assert.equal(sideFor(list, pr, wide), null)
})

test('the panel follows the list, for the same kind only', () => {
  const open = { kind: 'pr', repo: 'acme/web', number: 7 }
  assert.deepEqual(follow(open, { kind: 'pr', repo: 'acme/api', number: 2 }), { kind: 'pr', repo: 'acme/api', number: 2 })
  assert.equal(follow(open, { ...open }), null)
  assert.equal(follow(open, { kind: 'repo', repo: 'acme/web' }), null)
  assert.equal(follow(null, open), null)
  assert.equal(follow(open, null), null)
})

test('the panel is never narrower than 420px and leaves the list 360px', () => {
  assert.equal(clampWidth(NaN, 1600), 800)
  assert.equal(clampWidth(100, 1600), 420)
  assert.equal(clampWidth(1500, 1600), 1240)
  assert.equal(clampWidth(700, 1600), 700)
  assert.equal(clampWidth(700, 600), 420) // a small window: the panel still fits its content
})

test('with a panel open only the page in it takes keys', () => {
  assert.equal(listens({ sideOpen: false, inSide: false }), true)
  assert.equal(listens({ sideOpen: true, inSide: false }), false)
  assert.equal(listens({ sideOpen: true, inSide: true }), true)
})

test('what counts as leaving the page (for unsaved changes)', async () => {
  const { leaves } = await import('../src/panel.js')
  const repo = { path: '/repo', query: { repo: 'acme/web' } }
  assert.equal(leaves({ path: '/repo', query: { repo: 'acme/web', tab: 'x' } }, repo), false)
  assert.equal(leaves({ path: '/repo', query: { repo: 'acme/api' } }, repo), true)
  assert.equal(leaves({ path: '/prs', query: {} }, repo), true)
  const list = { path: '/', query: { side: 'repo:acme/web' } }
  assert.equal(leaves({ path: '/', query: { side: 'repo:acme/web', group: 'acme/' } }, list), false)
  assert.equal(leaves({ path: '/', query: { side: 'repo:acme/api' } }, list), true)
  assert.equal(leaves({ path: '/', query: {} }, list), true)
  assert.equal(leaves({ path: '/defaults', query: { file: 'b' } }, { path: '/defaults', query: { file: 'a' } }), false)
})
