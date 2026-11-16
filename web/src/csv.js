// A list as CSV, the way it is shown (filtered, sorted, cells in words). Kept free of Vue for node --test.

// A cell that starts with = + - @ (or a tab or CR) would run as a formula in a spreadsheet; titles and branch
// names come from anyone who can open a PR, so such cells get a leading ' (OWASP's advice for CSV injection).
export function csvCell(value) {
  let s = String(value ?? '')
  if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

// columns: [{key, label}], rows: shown rows, cell(column, row): the shown text
export function toCsv(columns, rows, cell) {
  const lines = [columns.map((c) => csvCell(c.label || c.key)).join(',')]
  for (const r of rows) lines.push(columns.map((c) => csvCell(cell(c, r))).join(','))
  return lines.join('\r\n') + '\r\n'
}

// "mason-pull-requests-2026-11-16.csv"
export function csvName(what, now = new Date()) {
  const slug = String(what || 'list').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'list'
  return `mason-${slug}-${now.toISOString().slice(0, 10)}.csv`
}
