// "to do": what across your repos waits for you, from the lists the other views read, most urgent first. Each
// item says what it is, why it is here, and where it opens (a side panel target, see panel.js). No imports, so
// node --test can run it (web/test/todo.test.js).

const FAILED = /^(failure|failed|error|timed_out|startup_failure)$/i

// rank: lower comes first. 1 something waits for you to act, 2 broken, 3 ready to go, 4 drift and releases,
// 5 open issues assigned to you (issues: the list of /issues?mine=1; now: for their age, a test passes its own)
// me: your logins (a PR that asks one of them for a review waits for you)
export function todoItems({ status = null, prs = [], approvals = [], releases = [], issues = [], me = [], now = Date.now() } = {}) {
  const out = []
  const add = (rank, why, what, target, cls = 'warn') => out.push({ rank, why, what, repo: target.repo, target, cls })
  const ref = (p) => `${p.repo}${p.provider === 'gitlab' ? '!' : '#'}${p.number}`

  for (const a of approvals) {
    if (!a?.repo || !a.id) continue
    // a GitLab deployment or manual job has no page of its own: its repo's
    const target = !a.kind || a.kind === 'run' ? { kind: 'run', repo: a.repo, id: a.id } : { kind: 'repo', repo: a.repo }
    // one you can't approve doesn't wait for you: it is stuck, so it goes with what is broken
    add(a.blocked ? 2 : 1, a.blocked ? 'waits, but you can\'t approve it' : 'waits for your approval', `${a.name || 'run'} → ${a.waits_for || 'an environment'}`,
      target, a.blocked ? 'bad' : 'warn')
  }

  const head = status?.head || []
  const ci = head.indexOf('CI')
  for (const r of status?.rows || []) {
    if (ci >= 0 && FAILED.test(String(r.cells?.[ci] || ''))) add(2, 'CI fails on the default branch', 'CI', { kind: 'repo', repo: r.repo }, 'bad')
  }

  for (const p of prs) {
    if (!p?.repo || !p.number || p.draft) continue
    const target = { kind: 'pr', repo: p.repo, number: p.number }
    const mine = new Set(me.map((x) => String(x).toLowerCase()))
    if ((p.reviewers || []).some((r) => mine.has(String(r).toLowerCase()))) {
      add(1, 'asks for your review', `${ref(p)} ${p.title || ''}`.trim(), target)
      continue
    }
    if (p.conflicts) add(2, 'has merge conflicts', `${ref(p)} ${p.title || ''}`.trim(), target, 'bad')
    else if (FAILED.test(String(p.checks || ''))) add(2, 'checks fail', `${ref(p)} ${p.title || ''}`.trim(), target, 'bad')
    else if (/changes requested/i.test(String(p.review || ''))) add(2, 'changes requested', `${ref(p)} ${p.title || ''}`.trim(), target, 'warn')
    else if (!p.auto && /^(clean|mergeable|ready|has_hooks|unstable)$/i.test(String(p.merge || '')) && !/^(pending|running|queued)/i.test(String(p.checks || ''))) {
      add(3, 'ready to merge', `${ref(p)} ${p.title || ''}`.trim(), target, 'ok')
    }
  }

  for (const [repo, d] of Object.entries(status?.doctor || {})) {
    if (d?.error) add(4, 'the defaults check failed', 'defaults', { kind: 'repo', repo }, 'bad')
    else if (d && !d.ok && d.issues) add(4, `${d.issues} drift issue${d.issues === 1 ? '' : 's'} against the defaults`, 'defaults', { kind: 'repo', repo })
  }

  for (const r of releases) {
    if (!r?.repo) continue
    const v = r.version
    if (r.busy) continue // a release run is going: nothing to do yet
    if (FAILED.test(String(r.run || '').split(/\s/)[0])) add(2, 'the last release run failed', r.release || 'release', { kind: 'release', repo: r.repo }, 'bad')
    else if (v?.todo) add(4, `${v.version} is not released yet`, v.file || 'version', { kind: 'release', repo: r.repo })
    else if ((r.problems || []).length) add(4, r.problems[0], r.release || 'release', { kind: 'release', repo: r.repo })
  }

  for (const i of issues) {
    if (!i?.repo || !i.number || (i.state && i.state !== 'open')) continue
    const days = i.updated ? Math.floor((now - new Date(i.updated)) / 86_400_000) : 0
    const target = { kind: 'issue', repo: i.repo, number: i.number }
    add(5, days >= 30 ? `assigned to you, untouched ${days}d` : 'assigned to you', `${i.repo}#${i.number} ${i.title || ''}`.trim(), target, days >= 30 ? 'warn' : '')
  }

  return out.sort((a, b) => a.rank - b.rank || a.repo.localeCompare(b.repo))
}

export const RANKS = { 1: 'waits for you', 2: 'broken', 3: 'ready to go', 4: 'drift and releases', 5: 'your issues' }

// What is new since your last look: keys not in seen ({key: when last listed}). The first look (no seen yet)
// marks nothing, or everything would be "new". Returns the new keys and the seen map to keep: this list's keys
// as of now, plus older ones (other filters) from the last `keepDays` days.
export function sinceLastLook(keys, seen, { now = Date.now(), keepDays = 30, before = [] } = {}) {
  const fresh = seen ? keys.filter((k) => !(k in seen) || before.includes(k)) : []
  const next = {}
  const oldest = now - keepDays * 86_400_000
  for (const [k, at] of Object.entries(seen || {})) if (at >= oldest) next[k] = at
  for (const k of keys) next[k] = now
  return { fresh, seen: next }
}

// Items you put off ("later", z): {key: until}. Returns the keys still put off and the map to keep, without the
// ones whose time is up, so an item comes back by itself.
export function laterOf(later, now = Date.now()) {
  const keep = {}
  for (const [k, until] of Object.entries(later || {})) if (until > now) keep[k] = until
  return { hidden: new Set(Object.keys(keep)), later: keep }
}
