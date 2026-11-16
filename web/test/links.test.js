// node --test (npm test): which outside URLs become links.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { openOut, safeHref } from '../src/links.js'

test('only http and https URLs are links', () => {
  assert.equal(safeHref('https://github.com/acme/web'), 'https://github.com/acme/web')
  assert.equal(safeHref(' http://example.com/x '), 'http://example.com/x')
  assert.equal(safeHref('HTTPS://EXAMPLE.COM'), 'HTTPS://EXAMPLE.COM')
  for (const bad of ['javascript:alert(1)', ' JavaScript:alert(1)', 'data:text/html,hi', 'file:///etc/passwd', '//evil.example',
    '/relative', 'https://', 'https:///x', '', null, undefined, 'vbscript:x']) {
    assert.equal(safeHref(bad), '', String(bad))
  }
})

test('openOut opens good links in a new tab, without the opener, and nothing else', () => {
  const opened = []
  const win = { open: (...a) => opened.push(a) }
  assert.equal(openOut('https://example.com/a', win), true)
  assert.equal(openOut('javascript:alert(1)', win), false)
  assert.equal(openOut(undefined, win), false)
  assert.deepEqual(opened, [['https://example.com/a', '_blank', 'noopener']])
})
