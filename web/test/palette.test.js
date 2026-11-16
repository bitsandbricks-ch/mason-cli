// node --test (npm test): the jump box's matching and ranking.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { itemsFrom, rank, score } from '../src/palette.js'

test('letters in order match, others do not', () => {
  assert.ok(score('aw', 'acme/web') > 0)
  assert.ok(score('acme web', 'acme/web') > 0) // spaces don't count
  assert.equal(score('wa', 'web'), 0)
  assert.equal(score('x', 'acme/web'), 0)
  assert.ok(score('', 'anything') > 0)
})

test('a match at the start of a word, and one in a row, beat scattered letters', () => {
  assert.ok(score('web', 'acme/web') > score('web', 'acme/wide-label-bundle'))
  assert.ok(score('pr', 'pull requests') < score('pr', 'prs'))
  assert.ok(score('api', 'acme/api') > score('api', 'acme/plugin-a-pi'))
})

const items = itemsFrom({
  views: [{ label: 'pull requests', hint: 'open pull and merge requests', path: '/prs' }, { label: 'releases', hint: 'latest', path: '/releases' }],
  repos: ['acme/web', 'acme/api', 'gitlab:grp/app'],
  prs: [{ repo: 'acme/web', number: 7, title: 'Add login page', author: 'ann' }, { repo: 'gitlab:grp/app', number: 2, title: 'Fix', author: 'bob' }],
  issues: [{ repo: 'acme/web', number: 3, title: 'Login fails on Safari', labels: ['bug'] }],
})

test('items carry where they go, GitLab MRs with !', () => {
  assert.deepEqual(items.find((i) => i.kind === 'pr').to, { path: '/pr', query: { repo: 'acme/web', number: '7' } })
  assert.ok(items.some((i) => i.label === 'gitlab:grp/app!2 Fix'))
  assert.deepEqual(items.find((i) => i.kind === 'repo').to, { path: '/repo', query: { repo: 'acme/web' } })
  assert.deepEqual(items.find((i) => i.kind === 'view').to, { path: '/prs' })
})

test('ranking: the best match first, the hint counts less, a limit', () => {
  assert.equal(rank(items, 'acme/api')[0].label, 'acme/api')
  assert.equal(rank(items, 'login').length, 2) // the PR and the issue
  assert.ok(rank(items, 'safari').every((i) => i.kind === 'issue'))
  assert.equal(rank(items, 'rel')[0].label, 'releases')
  assert.equal(rank(items, '', 3).length, 3)
  assert.deepEqual(rank(items, 'zzz'), [])
  assert.ok(rank(items, 'bug').some((i) => i.kind === 'issue')) // through the hint
  assert.ok(!rank(items, 'login').some((i) => i.kind === 'view')) // not 'open puLl and merGe requests'… scattered in a hint
})

test('recent: newest first, each once, at most max', async () => {
  const { remember, recentItem } = await import('../src/palette.js')
  let list = []
  list = remember(list, { kind: 'repo', repo: 'a/b' })
  list = remember(list, { kind: 'pr', repo: 'a/b', number: 7 })
  list = remember(list, { kind: 'repo', repo: 'a/b' })
  assert.deepEqual(list.map((t) => t.kind), ['repo', 'pr'])
  for (let i = 0; i < 20; i++) list = remember(list, { kind: 'issue', repo: 'a/b', number: i + 1 }, 5)
  assert.equal(list.length, 5)
  assert.equal(list[0].number, 20)
  assert.equal(remember(list, null), list)
  assert.equal(recentItem({ kind: 'pr', repo: 'gitlab:g/a', number: 2 }).label, 'gitlab:g/a!2')
  assert.equal(recentItem({ kind: 'run', repo: 'a/b', id: 9 }).label, 'a/b run 9')
})
