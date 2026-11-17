import { test } from 'node:test'
import assert from 'node:assert/strict'
import { dismiss, toast, toasts, working } from '../src/toast.js'

const clear = () => [...toasts].forEach((t) => dismiss(t.id))

test('a change shows working, then its result in the same toast', () => {
  clear()
  const w = working('Fix the drift of acme/web')
  assert.equal(toasts.length, 1)
  assert.equal(toasts[0].kind, 'busy')
  assert.equal(toasts[0].text, 'Fix the drift of acme/web…')
  w.done('Fix the drift of acme/web: done', 'ok', { detail: 'fixed 3' })
  assert.equal(toasts.length, 1)
  assert.deepEqual([toasts[0].kind, toasts[0].detail], ['ok', 'fixed 3'])
  clear()
})

test('the same text again does not stack, and old finished ones go first', () => {
  clear()
  toast('saved', 'ok'); toast('saved', 'ok')
  assert.equal(toasts.length, 1)
  const busy = working('long one')
  for (let i = 0; i < 6; i++) toast(`t${i}`, 'error')
  assert.equal(toasts.length, 4)
  assert.ok(toasts.some((t) => t.id === busy.id), 'one still working stays')
  assert.equal(toasts[0].text, 't5')
  clear()
})
