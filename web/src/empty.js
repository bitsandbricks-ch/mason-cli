// What an empty list says. "no open issues" was wrong when a filter or the group hid them: it said there were
// none at all, and nothing said why. With a filter on, it names the filters; with a group, the group.
// base: what the list says when nothing narrows it ("no open issues"; after a colon, a hint for that case).
// filters: the active filters in words (falsy ones are off). where: "in org acme", "on gitlab", '' for every repo.
export function emptyText(base, filters = [], where = '') {
  const on = filters.filter(Boolean)
  const at = where ? ` ${where}` : ''
  if (on.length) return `nothing matches ${on.join(' · ')}${at}: change or clear the filter`
  return where ? `${base.split(':')[0]}${at}` : base
}
