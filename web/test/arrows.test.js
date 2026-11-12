// node --test (npm test): arrow keys with nothing focused, on a list and on a detail page, with stand-in elements.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { arrowKey, nextTop, ownsArrows, pickPane } from '../src/arrows.js'

class Key {
  constructor(type, { key, shiftKey = false } = {}) { this.type = type; this.key = key; this.shiftKey = shiftKey; this.prevented = false }
  preventDefault() { this.prevented = true }
}

// an element: just what arrows.js reads
function el(tag, { cls = '', attrs = {}, kids = [], scroll = null, overflowY = 'visible' } = {}) {
  const me = {
    tag, cls, attrs, kids, parent: null, overflowY, events: [], focused: false,
    scrollTop: 0, scrollHeight: scroll?.[0] ?? 0, clientHeight: scroll?.[1] ?? 0, clientWidth: scroll?.[2] ?? 100,
    matches(sel) {
      return sel.split(',').map((s) => s.trim()).some((s) => {
        if (s === 'table.table') return tag === 'table' && cls === 'table'
        if (s === 'table.table[tabindex]') return tag === 'table' && cls === 'table' && 'tabindex' in attrs
        if (s.startsWith('[role=')) return attrs.role === s.slice(7, -2)
        return s === tag
      })
    },
    closest(sel) { for (let n = me; n; n = n.parent) if (n.matches(sel)) return n; return null },
    all() { return kids.flatMap((k) => [k, ...k.all()]) },
    querySelectorAll(sel) { return sel === '*' ? me.all() : me.all().filter((k) => k.matches(sel)) },
    querySelector(sel) { return me.querySelectorAll(sel)[0] || null },
    contains(n) { for (; n; n = n.parent) if (n === me) return true; return false },
    focus() { doc.activeElement = me },
    dispatchEvent(ev) { me.events.push(ev.key) },
  }
  kids.forEach((k) => { k.parent = me })
  return me
}
let doc
function page(main) {
  const body = el('body', { kids: [main] })
  doc = { body, activeElement: body, querySelector: (s) => body.querySelector(s), defaultView: { getComputedStyle: (e) => ({ overflowY: e.overflowY }) } }
  return doc
}

test('a list gets ↓ when nothing is focused, and keeps the focus', () => {
  const table = el('table', { cls: 'table', attrs: { tabindex: '0' } })
  const d = page(el('main', { kids: [table] }))
  const e = new Key('keydown', { key: 'ArrowDown' })
  assert.equal(arrowKey(e, d), true)
  assert.equal(d.activeElement, table)
  assert.deepEqual(table.events, ['ArrowDown'])
  assert.ok(e.prevented)
})

test('a repo page scrolls its pane on ↓ ↑ PageDown End Home', () => {
  const actions = el('div', { scroll: [1200, 600, 500], overflowY: 'auto' })
  const right = el('div', { scroll: [300, 600, 700], overflowY: 'auto' }) // fits: nothing to scroll
  const d = page(el('main', { kids: [el('div', { cls: 'split', kids: [actions, right] })] }))
  const press = (key) => arrowKey(new Key('keydown', { key }), d)
  assert.equal(press('ArrowDown'), true)
  assert.equal(actions.scrollTop, 40)
  press('ArrowUp'); press('ArrowUp')
  assert.equal(actions.scrollTop, 0)
  press('PageDown')
  assert.equal(actions.scrollTop, 540)
  press('End')
  assert.equal(actions.scrollTop, 600)
  press('Home')
  assert.equal(actions.scrollTop, 0)
})

test('the pane under the pointer wins, else the one with the most to scroll', () => {
  const big = el('div', { scroll: [2000, 600, 800], overflowY: 'auto' })
  const inner = el('span')
  const log = el('div', { scroll: [900, 200, 800], overflowY: 'auto', kids: [inner] })
  const d = page(el('main', { kids: [big, log] }))
  arrowKey(new Key('keydown', { key: 'ArrowDown' }), d, inner)
  assert.equal(log.scrollTop, 40)
  assert.equal(big.scrollTop, 0)
  assert.equal(pickPane([big, log], null), big)
  // a short screen: the actions pane is a small box with a lot below, the event log a wide band with a little
  const actions = el('div', { scroll: [1551, 90, 559] })
  const band = el('div', { scroll: [215, 169, 1400] })
  assert.equal(pickPane([actions, band], null), actions)
})

test('keys stay with what takes them: inputs, a focused list, a dialog, other keys, shift', () => {
  const input = el('input')
  const table = el('table', { cls: 'table', attrs: { tabindex: '0' } })
  const pane = el('div', { scroll: [1200, 600], overflowY: 'auto', kids: [input] })
  const d = page(el('main', { kids: [pane, table] }))
  d.activeElement = input
  assert.equal(arrowKey(new Key('keydown', { key: 'ArrowDown' }), d), false)
  d.activeElement = table
  assert.equal(arrowKey(new Key('keydown', { key: 'ArrowDown' }), d), false)
  assert.deepEqual(table.events, []) // the table's own handler does it
  d.activeElement = d.body
  assert.equal(arrowKey(new Key('keydown', { key: 'ArrowLeft' }), d), false)
  assert.equal(arrowKey(new Key('keydown', { key: 'ArrowDown', shiftKey: true }), d), false)
  assert.ok(ownsArrows(el('div', { attrs: { role: 'dialog' } })))
  assert.ok(!ownsArrows(el('button')))
})

test('a focused button hands the keys on (a clicked action keeps focus)', () => {
  const button = el('button')
  const pane = el('div', { scroll: [1200, 600], overflowY: 'auto', kids: [button] })
  const d = page(el('main', { kids: [pane] }))
  d.activeElement = button
  assert.equal(arrowKey(new Key('keydown', { key: 'ArrowDown' }), d), true)
  assert.equal(pane.scrollTop, 40)
})

test('scrolling stops at both ends', () => {
  assert.equal(nextTop('ArrowUp', 10, 500, 900), 0)
  assert.equal(nextTop('ArrowDown', 890, 500, 900), 900)
  assert.equal(nextTop('PageUp', 100, 500, 900), 0)
})
