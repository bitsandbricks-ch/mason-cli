// The jump box (ctrl+k): type a few letters of a repo, a PR, an issue or a view and go there. The matching is a
// loose one, like an editor's file finder: the letters in order, and better when they start a word or follow
// each other. No imports, so node --test can run it (web/test/palette.test.js).

// how well `query` matches `text`: 0 for not at all, higher for better
export function score(query, text) {
  const q = String(query || '').toLowerCase().replace(/\s+/g, '')
  const t = String(text || '').toLowerCase()
  if (!q) return 1
  if (!t) return 0
  let at = 0
  let total = 0
  let run = 0
  for (const ch of q) {
    const i = t.indexOf(ch, at)
    if (i < 0) return 0
    run = i === at && at > 0 ? run + 1 : 0
    const start = i === 0 || /[\s/#!:._-]/.test(t[i - 1])
    total += 1 + (start ? 3 : 0) + run * 2 - Math.min(i - at, 5) * 0.2
    at = i + 1
  }
  const whole = t.includes(q) ? 4 + (t.startsWith(q) ? 4 : 0) : 0
  return total + whole + 10 / (t.length + 1)
}

// items [{label, hint?, kind}] best first, at most `limit`; an item's label counts more than its hint
export function rank(items, query, limit = 12) {
  const out = []
  for (const it of items) {
    // the hint only as a whole word or part of one: scattered letters in a long hint matched nearly anything
    const q = String(query || '').toLowerCase().trim()
    const inHint = q && String(it.hint || '').toLowerCase().includes(q)
    const s = Math.max(score(query, it.label), inHint ? score(query, it.hint) * 0.6 : 0)
    if (s > 0) out.push({ it, s })
  }
  out.sort((a, b) => b.s - a.s || (KIND_ORDER[a.it.kind] ?? 9) - (KIND_ORDER[b.it.kind] ?? 9))
  return out.slice(0, limit).map((x) => x.it)
}
const KIND_ORDER = { view: 0, repo: 1, pr: 2, issue: 3, command: 4 }

// what the API's lists hold, as jump targets
export function itemsFrom({ views = [], repos = [], prs = [], issues = [] }) {
  const ref = (r, n) => `${r}${String(r).startsWith('gitlab:') ? '!' : '#'}${n}`
  return [
    ...views.map((v) => ({ kind: 'view', label: v.label, hint: v.hint, to: { path: v.path } })),
    ...repos.map((r) => ({ kind: 'repo', label: r, to: { path: '/repo', query: { repo: r } } })),
    ...prs.map((p) => ({ kind: 'pr', label: `${ref(p.repo, p.number)} ${p.title || ''}`.trim(), hint: p.author || '',
      to: { path: '/pr', query: { repo: p.repo, number: String(p.number) } } })),
    ...issues.map((i) => ({ kind: 'issue', label: `${i.repo}#${i.number} ${i.title || ''}`.trim(), hint: (i.labels || []).join(' '),
      to: { path: '/issue', query: { repo: i.repo, number: String(i.number) } } })),
  ]
}

// the things you opened last (a repo, a PR…), newest first, each once, at most max: what the jump box offers
// before you type
export function remember(list, target, max = 8) {
  const key = (t) => `${t.kind}:${t.repo}:${t.number ?? t.id ?? t.tag ?? ''}`
  if (!target?.kind || !target.repo) return list
  return [target, ...list.filter((t) => key(t) !== key(target))].slice(0, max)
}

// a remembered target as a jump box item (it goes where it went before; a PR's title is in the lists, not here)
export function recentItem(t) {
  const ref = t.number ? `${t.repo}${t.kind === 'pr' && t.repo.startsWith('gitlab:') ? '!' : '#'}${t.number}` : t.id ? `${t.repo} run ${t.id}` : t.tag ? `${t.repo} ${t.tag}` : t.repo
  return { kind: 'recent', label: ref, hint: { repo: 'repo', pr: 'pull request', issue: 'issue', run: 'run', release: 'releases' }[t.kind] || '', target: t }
}
