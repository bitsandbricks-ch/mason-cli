// A list's filters in its link (?state=closed&mine=1), so a bookmark, a shared link or a saved view opens the
// same list. Each filter has a default; only the ones that differ go in the link, and a value the list doesn't
// offer falls back to the default (a hand-edited link can't put a list in a state its menus can't show).
// spec: { name: { def, ok?: (value) => bool } }; the type of def says how to read the link (bool, number, string).

function read(raw, { def, ok }) {
  if (raw == null || Array.isArray(raw)) return def
  let v = raw
  if (typeof def === 'boolean') v = raw === '1' || raw === 'true'
  else if (typeof def === 'number') { v = Number(raw); if (!Number.isFinite(v)) return def }
  return !ok || ok(v) ? v : def
}

// The filters a route query asks for, every one of them set (defaults where the link says nothing).
export function fromQuery(query, spec) {
  const out = {}
  for (const [k, s] of Object.entries(spec)) out[k] = read(query?.[k], s)
  return out
}

// The route query for these filters: the other keys of query kept, a filter at its default left out.
export function toQuery(values, spec, query = {}) {
  const out = { ...query }
  for (const [k, s] of Object.entries(spec)) {
    const v = values[k]
    if (v === s.def || v == null || v === '') delete out[k]
    else out[k] = typeof v === 'boolean' ? '1' : String(v)
  }
  return out
}

// Whether two route queries say the same (so a replace that changes nothing is skipped).
export function sameQuery(a, b) {
  const ka = Object.keys(a || {}).filter((k) => a[k] != null)
  const kb = Object.keys(b || {}).filter((k) => b[k] != null)
  return ka.length === kb.length && ka.every((k) => String(a[k]) === String(b?.[k]))
}
