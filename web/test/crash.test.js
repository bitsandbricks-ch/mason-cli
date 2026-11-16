import { test } from 'node:test'
import assert from 'node:assert/strict'
import { crashText, isStaleBuild, mayReload } from '../src/crash.js'

test('the browsers\' words for a file of an old build', () => {
  assert.ok(isStaleBuild(new TypeError('Failed to fetch dynamically imported module: https://x/assets/Prs-abc.js')))
  assert.ok(isStaleBuild(new TypeError('error loading dynamically imported module')))
  assert.ok(isStaleBuild(new TypeError('Importing a module script failed.')))
  assert.ok(isStaleBuild(new Error('Unable to preload CSS for /assets/Prs-abc.css')))
  assert.ok(!isStaleBuild(new Error('rows is undefined')))
  assert.ok(!isStaleBuild(undefined))
})

test('a reload at most once a minute', () => {
  const kept = new Map()
  const storage = { getItem: (k) => kept.get(k) ?? null, setItem: (k, v) => kept.set(k, v) }
  assert.ok(mayReload(storage, 1_000_000))
  assert.ok(!mayReload(storage, 1_030_000))
  assert.ok(mayReload(storage, 1_061_000))
})

test('a reload without storage still happens', () => {
  const broken = { getItem: () => { throw new Error('denied') }, setItem: () => { throw new Error('denied') } }
  assert.ok(mayReload(broken, 1_000_000))
  assert.ok(mayReload(undefined, 1_000_000))
})

test('a bug reads as one line', () => {
  assert.equal(crashText(new Error('x is undefined\n  at foo')).split('\n').length, 1)
  assert.equal(crashText(new Error('x is undefined')), 'something went wrong on this page: x is undefined. Reloading the page starts over')
  assert.match(crashText('boom'), /: boom\./)
})
