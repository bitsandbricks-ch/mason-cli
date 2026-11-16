// node --test (npm test): errors in plain words, links in text, status words and the CLI's detail fields.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { explain, fieldOf, glyph, linkify, stateClass } from '../src/text.js'

test('errors from gh and the API read as plain words, the original kept', () => {
  const cases = [
    ['gh api -X GET /repos/a/b: HTTP 401: Bad credentials', 'your sign-in has expired'],
    ['API rate limit exceeded for user', 'the GitHub rate limit is used up'],
    ['HTTP 403: Resource not accessible by integration', "your account isn't allowed"],
    ['gh api -X GET /repos/acme/web/actions/runs/1: fake gh: no answer for GET', "doesn't exist, or your account can't see it"],
    ['connect GitLab first', 'connect GitLab under setup'],
    ['TypeError: Failed to fetch', "couldn't reach the server"],
  ]
  for (const [raw, want] of cases) {
    const e = explain(`error: ${raw}`)
    assert.ok(e.title.includes(want), `${raw} -> ${e.title}`)
    assert.equal(e.raw, raw)
  }
  assert.equal(explain('error: HTTP 401', 'the events').title.startsWith('the events: '), true)
})

test('an unknown error: its first line, without the command, cut when long', () => {
  assert.equal(explain('gh api -X POST /repos/a/b/pulls: Validation Failed\nmore').title, 'Validation Failed')
  assert.ok(explain('x'.repeat(300)).title.endsWith('…'))
  assert.equal(explain('').title, 'something went wrong')
})

test('links in text become link parts, the rest stays text', () => {
  assert.deepEqual(linkify('see https://github.com/acme/web/pull/7, then'), [
    { text: 'see ' }, { href: 'https://github.com/acme/web/pull/7', label: 'acme/web/pull/7' }, { text: ', then' }])
  assert.deepEqual(linkify(null), [])
  assert.deepEqual(linkify(42), [{ text: '42' }])
})

test('status words get a class and a mark', () => {
  assert.equal(stateClass('success'), 'ok')
  assert.equal(stateClass('CONFLICTS'), 'bad')
  assert.equal(stateClass('running'), 'warn')
  assert.equal(stateClass('open'), '')
  assert.equal(glyph('bad'), '✗')
})

test('a field of the CLI detail text', () => {
  const text = '#7 Add login\nhttps://github.com/acme/web/pull/7\n\n  state    open, by ann\n  branch   feat -> main\n'
  assert.equal(fieldOf(text, 'state'), 'open, by ann')
  assert.equal(fieldOf(text, 'branch'), 'feat -> main')
  assert.equal(fieldOf(text, 'nope'), '')
})

test('which console lines ask first', async () => {
  const { consoleWrites } = await import('../src/text.js')
  const writes = new Set(['merge', 'approve', 'doctor', 'issue', 'release', 'workflows', 'hubra-sync'])
  for (const l of ['merge web#7', 'mason approve', 'doctor', 'issue close web#3', 'release web', 'workflows --fix', 'hubra-sync x'])
    assert.equal(consoleWrites(l, writes), true, l)
  for (const l of ['status', 'merge --dry-run web#7', 'issue view web#3', 'release', 'release --list web', 'workflows', ''])
    assert.equal(consoleWrites(l, writes), false, l)
})
