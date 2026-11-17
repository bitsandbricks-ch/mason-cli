// node --test (npm test): changes to many rows at once.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { BULK_MAX, bulkQuestion, rerunnable } from '../src/bulk.js'

const run = (repo, name, state, created, id) => ({ repo, name, state, created, id })

test('only failed runs, and only the newest of each repo and workflow', () => {
  const runs = [
    run('acme/web', 'CI', 'failure', '2026-11-01', 1),
    run('acme/web', 'CI', 'success', '2026-11-02', 2), // fixed since: leave run 1 alone
    run('acme/api', 'CI', 'failure', '2026-11-02', 3),
    run('acme/api', 'Release', 'timed_out', '2026-11-02', 4),
    run('gitlab:grp/app', 'pipeline', 'failed', '2026-11-02', 5),
    run('acme/doc', 'CI', 'cancelled', '2026-11-02', 6),
    { repo: 'acme/x', error: 'no access' },
  ]
  assert.deepEqual(rerunnable(runs).map((r) => r.id), [3, 4, 5])
})

test('the question counts and lists them, up to the limit', () => {
  const rows = Array.from({ length: BULK_MAX + 2 }, (_, i) => ({ repo: `a/${i}` }))
  const q = bulkQuestion('Run the failed jobs again', 'run', rows, (r) => r.repo)
  assert.equal(q.question, `Run the failed jobs again: ${BULK_MAX} runs?`)
  assert.equal(q.detail.split('\n').length, BULK_MAX + 1)
  assert.match(q.detail, /and 2 more/)
  assert.equal(bulkQuestion('Rerun', 'run', [{ repo: 'a/b' }], (r) => r.repo).question, 'Rerun: 1 run?')
})
