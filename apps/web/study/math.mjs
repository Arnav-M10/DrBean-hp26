// Mathematical notation, typeset with KaTeX (vendor/katex, MIT, loaded by the page).
// In the page the output is KaTeX HTML with hidden MathML for screen readers; in the
// downloadable report it is MathML only, so the report needs no stylesheet or fonts.
const escape = text => String(text).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c])

export function tex(source, { display = false, output = 'htmlAndMathml' } = {}) {
  const katex = globalThis.katex
  if (!katex) return `<code class="tex-source">${escape(source)}</code>`
  return katex.renderToString(source, { displayMode: display, output, throwOnError: false, strict: 'ignore', trust: false })
}

// The symbols every screen uses, for one output mode.
export function symbols(output = 'htmlAndMathml') {
  const t = (source, display = false) => tex(source, { display, output })
  return {
    ke: t('k_e'), ka: t('k_a'), A: t('A'), C: t('C(t)'),
    perHour: t('\\mathrm{h}^{-1}'), mgL: t('\\mathrm{mg/L}'), pm: t('\\pm'),
    model: t('C(t) = A\\left(e^{-k_e t} - e^{-k_a t}\\right)', true),
    modelInline: t('C(t) = A\\left(e^{-k_e t} - e^{-k_a t}\\right)'),
    order: t('k_e < k_a'),
    exact(text) {
      const [n, d] = String(text).split('/')
      if (!/^-?\d+$/.test(n) || (d !== undefined && !/^\d+$/.test(d))) return escape(text)
      return d === undefined || d === '1' ? t(n) : t(`\\tfrac{${n}}{${d}}`)
    },
    claim(low, high) {
      if (![low, high].every(v => /^\d+(?:\.\d+)?$/.test(String(v)))) return `k<sub>e</sub> from ${escape(low)} to ${escape(high)} per hour`
      return t(`k_e \\in [\\,${low},\\ ${high}\\,]\\ \\mathrm{h}^{-1}`)
    },
  }
}

export const page = symbols()
