// Front end v1 motion and figures. Presentation only: no API calls, no state of its own,
// and nothing here changes what the shared modules in apps/web decide or send.
import { approx, axes, curvePath, el, scales } from './figure.mjs'

const reduce = matchMedia('(prefers-reduced-motion: reduce)')
const byId = id => document.getElementById(id)
const story = byId('story')

// 1. Reading progress, as a thin margin-red rule along the top.
const progress = document.createElement('div')
progress.className = 'scroll-progress'; progress.setAttribute('aria-hidden', 'true')
document.body.append(progress)
const updateProgress = () => {
  const max = document.documentElement.scrollHeight - innerHeight
  progress.style.setProperty('--progress', max > 0 ? Math.min(1, scrollY / max) : 0)
}
addEventListener('scroll', updateProgress, { passive: true }); addEventListener('resize', updateProgress)

// 2. Pages and headings settle into place the first time they scroll into view.
const revealer = 'IntersectionObserver' in window ? new IntersectionObserver(entries => {
  for (const entry of entries) if (entry.isIntersecting) { entry.target.classList.add('is-in'); revealer.unobserve(entry.target) }
}, { rootMargin: '0px 0px -8% 0px' }) : null
const seen = new WeakSet()
function reveal(root = document) {
  const targets = root.querySelectorAll('.section-heading, main .card, #connection-panel, .notebook-figure, .workspace-heading')
  let index = 0
  for (const node of targets) {
    if (seen.has(node) || node.closest('.story')) continue
    seen.add(node)
    if (!revealer || reduce.matches) continue
    node.classList.add('reveal'); node.style.setProperty('--stagger', Math.min(index++, 5)); revealer.observe(node)
  }
}

// 3. Moving between notebook pages turns the page (View Transitions where supported).
function onRoute() {
  const hash = location.hash.slice(1)
  if (story) story.hidden = !['', 'research', 'story', 'notebook'].includes(hash)
  reveal(); updateProgress()
}
document.addEventListener('click', event => {
  const link = event.target.closest('a[href^="#"]')
  if (!link || event.defaultPrevented || event.metaKey || event.ctrlKey || event.button !== 0) return
  const target = link.getAttribute('href')
  if (target === location.hash || ['#main', '#notebook', '#story'].includes(target)) return
  if (!document.startViewTransition || reduce.matches) return
  event.preventDefault()
  document.startViewTransition(() => new Promise(resolve => {
    addEventListener('hashchange', () => requestAnimationFrame(resolve), { once: true })
    location.hash = target
    setTimeout(resolve, 300) // never hold the page if the route does not change
  }))
})
addEventListener('hashchange', onRoute)

// 4. Results figure: when the shared workflow shows computed candidates, draw their curves.
// Drawn from the table's exact values (approximated for display), labelled as a drawing.
function drawCandidates() {
  const table = document.querySelector('[aria-label="Computed candidate parameters"] table')
  const host = table?.closest('.table-region')
  if (!host || host.nextElementSibling?.classList.contains('notebook-figure')) return
  const rows = [...table.tBodies[0].rows].map(row => [...row.cells].map(cell => cell.textContent.trim()))
  const candidates = rows.map(([id, A, ke, ka]) => ({ id, vector: { A: approx(A), ke: approx(ke), ka: approx(ka) } }))
    .filter(c => Object.values(c.vector).every(Number.isFinite)).slice(0, 4)
  if (!candidates.length) return
  const claim = [approx(byId('targetMin')?.value), approx(byId('targetMax')?.value)]
  const width = 760, height = 320, margin = { top: 28, right: 24, bottom: 40, left: 44 }, xMax = 9
  const level = (v, t) => Math.max(0, v.A * (Math.exp(-v.ke * t) - Math.exp(-v.ka * t)))
  const peak = Math.max(...candidates.flatMap(c => Array.from({ length: 50 }, (_, i) => level(c.vector, i * xMax / 49))))
  const yMax = Math.max(2, Math.ceil(peak * 1.15 / 2) * 2)
  const figure = document.createElement('figure'); figure.className = 'notebook-figure'
  const svg = el('svg', { viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': 'Computed candidate curves over time' }, figure)
  const { x, y } = scales({ width, height, margin, xMax, yMax })
  axes(svg, { width, height, margin, xMax, yMax, yStep: yMax > 12 ? 4 : 2, x, y, xLabel: 'elapsed time (h)', yLabel: 'concentration (mg/L)' })
  const legend = document.createElement('p'); legend.className = 'figure-legend'
  // Ink follows meaning, as in the worked example: blue inside the draft's claim, red outside it.
  // Without a readable claim the two inks only tell candidates apart. A repeated ink is dashed.
  const used = { reference: 0, outside: 0 }
  candidates.forEach((candidate, i) => {
    const inside = claim.every(Number.isFinite) ? (candidate.vector.ke >= claim[0] && candidate.vector.ke <= claim[1] ? 'inside' : 'outside') : null
    const ink = inside ? (inside === 'inside' ? 'reference' : 'outside') : (i % 2 ? 'outside' : 'reference')
    const path = el('path', { class: `fig-curve ${ink}`, d: curvePath(candidate.vector, x, y, xMax) }, svg)
    const dashed = used[ink]++ > 0
    if (dashed) path.setAttribute('stroke-dasharray', '6 5')
    const item = document.createElement('span')
    item.style.setProperty('--swatch', `var(--${ink === 'reference' ? 'accent' : 'counter'})`)
    if (dashed) item.classList.add('dashed')
    item.textContent = `${candidate.id} · ke ≈ ${candidate.vector.ke.toPrecision(3)}${inside ? ` · ${inside} your draft's claim` : ''}`
    legend.append(item)
    if (!reduce.matches && !dashed) {
      const length = Math.ceil(path.getTotalLength())
      path.animate([{ strokeDasharray: `${length} ${length}`, strokeDashoffset: length }, { strokeDasharray: `${length} ${length}`, strokeDashoffset: 0 }],
        { duration: 1400, delay: i * 250, easing: 'cubic-bezier(.2,.7,.2,1)', fill: 'backwards' })
    }
  })
  const caption = document.createElement('figcaption')
  caption.textContent = 'Drawn from the exact candidate values above, approximated for display. The table and the evidence record are authoritative; a curve is not a check.'
  figure.append(legend, caption)
  host.after(figure); reveal(figure.parentElement)
}

// The shared modules re-render panels freely; watch for new content instead of patching them.
let pending = false
new MutationObserver(() => {
  if (pending) return
  pending = true
  requestAnimationFrame(() => { pending = false; reveal(); drawCandidates() })
}).observe(byId('main') ?? document.body, { childList: true, subtree: true })

onRoute()
