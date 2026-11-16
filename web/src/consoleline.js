// The console's line before it is sent: whether it can change repos (so it asks first) and the dry-run switch.
// No imports, so node --test can run it (web/test/consoleline.test.js). The server decides for itself as well.

// the words the CLI reads as options: everything before a lone --
const options = (words) => { const i = words.indexOf('--'); return i < 0 ? words : words.slice(0, i) }
export const isDry = (words) => options(words).includes('--dry-run')

// writes: the CLI's writing commands; plugins: plugin commands, which may write too
export function prepare(line, { writes = new Set(), plugins = new Set(), dryRun = false } = {}) {
  let text = String(line || '').trim()
  const words = text.replace(/^mason\s+/, '').split(/\s+/).filter(Boolean)
  const cmd = words[0] || ''
  const writing = (writes.has(cmd) || plugins.has(cmd)) && !isDry(words)
  if (writing && dryRun) {
    // the header's dry-run switch is on: the line runs as a dry run, the flag before any --
    const at = text.search(/\s--(\s|$)/)
    text = at < 0 ? `${text} --dry-run` : `${text.slice(0, at)} --dry-run${text.slice(at)}`
    return { line: text, ask: false }
  }
  return { line: text, ask: writing }
}
