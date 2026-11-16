// node --test (npm test): which links from data may become an href.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { safeNext, safeUrl } from '../src/links.js'

test('http and https links pass', () => {
  assert.equal(safeUrl('https://github.com/acme/web/pull/7'), 'https://github.com/acme/web/pull/7')
  assert.equal(safeUrl(' http://example.com '), 'http://example.com')
})

test('anything else is no link', () => {
  for (const bad of ['javascript:alert(1)', 'JavaScript:alert(1)', ' javascript:x', 'data:text/html,x', 'vbscript:x',
    '//evil.example', '/local', 'https:/x', 'https:// x', '', null, undefined, 42]) {
    assert.equal(safeUrl(bad), '', String(bad))
  }
})

test('after signing in, only paths on this site', () => {
  assert.equal(safeNext('/prs?group=acme/'), '/prs?group=acme/')
  for (const bad of ['//evil.example', '/\t/evil.example', '/\\evil', 'https://evil.example', '/a b', '', null]) {
    assert.equal(safeNext(bad), '/', String(bad))
  }
})
