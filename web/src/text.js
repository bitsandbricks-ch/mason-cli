// Pure text helpers (no Vue, no router), so node --test can check them: times, links in text, status words,
// errors in plain words and fields of the CLI's detail text. ui.js re-exports them.

export function ago(stamp) {
  if (!stamp) return '-'
  const secs = (Date.now() - new Date(stamp.endsWith('Z') || stamp.includes('+') ? stamp : stamp + 'Z')) / 1000
  for (const [u, s] of [['d', 86400], ['h', 3600], ['m', 60]]) if (secs >= s) return `${Math.floor(secs / s)}${u} ago`
  return 'just now'
}

const URL_RE = /(https?:\/\/[^\s)\]>,'"]+)/g

// Text -> [{text}|{href,label}] so templates can render links without v-html.
export function linkify(text) {
  const t = String(text ?? '')
  const out = []
  let last = 0
  for (const m of t.matchAll(URL_RE)) {
    if (m.index > last) out.push({ text: t.slice(last, m.index) })
    out.push({ href: m[0], label: shortLink(m[0]) })
    last = m.index + m[0].length
  }
  if (last < t.length) out.push({ text: t.slice(last) })
  return out
}

export function shortLink(url) {
  return url.replace(/^https:\/\/(github\.com|gitlab\.com)\//, '').replace(/^https?:\/\//, '')
}

export function stateClass(value) {
  const v = String(value || '').toLowerCase()
  if (/^(success|passing|ok|approved|merged|verified|ready|green)/.test(v)) return 'ok'
  if (/(fail|error|conflict|critical|high|secret|denied|unverified|missing|blocked)/.test(v)) return 'bad'
  if (/(pending|running|waiting|draft|medium|moderate|manual|review)/.test(v)) return 'warn'
  return ''
}

// A status word's mark, so a column reads at a glance: ✓ fine, ✗ needs you, ● on its way.
export function glyph(cls) {
  return { ok: '✓', bad: '✗', warn: '●' }[cls] || ''
}

// An error from the API (often a gh or glab command's output) in plain words: {title, raw}. raw is the
// original, for a "details" toggle.
export function explain(message, what = '') {
  const raw = String(message || '').replace(/^error:\s*/i, '').trim()
  const lead = what ? `${what}: ` : ''
  const say = (t) => ({ title: lead + t, raw })
  if (/bad credentials|\b401\b|token.*(expired|revoked)|sign in again/i.test(raw)) return say('your sign-in has expired. Sign out and in again.')
  if (/rate limit|\b429\b/i.test(raw)) return say('the GitHub rate limit is used up. Try again in a few minutes.')
  // two 403s with their own way out: an org's SSO, and an org that restricts OAuth apps
  if (/saml|single sign-on|\bsso\b/i.test(raw)) return say('the org uses single sign-on: authorize your GitHub sign-in for it on GitHub, then try again.')
  if (/oauth app access restrictions|third-party application access/i.test(raw)) return say("the org hasn't approved Mason yet: an org owner can, in the org's third-party access settings.")
  if (/must have admin|admin rights|\b403\b|resource not accessible|forbidden|permission/i.test(raw)) return say("your account isn't allowed to do this here (it may need admin rights on the repo).")
  if (/no answer for|\b404\b|not found|could not resolve/i.test(raw)) return say("GitHub says it doesn't exist, or your account can't see it.")
  if (/connect gitlab/i.test(raw)) return say('connect GitLab under setup › settings first.')
  if (/timed? ?out|econn|network|failed to fetch|unreachable|can't reach/i.test(raw)) return say("couldn't reach the server. Check the connection and try again.")
  // no idea: the first line, without the command that printed it
  const first = raw.split('\n')[0].replace(/^(gh|glab) (api )?(-X \w+ )?\S+:\s*/, '').replace(/^[^:]{0,40}: (gh|glab) [^:]+: /, '')
  return { title: lead + (first.length > 160 ? first.slice(0, 157) + '…' : first || 'something went wrong'), raw }
}

// "  state    open, by ann" -> 'open, by ann': a field of a detail text (the CLI's layout)
export function fieldOf(text, name) {
  const re = new RegExp(`^\\s+${name}\\s`)
  return (String(text || '').split('\n').find((l) => re.test(l)) || '').trim().slice(name.length).trim()
}

// Whether a console line changes repos, so the console asks first: like the server's console.is_write, except
// that doctor always asks (a repo's auto_fix can make a plain check fix things).
export function consoleWrites(line, writes) {
  const argv = String(line || '').trim().replace(/^mason\s+/, '').split(/\s+/).filter(Boolean)
  const [cmd] = argv
  if (!cmd || argv.includes('--dry-run')) return false
  if (cmd === 'workflows') return argv.includes('--fix')
  if (cmd === 'issue') return argv[1] !== 'view'
  if (cmd === 'release') return !argv.includes('--list') && argv.slice(1).some((a) => !a.startsWith('-'))
  return writes.has(cmd)
}
