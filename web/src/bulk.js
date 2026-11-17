// Changes to many rows at once, one request each, with one question up front. The rules are pure, for
// node --test.

export const BULK_MAX = 30 // one click shouldn't fire hundreds of writes at GitHub

// runs worth running again: failed ones (GitHub "failure"/"timed_out", GitLab "failed"), newest per repo and
// workflow only, so an old failure that a later run fixed isn't run again
export function rerunnable(runs) {
  const newest = new Map()
  for (const r of runs) {
    if (r.id == null || r.error) continue
    const k = `${r.repo}|${r.name}`
    const at = newest.get(k)
    if (!at || String(r.created || '') > String(at.created || '')) newest.set(k, r)
  }
  return [...newest.values()].filter((r) => /^(failure|failed|timed_out)$/i.test(String(r.state || '')))
}

// ("Run the failed jobs again", "run", rows) -> "Run the failed jobs again: 3 runs?" and the list, for one question
export function bulkQuestion(verb, noun, rows, label) {
  const n = Math.min(rows.length, BULK_MAX)
  const more = rows.length > BULK_MAX ? `\n… and ${rows.length - BULK_MAX} more, for the next go` : ''
  return { question: `${verb}: ${n} ${noun}${n === 1 ? '' : 's'}?`, detail: rows.slice(0, BULK_MAX).map(label).join('\n') + more }
}
