// node --test (npm test): lists as CSV.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { csvCell, csvName, toCsv } from '../src/csv.js'

test('quotes, commas and line breaks are quoted', () => {
  assert.equal(csvCell('plain'), 'plain')
  assert.equal(csvCell('a, b'), '"a, b"')
  assert.equal(csvCell('say "hi"'), '"say ""hi"""')
  assert.equal(csvCell('two\nlines'), '"two\nlines"')
  assert.equal(csvCell(null), '')
  assert.equal(csvCell(7), '7')
})

test('a cell that a spreadsheet would run as a formula is defused', () => {
  assert.equal(csvCell('=HYPERLINK("http://example.com")'), '"\'=HYPERLINK(""http://example.com"")"')
  assert.equal(csvCell('+1'), "'+1")
  assert.equal(csvCell('-x'), "'-x")
  assert.equal(csvCell('@sum'), "'@sum")
})

test('a header row from the labels (or keys), then the shown cells', () => {
  const cols = [{ key: 'repo', label: 'repo' }, { key: 'n', label: '#' }, { key: 'flags', label: '' }]
  const rows = [{ repo: 'acme/web', n: 7, flags: 'auto-merge' }]
  const got = toCsv(cols, rows, (c, r) => (c.key === 'n' ? `#${r.n}` : r[c.key]))
  assert.equal(got, 'repo,#,flags\r\nacme/web,#7,auto-merge\r\n')
})

test('the file name says what and when', () => {
  assert.equal(csvName('pull requests', new Date('2026-11-16T03:00:00Z')), 'mason-pull-requests-2026-11-16.csv')
  assert.equal(csvName('', new Date('2026-11-16T03:00:00Z')), 'mason-list-2026-11-16.csv')
})
