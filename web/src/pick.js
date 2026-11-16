// Picking several rows of a list (space, or the boxes in the first column) to act on them at once. No imports,
// so node --test can run it (web/test/pick.test.js).

// keys with `key` in or out
export function toggle(picked, key) {
  return picked.includes(key) ? picked.filter((k) => k !== key) : [...picked, key]
}

// the header box: all of `shown` picked, or (when they all were) none of them; picks of rows the filter hides stay
export function toggleAll(picked, shown) {
  const all = shown.length > 0 && shown.every((k) => picked.includes(k))
  if (all) return picked.filter((k) => !shown.includes(k))
  return [...picked, ...shown.filter((k) => !picked.includes(k))]
}

// shift+click: every row from the last one clicked to this one, in the list's order
export function range(picked, order, from, to) {
  const a = order.indexOf(from)
  const b = order.indexOf(to)
  if (a < 0 || b < 0) return toggle(picked, to)
  const span = order.slice(Math.min(a, b), Math.max(a, b) + 1)
  return [...picked, ...span.filter((k) => !picked.includes(k))]
}

// the picks that are still rows (a merged PR leaves the list, and its pick with it)
export const alive = (picked, keys) => picked.filter((k) => keys.includes(k))
