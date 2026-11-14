// Presentation only. No application imports, requests, timers that poll, or
// authority-bearing state. Content is visible without this module/WAAPI.
const mounted = new WeakMap()
export const MOTION = Object.freeze({ press: 120, panel: 220, event: 180, ease: 'cubic-bezier(.2,.8,.2,1)' })

export function installMotion(doc = document) {
  if (mounted.has(doc)) return mounted.get(doc)
  const win = doc.defaultView, reduced = win.matchMedia('(prefers-reduced-motion: reduce)')
  const active = new Set(), byElement = new WeakMap(), streams = new Map(), charts = new Set()
  let page = doc.querySelector('.page:not([hidden])'), frame = 0, disposed = false
  const visible = node => !node.closest('[hidden], details:not([open])')
  function play(node, frames, duration = MOTION.panel, delay = 0) {
    byElement.get(node)?.cancel()
    if (disposed || reduced.matches || doc.visibilityState === 'hidden' || !node.isConnected || !visible(node) || !node.animate) return
    const animation = node.animate(frames, { duration, delay, easing: MOTION.ease })
    byElement.set(node, animation); active.add(animation)
    const clean = () => { active.delete(animation); if (byElement.get(node) === animation) byElement.delete(node) }
    animation.addEventListener('finish', clean, { once: true })
    animation.addEventListener('cancel', clean, { once: true })
  }
  function cancel() { for (const animation of active) animation.cancel(); active.clear() }
  function revealCharts(scope) {
    for (const chart of scope.querySelectorAll('#backend-results .chart svg, #backend-next .mini-plot svg')) {
      if (!visible(chart)) continue
      // Geometry comes from already-returned evidence. No values are changed
      // and rebuilding an identical plot during polling does not animate it.
      const key = chart.outerHTML
      if (charts.has(key)) continue
      charts.add(key); if (charts.size > 64) charts.delete(charts.values().next().value)
      play(chart, [{ opacity: .85 }, { opacity: 1 }])
    }
  }
  function activity(list) {
    const key = list.dataset.motionStream
    if (!key) return
    let seen = streams.get(key), initial = !seen, count = 0
    if (!seen) { seen = new Set(); streams.set(key, seen) }
    for (const item of list.querySelectorAll('[data-motion-event]')) {
      const id = item.dataset.motionEvent
      if (!id || seen.has(id)) continue
      seen.add(id)
      // Existing/reopened history is immediately readable. Only newly joined
      // events on an established stream get bounded feedback.
      if (!initial && count < 4) play(item, [{ opacity: .85, transform: 'translateY(3px)' }, { opacity: 1, transform: 'none' }], MOTION.event, count++ * 24)
    }
    while (seen.size > 256) seen.delete(seen.values().next().value)
    while (streams.size > 24) streams.delete(streams.keys().next().value)
  }
  function navigate() {
    frame = 0
    const next = doc.querySelector('.page:not([hidden])')
    if (next && next !== page) {
      const order = [...doc.querySelectorAll('.page')], direction = order.indexOf(next) < order.indexOf(page) ? -1 : 1
      if (page) byElement.get(page)?.cancel()
      if (page) play(next, [{ opacity: .88, transform: `translateX(${direction * 6}px)` }, { opacity: 1, transform: 'none' }])
      page = next
    }
    if (next) revealCharts(next)
  }
  function scan(node) {
    if (node.nodeType !== 1) return
    if (node.matches('[data-motion-stream]')) activity(node)
    for (const list of node.querySelectorAll('[data-motion-stream]')) activity(list)
    const stream = node.closest('[data-motion-stream]')
    if (stream) activity(stream)
  }
  for (const list of doc.querySelectorAll('[data-motion-stream]')) activity(list)
  // Do not animate charts already on screen at installation/page load.
  for (const chart of doc.querySelectorAll('#backend-results .chart svg, #backend-next .mini-plot svg')) if (visible(chart)) charts.add(chart.outerHTML)
  const observer = new win.MutationObserver(records => {
    for (const record of records) for (const node of record.addedNodes) scan(node)
    if (!frame) frame = win.requestAnimationFrame(navigate)
  })
  observer.observe(doc.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['hidden'] })
  const preference = () => { if (reduced.matches) cancel() }
  const visibility = () => { if (doc.visibilityState === 'hidden') cancel() }
  function download(event) {
    const target = event.detail?.target
    if (!(target instanceof win.HTMLElement) || !target.matches('button, a[download]')) return
    // Caller emits this after bytes have been authenticated and saved. No
    // success is inferred from a click or elapsed time.
    play(target, [{ outlineColor: 'var(--ok)', outlineWidth: '2px', outlineStyle: 'solid', outlineOffset: '3px' }, { outlineColor: 'transparent', outlineWidth: '2px', outlineStyle: 'solid', outlineOffset: '3px' }])
  }
  reduced.addEventListener('change', preference)
  doc.addEventListener('visibilitychange', visibility)
  doc.addEventListener('bean:download-ready', download)
  doc.documentElement.dataset.motion = 'ready'
  const dispose = () => {
    disposed = true; observer.disconnect(); win.cancelAnimationFrame(frame); cancel()
    reduced.removeEventListener('change', preference); doc.removeEventListener('visibilitychange', visibility); doc.removeEventListener('bean:download-ready', download)
    delete doc.documentElement.dataset.motion; mounted.delete(doc)
  }
  mounted.set(doc, dispose)
  return dispose
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => installMotion(), { once: true })
  else installMotion()
}
