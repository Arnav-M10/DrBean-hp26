// Paper (PDF) review panel. Every action is an ordinary server request; nothing here sends a
// paper to a model, accepts a value, approves a plan or starts science.
import { NOTE_KINDS, evidenceMap, missingChecklist, paperAvailable, selectionProblem, statementWarnings, validatePaperFile } from './paper.mjs'

export function setupPaperWorkflow({ context, getDraft, button, node, exactRecord, attachPaper }) {
  let papers = [], paper, page = 1, pageText, previewUrl, previewFor = '', selected = new Set(), selection
  let file, origin = '', notes = [], noteDraft = { kind: 'claim', excerpt: '' }, attachedTo = ''
  function clearPaper() {
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    paper = pageText = previewUrl = selection = undefined; previewFor = ''; page = 1; selected = new Set(); notes = []; attachedTo = ''
  }
  function reset() { clearPaper(); papers = []; file = undefined; origin = '' }

  async function open(record) {
    const { api, workspace } = context()
    if (record.workspace_id !== workspace) throw new Error('Select the paper’s workspace first.')
    if (paper?.id !== record.id) clearPaper()
    paper = record
    await showPage(page)
  }
  async function showPage(number) {
    const { api } = context()
    const count = paper.body.manifest.page_count
    if (number < 1 || number > count) throw new Error(`This paper has pages 1 to ${count}.`)
    page = number
    pageText = await api.json(`/papers/${encodeURIComponent(paper.id)}/pages/${number}/text`)
    const key = `${paper.id}:${number}`
    if (previewFor !== key) {
      const preview = await api.download(`/papers/${encodeURIComponent(paper.id)}/pages/${number}/preview`)
      if (previewUrl) URL.revokeObjectURL(previewUrl)
      previewUrl = URL.createObjectURL(new Blob([preview.bytes], { type: 'image/png' })); previewFor = key
    }
  }
  async function refreshList() {
    const { api, workspace } = context()
    papers = await api.json(`/workspaces/${encodeURIComponent(workspace)}/papers`)
  }

  function labelled(parent, text, control) {
    const label = node('label', text); label.className = 'stack'; label.append(control); parent.append(label); return control
  }
  function select(choices, value, onChange, id) {
    const control = node('select', ''); if (id) control.id = id
    for (const [v, t] of choices) { const option = node('option', t); option.value = v; control.append(option) }
    control.value = value; control.disabled = context().busy
    control.addEventListener('change', () => onChange(control.value)); return control
  }
  function list(parent, title, items, id) {
    parent.append(node('h5', title))
    const ul = node('ul', ''); if (id) ul.id = id
    for (const item of items) ul.append(node('li', item))
    parent.append(ul)
  }

  function render(parent) {
    const { api, workspace, busy, capabilities, rerender } = context()
    const section = node('section', ''); section.id = 'paper-review'; parent.append(section)
    section.append(node('h3', 'Paper (PDF) review'))
    if (!api || !workspace) { section.append(node('p', 'Connect and choose a workspace to review a paper.')); return }
    if (!paperAvailable(capabilities)) {
      section.append(node('p', 'This server does not accept papers yet (no paper_intake capability). Use a source image or enter measurements manually.'))
      return
    }
    const limits = capabilities.paper_intake
    section.append(node('p', `Upload keeps the paper on this server only. Nothing is sent to Gemini or any other model by uploading, reading pages or selecting pages. Limits: one PDF up to ${Math.floor(limits.max_bytes / 1048576)} MiB and ${limits.max_pages} pages; at most ${limits.max_pages_per_batch} pages per model batch. Document scripts, attachments and links are never run or followed.`))

    // 1. Choose or reopen a paper.
    const input = node('input', ''); input.type = 'file'; input.accept = 'application/pdf,.pdf'; input.id = 'paper-file'; input.disabled = busy
    input.addEventListener('change', () => { file = input.files[0]; rerender() })
    labelled(section, 'Public or synthetic paper (PDF)', input)
    if (file) section.append(node('p', `Chosen: ${file.name} (${file.size.toLocaleString()} bytes). Not uploaded yet.`))
    labelled(section, 'Paper origin', select([['', 'Choose origin'], ['synthetic', 'Synthetic (authored for testing)'], ['public', 'Public (you may use and share it)']], origin, value => { origin = value }, 'paper-origin'))
    button(section, 'Upload paper (stays on this server)', async () => {
      validatePaperFile(file, capabilities)
      if (!['synthetic', 'public'].includes(origin)) throw new Error('Declare whether the paper is synthetic or public.')
      const record = await api.uploadPaper(workspace, file, origin)
      file = undefined; await refreshList(); await open(record)
    }, busy)
    button(section, 'List retained papers', refreshList, busy)
    if (papers.length) {
      labelled(section, 'Reopen a retained paper', select([['', 'Choose a paper'], ...papers.map(p => [p.id, `${p.body.filename} · ${p.body.manifest.page_count} pages · ${p.body.origin}`])],
        paper?.id ?? '', value => context().perform(() => open(papers.find(p => p.id === value))), 'paper-reopen'))
    }
    if (!paper) return

    // 2. The paper and what was (and was not) read from it.
    const m = paper.body.manifest, coverage = m.coverage
    section.append(node('h4', paper.body.filename),
      node('p', `Origin: ${paper.body.origin}. ${m.page_count} physical pages. SHA-256 ${paper.body.sha256}.`),
      node('p', `Native text layer on pages: ${coverage.pages_with_text_layer.join(', ') || 'none'}. Without a text layer (for example scans): ${coverage.pages_without_text_layer.join(', ') || 'none'}. Pages processed by a model: ${coverage.model_processed_pages.join(', ') || 'none'}.`))
    if (m.document_warnings.length) section.append(node('p', `Document contents reported but never run: ${m.document_warnings.join(', ')}.`))
    section.append(exactRecord('Paper manifest (digests, page sizes, coordinate conventions)', m))

    // 3. Page navigation: rendered page beside its native text.
    const nav = node('div', ''); nav.className = 'actions'; section.append(nav)
    button(nav, 'Previous page', () => showPage(page - 1), busy || page <= 1)
    const pageSelect = select(m.pages.map(p => [String(p.physical_page), `Page ${p.physical_page}${p.printed_label !== String(p.physical_page) ? ` (printed ${p.printed_label})` : ''}`]),
      String(page), value => context().perform(() => showPage(Number(value))), 'paper-page')
    pageSelect.setAttribute('aria-label', 'Physical page'); nav.append(pageSelect)
    button(nav, 'Next page', () => showPage(page + 1), busy || page >= m.page_count)
    const pair = node('div', ''); pair.className = 'paper-page'; section.append(pair)
    if (previewUrl) { const image = node('img', ''); image.src = previewUrl; image.alt = `Rendered page ${page} of ${paper.body.filename}`; image.id = 'paper-preview'; pair.append(image) }
    const textBox = node('div', ''); pair.append(textBox)
    if (pageText) {
      textBox.append(node('p', pageText.has_text_layer ? `Native text of page ${page} (may miss tables, symbols and layout).` : `Page ${page} has no useful text layer. Read the image; nothing here was extracted.`))
      const pre = node('pre', pageText.text || '(no native text)'); pre.id = 'paper-page-text'; textBox.append(pre)
    }

    // 4. Cited statements: what the paper says, located on a page, with an honest citation check.
    section.append(node('h4', 'Cite what the paper states'),
      node('p', 'Copy a short exact quotation from the current page. The check only says whether those words occur on that page; it does not confirm your reading of them.'))
    labelled(section, 'Kind of statement', select(NOTE_KINDS, noteDraft.kind, value => { noteDraft.kind = value }, 'paper-note-kind'))
    const excerpt = node('textarea', ''); excerpt.id = 'paper-note-excerpt'; excerpt.rows = 2; excerpt.maxLength = 1000; excerpt.value = noteDraft.excerpt; excerpt.disabled = busy
    excerpt.addEventListener('input', () => { noteDraft.excerpt = excerpt.value })
    labelled(section, `Quotation from page ${page}`, excerpt)
    button(section, 'Add cited statement', async () => {
      const text = noteDraft.excerpt.trim()
      if (!text) throw new Error('Enter the quotation first.')
      const check = await api.json(`/papers/${encodeURIComponent(paper.id)}/citation-checks`, { page, excerpt: text })
      const info = m.pages[page - 1]
      notes.push({ kind: noteDraft.kind, page, printedLabel: info.printed_label, excerpt: text, check: check.quotation })
      noteDraft.excerpt = ''
    }, busy)
    if (notes.length) {
      const ul = node('ul', ''); ul.id = 'paper-notes'; section.append(ul)
      notes.forEach((note, index) => {
        const li = node('li', `p.${note.page} · ${note.kind}: “${note.excerpt}” · ${note.check.status.replaceAll('_', ' ')}`)
        for (const warning of statementWarnings(note)) li.append(node('p', `Caution: ${warning}`))
        const remove = node('button', 'Remove'); remove.type = 'button'; remove.className = 'secondary'
        remove.addEventListener('click', () => { notes.splice(index, 1); rerender() }); li.append(remove); ul.append(li)
      })
      section.append(node('p', 'Cited statements stay in this tab (they are in Download draft). They are your reading of the paper, not extracted or verified values.'))
    }

    // 5. The three things that must stay apart, and what is still missing.
    const draft = getDraft(), map = evidenceMap(draft, notes, capabilities)
    const columns = node('div', ''); columns.className = 'paper-columns'; columns.id = 'paper-evidence-map'; section.append(node('h4', 'Evidence map'), columns)
    const column = () => { const c = node('div', ''); columns.append(c); return c }
    list(column(), 'What the paper states (your cited quotations)', map.paperStates.length ? map.paperStates : ['Nothing cited yet.'])
    list(column(), 'What you are asking to test', map.youAsk)
    list(column(), 'What the engine can check', map.engineChecks)
    const missing = missingChecklist(draft, notes, capabilities)
    list(section, missing.length ? 'Still missing before an investigation can be planned' : 'Nothing listed is missing. Review the plan before approving it.', missing, 'paper-missing')
    section.append(node('p', 'A paper’s confidence interval is not a universal parameter bound, and SD, SEM or error bars are not hard measurement allowances. A checked counterexample would challenge only your reviewed claim under your stated assumptions; it would not disprove the paper.'))

    // 6. Use this paper as the cited source of the manual measurement draft.
    button(section, 'Record this paper as the source of my measurement draft', async () => {
      const pages = [...new Set(notes.filter(n => ['measurement', 'allowance'].includes(n.kind)).map(n => n.page))]
      if (!pages.length) throw new Error('Cite the page(s) with the measurements first, so the draft records where its values came from.')
      attachPaper(paper, pages); attachedTo = paper.id
    }, busy)
    if (attachedTo === paper.id) section.append(node('p', 'The measurement draft now names this paper, its digest and the cited pages as the source of its rows. You still type and review every value; the server stores them as an ordinary reviewed dataset.'))

    // 7. A bounded page selection for a later model batch, and the honest state of model processing.
    section.append(node('h4', 'Pages for model-assisted extraction'))
    const boxes = node('div', ''); boxes.className = 'actions'; section.append(boxes)
    for (const info of m.pages) {
      const label = node('label', ` ${info.physical_page}`)
      const check = node('input', ''); check.type = 'checkbox'; check.checked = selected.has(info.physical_page); check.disabled = busy
      check.setAttribute('aria-label', `Select page ${info.physical_page} for extraction`)
      check.addEventListener('change', () => { if (check.checked) selected.add(info.physical_page); else selected.delete(info.physical_page); selection = undefined; rerender() })
      label.prepend(check); boxes.append(label)
    }
    button(section, 'Prepare page selection', async () => {
      const pages = [...selected].sort((a, b) => a - b), problem = selectionProblem(pages, m.page_count, limits.max_pages_per_batch)
      if (problem) throw new Error(problem)
      selection = await api.json(`/papers/${encodeURIComponent(paper.id)}/page-selections`, { pages })
    }, busy)
    if (selection) {
      const s = selection.body
      section.append(node('p', `Selection ${selection.id}: physical pages ${s.mapping.map(x => x.physical_page).join(', ')} as a derived ${s.subset_byte_size.toLocaleString()}-byte PDF (SHA-256 ${s.subset_sha256}). ${s.coverage_note}`), exactRecord('Selected-page manifest and mapping', s))
    }
    section.append(node('p', `Model extraction on this server: ${limits.model_extraction}. Before any page is sent to a model you will see the pages, purpose, provider, model and request budget, and must consent explicitly. Until then, review the pages yourself and enter values manually.`))
  }
  return { render, reset, notes: () => notes }
}
