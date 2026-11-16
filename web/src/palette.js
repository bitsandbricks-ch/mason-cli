// The finder (Ctrl+K): one box for views, repos, pull requests and commands. The matching lives here, without
// Vue, so node --test can check it.

// How well one word of the query fits a text: 0 is no match. A match at the start beats one at a word start
// (after / # : . _ - or a space), which beats one inside a word, which beats letters in order ("mw" ~ "mason-web").
export function score(word, text) {
  const q = String(word || '').toLowerCase()
  const t = String(text || '').toLowerCase()
  if (!q) return 1
  if (!t) return 0
  const at = t.indexOf(q)
  if (at === 0) return 100 - Math.min(t.length, 99) / 100
  if (at > 0) return (/[\s/#:._-]/.test(t[at - 1]) ? 80 : 60) - Math.min(at, 99) / 100
  let i = 0
  let gaps = 0
  let last = -1
  for (let j = 0; j < t.length && i < q.length; j++) {
    if (t[j] !== q[i]) continue
    if (last >= 0) gaps += j - last - 1
    last = j
    i++
  }
  return i === q.length ? Math.max(1, 40 - gaps) : 0
}

// Every word must fit the label (or, worth less, the hint). The kinds keep their order on a tie, so a view
// named like a repo comes first. items: [{kind, label, hint}].
export function search(items, query, limit = 40) {
  const words = String(query || '').trim().split(/\s+/).filter(Boolean)
  if (!words.length) return items.slice(0, limit)
  const out = []
  items.forEach((item, i) => {
    let total = 0
    for (const w of words) {
      const s = Math.max(score(w, item.label), score(w, item.hint) / 2)
      if (!s) return
      total += s
    }
    out.push({ item, total, i })
  })
  out.sort((a, b) => b.total - a.total || a.i - b.i)
  return out.slice(0, limit).map((x) => x.item)
}

// The last picks, newest first, without repeats: what the finder shows before you type.
export function remember(list, id, max = 8) {
  return [id, ...(list || []).filter((x) => x !== id)].slice(0, max)
}
