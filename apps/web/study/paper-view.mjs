// Paper review uses the ordinary editable scientific inputs and action buttons.
// Only their presentation changes; there is no scientific result in this view.
import { escapeHTML } from './results.mjs'
import { paperInputsMatch } from './paper-study.mjs'

export function createPaperView(editor, sym) {
  const pane = document.createElement('div')
  pane.id = 'paper-editor'; pane.hidden = true
  pane.innerHTML = `<p class="meta paper-source"></p>
    <h1 id="paper-data-title" tabindex="-1">Check the proof’s numerical premise</h1>
    <p class="lead">The proposed proof depends on Proposition 3.1. Test whether the paper’s synthetic data allow a counterexample to that premise.</p>
    <section class="paper-premise" aria-labelledby="paper-premise-title">
      <h2 id="paper-premise-title">The claim this proof needs</h2>
      <blockquote>Every parameter triple in the admitted domain that satisfies all five hard bounds in Table 1 obeys the closed rate constraint ${sym.claim('0.10', '0.17')}.</blockquote>
      <p class="hint">Proposition 3.1, page 3. The theorem on page 4 explicitly requires this proposition.</p>
    </section>
    <div class="paper-review-brief"><section><h2>What will be checked</h2><p>Counterdex searches the paper’s stated model for a curve that fits every synthetic reading but falls outside the claimed interval.</p></section>
    <section><h2>Why it matters</h2><p>One checked counterexample would invalidate this necessary premise and break the proposed proof. The Riemann hypothesis itself is outside this check.</p></section></div>
    <p class="paper-edited notice" hidden>These inputs differ from the paper. The check will apply to your edited study; it cannot establish that the original paper’s premise is false.</p>
    <details class="paper-values"><summary>Review the source values and assumptions</summary><div class="paper-values-body"></div></details>
    <details class="paper-inputs"><summary>Edit the numerical inputs</summary><p class="hint">These are the two-rate model inputs from the paper. Changing them creates a different numerical check.</p></details>`
  editor.before(pane)
  const details = pane.querySelector('.paper-inputs'), actions = editor.querySelector('.actions')
  const heading = editor.querySelector('h1'), originalHeadingTag = heading.tagName
  let active = false
  details.addEventListener('toggle', () => { if (details.open) window.dispatchEvent(new Event('resize')) })
  const style = document.createElement('style')
  style.textContent = `
#paper-editor>h1{max-width:850px}#paper-editor>.lead{max-width:860px}
.paper-premise{margin:28px 0;padding:24px 28px;border:1px solid var(--line);border-radius:12px;background:var(--surface)}
#paper-editor h2{font-size:19px;line-height:1.4;margin:0 0 12px;font-weight:550}
.paper-premise blockquote{font-size:21px;line-height:1.65;margin:0;max-width:900px}.paper-premise blockquote .katex{white-space:nowrap}
.paper-review-brief{display:grid;grid-template-columns:1fr 1fr;gap:40px;margin:28px 0}.paper-review-brief p{color:var(--text-2);line-height:1.7;margin:0}
.paper-values,.paper-inputs{border-top:1px solid var(--line);padding:18px 0}.paper-values summary,.paper-inputs summary{font-size:16px}.paper-values-body{padding-top:18px;max-width:900px}.paper-values-body table{width:100%}.paper-values-body .equation{overflow-x:auto}
#paper-editor>.actions{position:static;margin-top:12px;box-shadow:none}#paper-editor #editor{padding:22px 0}#paper-editor #claim-title{font-size:24px}#paper-editor .paper-edited{margin:24px 0}
@media(max-width:700px){.paper-review-brief{grid-template-columns:1fr;gap:22px}.paper-premise{padding:20px}.paper-premise blockquote{font-size:18px}.paper-values-body{overflow-x:auto}}
`
  document.head.append(style)
  return {
    setActive(next) {
      if (active === next) return
      active = next; pane.hidden = !next
      if (next) {
        details.append(editor); pane.append(actions); details.open = false
        heading.setAttribute('role','heading'); heading.setAttribute('aria-level','2')
        actions.querySelector('[data-action="start-over"]').textContent = 'Back to the paper'
        actions.querySelector('#prepare').textContent = 'Review and prepare the premise check'
      } else {
        pane.before(editor); editor.append(actions)
        if (originalHeadingTag === 'H1') {heading.removeAttribute('role');heading.removeAttribute('aria-level')}
        actions.querySelector('[data-action="start-over"]').textContent = 'Use different data'
        actions.querySelector('#prepare').textContent = 'Prepare the check'
      }
    },
    render(draft, asset) {
      pane.querySelector('.paper-source').textContent = `${asset.filename} · Page 3 · Proposition 3.1`
      pane.querySelector('.paper-edited').hidden = paperInputsMatch(draft)
      const L = draft.limits
      pane.querySelector('.paper-values-body').innerHTML = `<p class="hint">Prepared transcription of Table 1. Compare these values with the uploaded PDF. The paper declares a synthetic calibration, using a two-rate concentration equation; it reports no medicine experiment.</p>
        <table class="data"><caption>Inputs for this check</caption><thead><tr><th>Included</th><th>Elapsed time (h)</th><th>Response (mg/L)</th><th>Hard allowance (± mg/L)</th></tr></thead><tbody>${draft.rows.map(r=>`<tr><td>${r.included?'Yes':'No'}</td><td>${escapeHTML(r.time)}</td><td>${escapeHTML(r.value)}</td><td>${escapeHTML(r.allowance)}</td></tr>`).join('')}</tbody></table>
        <p>Reviewed claim: ${sym.claim(draft.low,draft.high)}. Origin: ${draft.origin==='synthetic'?'synthetic':escapeHTML(draft.origin||'not specified')}.</p>
        <div class="equation">${sym.model}</div><p class="hint">${sym.A} ∈ [${escapeHTML(L.aLow)}, ${escapeHTML(L.aHigh)}] mg/L; ${sym.ke} ∈ [${escapeHTML(L.keLow)}, ${escapeHTML(L.keHigh)}] h⁻¹; ${sym.ka} ∈ [${escapeHTML(L.kaLow)}, ${escapeHTML(L.kaHigh)}] h⁻¹, with ${sym.order}.</p>
        <p class="hint">${escapeHTML(draft.timeOrigin)}. ${escapeHTML(draft.source)}</p>`
    },
    focus() { pane.querySelector('#paper-data-title').focus({preventScroll:true}) },
    revealInputs() { details.open = true },
  }
}
