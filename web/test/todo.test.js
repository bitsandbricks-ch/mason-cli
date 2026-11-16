// node --test (npm test): what the "to do" view lists, and in which order.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { todoItems } from '../src/todo.js'

const status = {
  head: ['group', 'released', 'PRs ready/draft', 'CI'],
  rows: [{ repo: 'acme/api', cells: ['default', 'v1', '0/0', 'failure'] }, { repo: 'acme/web', cells: ['default', '-', '2/1', 'success'] }],
  doctor: { 'acme/web': { ok: false, issues: 3 }, 'acme/api': { ok: true, issues: 0 }, 'mike/x': { error: true } },
}
const prs = [
  { repo: 'acme/web', number: 7, title: 'Add login', merge: 'clean', checks: 'success' },
  { repo: 'acme/web', number: 8, title: 'WIP', draft: true, merge: 'clean', checks: 'success' },
  { repo: 'acme/web', number: 9, title: 'Clash', conflicts: true },
  { repo: 'acme/web', number: 10, title: 'Red', checks: 'failure', merge: 'blocked' },
  { repo: 'acme/web', number: 11, title: 'Auto', auto: true, merge: 'clean', checks: 'success' },
  { repo: 'acme/web', number: 12, title: 'Waiting', merge: 'clean', checks: 'running' },
  { repo: 'gitlab:g/app', provider: 'gitlab', number: 2, title: 'MR', merge: 'mergeable', checks: 'success' },
]
const approvals = [{ repo: 'acme/api', id: 5, name: 'Deploy', waits_for: 'production' }, { repo: 'acme/x', id: 6, name: 'Rel', waits_for: 'release', blocked: 'self-review' }]
const releases = [
  { repo: 'acme/a', release: 'v1', version: { todo: true, version: '1.1.0', file: 'pyproject.toml' }, problems: [] },
  { repo: 'acme/b', release: 'v2', run: 'failure 3d ago', problems: [] },
  { repo: 'acme/c', release: 'v3', problems: ['missing *.zip'] },
  { repo: 'acme/d', release: 'v4', busy: true, version: { todo: true, version: '9' }, problems: [] },
]
const items = todoItems({ status, prs, approvals, releases })
const find = (pred) => items.find(pred)

test('approvals first, then what is broken, then what is ready, then drift and releases', () => {
  const ranks = items.map((i) => i.rank)
  assert.deepEqual(ranks, [...ranks].sort((a, b) => a - b))
  assert.equal(items[0].rank, 1)
})

test('each kind of item, with where it opens', () => {
  assert.deepEqual(find((i) => i.why === 'waits for your approval').target, { kind: 'run', repo: 'acme/api', id: 5 })
  assert.equal(find((i) => i.target.repo === 'acme/x').cls, 'bad')
  assert.deepEqual(find((i) => i.why === 'CI fails on the default branch').target, { kind: 'repo', repo: 'acme/api' })
  assert.deepEqual(find((i) => i.why === 'has merge conflicts').target, { kind: 'pr', repo: 'acme/web', number: 9 })
  assert.ok(find((i) => i.why === 'checks fail' && i.target.number === 10))
  assert.deepEqual(items.filter((i) => i.why === 'ready to merge').map((i) => i.what), ['acme/web#7 Add login', 'gitlab:g/app!2 MR'])
  assert.ok(find((i) => i.why === '3 drift issues against the defaults' && i.repo === 'acme/web'))
  assert.ok(find((i) => i.why === 'the defaults check failed' && i.repo === 'mike/x'))
  assert.ok(find((i) => i.why === '1.1.0 is not released yet' && i.target.kind === 'release'))
  assert.ok(find((i) => i.why === 'the last release run failed' && i.repo === 'acme/b'))
  assert.ok(find((i) => i.why === 'missing *.zip' && i.repo === 'acme/c'))
})

test('drafts, auto-merge on, running checks, a release run going and fine repos are not to do', () => {
  for (const n of [8, 11, 12]) assert.ok(!find((i) => i.target.number === n), `#${n}`)
  assert.ok(!find((i) => i.repo === 'acme/d'))
  assert.ok(!find((i) => i.repo === 'acme/api' && i.what === 'defaults'))
  assert.deepEqual(todoItems(), [])
})
