// Small page helpers shared by every kind of study.
export const $ = id => document.getElementById(id)

export function status(id, text, tone = 'busy') {
  const el = $(id)
  delete el.dataset.count
  el.hidden = !text
  el.textContent = text || ''
  el.className = `status ${tone}`
}
// After a press with problems left: how many remain, gone once they are fixed.
export function countStatus(id, count) {
  if (count) { status(id, count === 1 ? 'One thing needs fixing first.' : `${count} things need fixing first.`, 'bad'); $(id).dataset.count = '' }
  else if ($(id).dataset.count !== undefined) status(id, '')
}
// Server refusals arrive as "code: message Request: id." Keep the message and the request id
// (it matches the server log); a lost session is explained once, by the notice at the top.
export function readable(error) {
  if (error?.status === 401) return 'Your private session ended. Reconnect at the top of the page, then try again.'
  return String(error?.message || 'Something went wrong.').replace(/^[a-z0-9_]+: /, '')
}
export function failure(id, error) {
  status(id, readable(error), 'bad')
}

export function size(id, cap = 380) {
  const width = Math.round($(id).getBoundingClientRect().width) || 720
  return { width, height: Math.round(Math.max(220, Math.min(cap, window.innerHeight - 470, width * 0.62))) }
}

export function saveBytes(name, bytes, type) {
  const url = URL.createObjectURL(new Blob([bytes], { type }))
  const link = Object.assign(document.createElement('a'), { href: url, download: name })
  document.body.append(link); link.click(); link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}
export const saveText = (name, text, type) => saveBytes(name, text, type)
