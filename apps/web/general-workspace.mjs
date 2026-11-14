// General research is interpretation of retained sources, never checker authority.
// This controller has no provider transport or production fallback answers.
export const GENERAL_LIMITS = Object.freeze({ files: 5, fileBytes: 5 * 1024 * 1024, totalBytes: 10 * 1024 * 1024, pdfPages: 10 })
const TYPES = Object.freeze({ csv: 'text/csv', tsv: 'text/tab-separated-values', json: 'application/json', txt: 'text/plain', md: 'text/markdown', markdown: 'text/markdown', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', pdf: 'application/pdf' })
const ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/
const SHA = /^[a-f0-9]{64}$/
const freeze = value => { if (value && typeof value === 'object') { Object.freeze(value); Object.values(value).forEach(freeze) }; return value }
const clone = value => JSON.parse(JSON.stringify(value))
const bounded = (value, max, label) => { if (typeof value !== 'string' || value.length > max) throw new Error(`The server returned an invalid ${label}.`); return value }
const list = (value, max, label) => { if (!Array.isArray(value) || value.length > max) throw new Error(`The server returned an invalid ${label}.`); return value }

export function generalCapabilities(capabilities) {
  const general = capabilities?.general_research
  const lower = (value, ceiling) => Number.isInteger(value) && value > 0 ? Math.min(value, ceiling) : ceiling
  return {
    available: general?.available === true,
    mediaTypes: Array.isArray(general?.media_types) ? general.media_types.filter(type => Object.values(TYPES).includes(type)) : [],
    maxFiles: lower(general?.max_assets, GENERAL_LIMITS.files),
    maxFileBytes: lower(general?.max_file_bytes, GENERAL_LIMITS.fileBytes),
    maxTotalBytes: lower(general?.max_total_bytes, GENERAL_LIMITS.totalBytes),
    maxPdfPages: lower(general?.max_pdf_pages, GENERAL_LIMITS.pdfPages),
    analysisAvailable: general?.analysis?.available === true,
    model: typeof general?.analysis?.model === 'string' ? general.analysis.model : '',
    reason: typeof general?.analysis?.reason === 'string' ? general.analysis.reason : '',
    remaining: general?.budget?.remaining ?? null,
  }
}

export function fileMediaHint(file) {
  const extension = file.name?.split('.').at(-1)?.toLowerCase()
  // A hint selects a request media type; admission is decided by the server's parser.
  if (['', 'application/octet-stream', 'text/plain'].includes(file.type ?? '') && TYPES[extension]) return TYPES[extension]
  return file.type
}

export function validateFileSelection(existing, files, limits) {
  if (!limits.available) throw new Error('General file admission is unavailable on this server. Existing evidence is unchanged.')
  if (!files.length || existing.length + files.length > limits.maxFiles) throw new Error(`Choose between 1 and ${limits.maxFiles} files in total.`)
  for (const file of files) {
    if (typeof file.name !== 'string' || !file.name || file.name.length > 240) throw new Error('Choose a file with a name of 240 characters or fewer.')
    if (!Number.isSafeInteger(file.size) || file.size < 1 || file.size > limits.maxFileBytes) throw new Error(`${file.name}: files must be nonempty and at most ${Math.floor(limits.maxFileBytes / 1024 / 1024)} MiB.`)
    if (!limits.mediaTypes.includes(fileMediaHint(file))) throw new Error(`${file.name}: this format is not supported by the server. Choose an advertised CSV, TSV, JSON, text, image or PDF format.`)
  }
  if (existing.reduce((n, file) => n + file.byte_size, 0) + files.reduce((n, file) => n + file.size, 0) > limits.maxTotalBytes) throw new Error('Selected files exceed the 10 MiB combined limit. Remove a file or choose a smaller scope.')
}

export function validateResearchAsset(asset, expected = {}) {
  if (!asset || !ID.test(asset.id) || !SHA.test(asset.sha256) || !Object.values(TYPES).includes(asset.media_type)
      || !Number.isSafeInteger(asset.byte_size) || asset.byte_size < 1 || asset.byte_size > GENERAL_LIMITS.fileBytes) throw new Error('The server did not return a valid retained file identity.')
  bounded(asset.filename, 240, 'filename')
  if (expected.sha256 && asset.sha256 !== expected.sha256 || expected.byte_size !== undefined && asset.byte_size !== expected.byte_size
      || expected.workspaceId && asset.workspace_id && asset.workspace_id !== expected.workspaceId) throw new Error('The retained file does not match the selected bytes or workspace.')
  const pages = list(asset.pages, GENERAL_LIMITS.pdfPages, 'page list')
  if (!pages.length) throw new Error('The server admitted no inspectable pages. Use a supported file or a smaller excerpt.')
  pages.forEach((page, index) => {
    if (page.page_index !== index || page.page_number !== index + 1) throw new Error('The server returned inconsistent source page identities.')
    for (const key of ['image_sha256', 'text_sha256']) if (page[key] !== null && !SHA.test(page[key])) throw new Error('The source page digest is invalid.')
  })
  return clone(asset)
}

export function validateResearchAnalysis(record, assets, workspaceId) {
  if (JSON.stringify(record).length > 4 * 1024 * 1024) throw new Error('The analysis exceeds the bounded browser preview. Request a smaller scope.')
  if (!record || !ID.test(record.id) || record.workspace_id && record.workspace_id !== workspaceId) throw new Error('The saved analysis belongs to another workspace or has an invalid identity.')
  const body = record.body
  if (!body || body.verification?.status !== 'not_mathematically_verified') throw new Error('General AI analysis cannot be presented as a mathematically verified result.')
  bounded(body.summary, 16000, 'summary')
  const byAsset = new Map(assets.map(asset => [asset.id, asset]))
  const citations = list(body.citations, 100, 'citations')
  const citationIds = new Set()
  citations.forEach(citation => {
    if (!ID.test(citation.id) || citationIds.has(citation.id)) throw new Error('The analysis contains duplicate or invalid citation identities.')
    citationIds.add(citation.id)
    const source = byAsset.get(citation.asset_id)
    if (!source || citation.source_sha256 !== source.sha256 || !Number.isInteger(citation.page_index)
        || !source.pages[citation.page_index]) throw new Error('A citation does not match the selected retained source and page.')
    if (!bounded(citation.quote, 8000, 'source quote').trim()) throw new Error('A citation has no source quote.')
    if (citation.bbox != null) {
      const b = citation.bbox
      if (citation.bbox_space !== 'normalized_top_left' || !Array.isArray(b) || b.length !== 4
          || !b.every(n => typeof n === 'number' && Number.isFinite(n) && n >= 0 && n <= 1)
          || b[0] >= b[2] || b[1] >= b[3]) throw new Error('Citation coordinates are not in the declared normalized page space.')
    }
  })
  const refs = item => list(item.citation_ids, 100, 'citation references').forEach(id => { if (!citationIds.has(id)) throw new Error('A statement refers to a missing source citation.') })
  for (const item of list(body.claims, 100, 'claims')) { bounded(item.text, 8000, 'claim'); refs(item) }
  for (const item of list(body.suggested_next_steps, 50, 'next steps')) { bounded(item.text, 4000, 'next step'); refs(item) }
  for (const item of list(body.clarifications, 50, 'clarifications')) { bounded(item.question, 4000, 'clarification'); refs(item) }
  list(body.limitations, 50, 'limitations').forEach(item => bounded(item, 4000, 'limitation'))
  for (const table of list(body.extracted_tables, 20, 'tables')) {
    if (!ID.test(table.id)) throw new Error('An extracted table has an invalid identity.')
    bounded(table.title, 500, 'table title'); refs(table)
    const columns = list(table.columns, 50, 'columns')
    columns.forEach(column => bounded(column, 300, 'column name'))
    for (const row of list(table.rows, 500, 'table rows')) {
      if (!Array.isArray(row) || row.length !== columns.length) throw new Error('An extracted table has inconsistent columns.')
      row.forEach(cell => { if (cell !== null) bounded(cell, 4000, 'table cell') })
    }
  }
  return clone(record)
}

// The small interface keeps session and HTTP ownership in GPT1's transport.
export function generalService(api, workspaceId) {
  return {
    upload: (file, operationId) => api.uploadResearchAsset(workspaceId, file, operationId),
    analyze: body => api.researchAnalysis(workspaceId, body),
    asset: id => api.json(`/research-assets/${encodeURIComponent(id)}`),
    analysis: id => api.json(`/research-analyses/${encodeURIComponent(id)}`),
  }
}

export class GeneralResearchWorkspace {
  constructor({ serviceFactory = generalService, changed = () => {}, storage = globalThis.sessionStorage, randomId = () => crypto.randomUUID() } = {}) {
    this.serviceFactory = serviceFactory; this.changed = changed; this.storage = storage; this.randomId = randomId
    this.generation = 0; this.connection = {}; this.state = this.empty()
  }
  empty() { return { assets: [], question: '', review: null, accepted: false, busy: false, error: '', notice: '', pending: [], history: [], result: null, resultQuestion: '', citation: null } }
  emit() { this.changed(this.state) }
  key() { return `drbean-general-v1:${this.connection.workspaceId}` }
  persist() {
    if (!this.connection.workspaceId) return
    try { this.storage?.setItem(this.key(), JSON.stringify({ version: 1, assets: this.state.assets.map(({ id, sha256 }) => ({ id, sha256 })), question: this.state.question, pending: this.state.pending, history: this.state.history })) } catch { this.state.notice = 'Browser storage is unavailable. Keep this tab open to retain pending request identities.' }
  }
  async connect(connection) {
    const same = connection.api === this.connection.api && connection.workspaceId === this.connection.workspaceId && connection.mode === this.connection.mode
    const previousModel = this.limits?.model
    this.connection = connection; this.limits = generalCapabilities(connection.capabilities)
    if (same && previousModel !== this.limits.model) { this.state.review = null; this.state.accepted = false }
    if (same) { this.emit(); return }
    this.generation++; this.state = this.empty()
    this.service = null
    if (!connection.api || !connection.workspaceId || !['browser_session', 'local_owner'].includes(connection.mode)) { this.emit(); return }
    this.service = this.serviceFactory(connection.api, connection.workspaceId)
    let saved
    try {
      for (let index = this.storage?.length - 1; index >= 0; index--) { const key = this.storage.key(index); if (key?.startsWith('drbean-general-v1:') && key !== this.key()) this.storage.removeItem(key) }
      saved = JSON.parse(this.storage?.getItem(this.key()) ?? 'null')
    } catch { /* No guessed server lookups or analysis on storage failure. */ }
    const generation = this.generation
    if (saved?.version === 1) {
      try {
        const references = list(saved.assets, this.limits.maxFiles, 'saved source references')
        const assets = await Promise.all(references.map(async ref => {
          if (!ID.test(ref.id) || !SHA.test(ref.sha256)) throw new Error('Invalid saved source reference.')
          return validateResearchAsset(await this.service.asset(ref.id), { sha256: ref.sha256, workspaceId: connection.workspaceId })
        }))
        if (generation !== this.generation) return
        this.state.assets = assets; this.state.question = bounded(saved.question, 8000, 'saved question')
        this.state.pending = list(saved.pending, 10, 'pending operations').map(operation => this.restoreOperation(operation))
        this.state.history = list(saved.history, 20, 'saved analyses').filter(item => ID.test(item.id))
        this.state.notice = this.state.pending.length ? 'A request may have completed before this page closed. Inspect its frozen disclosure and deliberately retry the same request; no analysis runs automatically.' : 'Retained sources restored. Reopen a saved analysis without another model call.'
      } catch (error) { if (generation === this.generation) this.state.error = `Saved workspace could not be reopened: ${error.message}` }
    }
    if (generation === this.generation) this.emit()
  }
  restoreOperation(operation) {
    const body = operation?.body
    if (!body || !ID.test(body.client_operation_id) || !body.consent?.accepted || body.consent.provider !== 'gemini' || body.consent.include_question !== true) throw new Error('A saved request has no valid consent identity.')
    bounded(body.question, 8000, 'saved request question'); bounded(body.consent.model, 128, 'saved model')
    const assets = list(body.assets, 5, 'saved request files')
    if (!assets.length || assets.some(asset => !ID.test(asset.id) || !SHA.test(asset.sha256))
        || JSON.stringify(body.consent.asset_ids) !== JSON.stringify(assets.map(asset => asset.id))) throw new Error('A saved request has inconsistent source disclosure.')
    return { body: freeze(clone(body)), status: 'uncertain' }
  }
  editQuestion(question) {
    if (this.state.busy) return
    this.state.question = question; this.state.review = null; this.state.accepted = false; this.persist()
    // Input handlers update only consent/review state, not the input DOM itself.
  }
  removeAsset(id) {
    if (this.state.busy) return
    this.state.assets = this.state.assets.filter(asset => asset.id !== id)
    this.state.review = null; this.state.accepted = false; this.persist(); this.emit()
  }
  dismissRefused(operationId) {
    const operation = this.state.pending.find(item => item.body.client_operation_id === operationId)
    if (operation?.status !== 'refused') throw new Error('An uncertain request must retain its original operation identity.')
    this.state.pending = this.state.pending.filter(item => item !== operation); this.persist(); this.emit()
  }
  async upload(files) {
    if (this.state.busy) return
    try { validateFileSelection(this.state.assets, files, this.limits); if (!this.service) throw new Error('Connect to a private workspace first.') } catch (error) { this.state.error = error.message; this.emit(); return }
    this.state.busy = true; this.state.error = ''; this.state.review = null; this.state.accepted = false; this.emit()
    const generation = this.generation
    const service = this.service, workspaceId = this.connection.workspaceId
    try {
      for (const file of files) {
        const raw = await file.arrayBuffer()
        const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', raw)), n => n.toString(16).padStart(2, '0')).join('')
        if (generation !== this.generation) return
        const retained = validateResearchAsset(await service.upload(file, this.randomId()), { sha256: digest, byte_size: file.size, workspaceId })
        if (generation !== this.generation) return
        if (!this.state.assets.some(asset => asset.id === retained.id)) this.state.assets.push(retained)
        this.persist()
      }
      this.state.notice = 'Files retained for your inspection. Nothing has been sent to Gemini.'
    } catch (error) { if (generation === this.generation) this.state.error = `${error.message} Previously admitted files and evidence are preserved.` }
    finally { if (generation === this.generation) { this.state.busy = false; this.emit() } }
  }
  prepareReview() {
    try {
      if (!this.service || !this.state.assets.length) throw new Error('Add at least one admitted file to a private workspace first.')
      const question = this.state.question.trim()
      if (!question || question.length > 8000) throw new Error('Enter a question of 1–8,000 characters about your files.')
      if (!this.limits.analysisAvailable || !this.limits.model) throw new Error(this.limits.reason || 'Gemini analysis is unavailable. Your files and question remain available for manual review.')
      if (this.limits.remaining?.requests === 0 || this.limits.remaining?.input_tokens === 0 || this.limits.remaining?.output_tokens === 0) throw new Error('The shared application budget is exhausted. No provider request was made.')
      if (this.state.pending.length >= 10) throw new Error('Resolve a pending request before preparing another analysis.')
      const assets = this.state.assets.map(({ id, sha256 }) => ({ id, sha256 }))
      this.state.review = freeze({ client_operation_id: this.randomId(), question, assets,
        consent: { accepted: true, provider: 'gemini', model: this.limits.model, asset_ids: assets.map(asset => asset.id), include_question: true } })
      this.state.accepted = false; this.state.error = ''
    } catch (error) { this.state.error = error.message }
    this.emit()
  }
  accept(value) { this.state.accepted = value === true }
  async analyze(pendingBody = null) {
    if (this.state.busy) return
    const body = pendingBody ?? this.state.review
    if (!body || !pendingBody && !this.state.accepted) { this.state.error = 'Review the exact files, question and model, then explicitly accept their disclosure.'; this.emit(); return }
    if (pendingBody && !this.state.pending.some(operation => JSON.stringify(operation.body) === JSON.stringify(pendingBody))) throw new Error('Only an original frozen pending request can be retried.')
    const generation = this.generation
    const service = this.service, workspaceId = this.connection.workspaceId
    this.state.busy = true; this.state.error = ''; this.emit()
    let pending = this.state.pending.find(item => item.body.client_operation_id === body.client_operation_id)
    if (!pending) { pending = { body, status: 'sent' }; this.state.pending.push(pending) }
    this.persist() // Reserve the exact body/key locally before the mutation is sent.
    try {
      const result = await service.analyze(body)
      if (generation !== this.generation) return
      const sources = await Promise.all(body.assets.map(async ref => validateResearchAsset(await service.asset(ref.id), { sha256: ref.sha256, workspaceId })))
      if (generation !== this.generation) return
      this.state.result = validateResearchAnalysis(result, sources, workspaceId)
      this.state.resultQuestion = body.question; this.state.resultAssets = sources
      this.state.pending = this.state.pending.filter(item => item !== pending)
      this.state.history = [{ id: result.id, question: body.question, assets: body.assets }, ...this.state.history.filter(item => item.id !== result.id)].slice(0, 20)
      this.state.review = null; this.state.accepted = false
      this.state.notice = 'Analysis saved. It is AI interpretation, not mathematical verification.'; this.persist()
    } catch (error) {
      if (generation === this.generation) {
        pending.status = error.kind === 'rejected' && ![408, 409, 429, 500, 502, 503, 504].includes(error.status) ? 'refused' : 'uncertain'
        this.state.error = error.message; this.persist()
      }
    } finally { if (generation === this.generation) { this.state.busy = false; this.emit() } }
  }
  async reopen(item) {
    if (this.state.busy || !ID.test(item.id)) return
    const generation = this.generation
    const service = this.service, workspaceId = this.connection.workspaceId
    this.state.busy = true; this.state.error = ''; this.emit()
    try {
      const assets = await Promise.all(item.assets.map(async ref => validateResearchAsset(await service.asset(ref.id), { sha256: ref.sha256, workspaceId })))
      const result = validateResearchAnalysis(await service.analysis(item.id), assets, workspaceId)
      if (generation !== this.generation) return
      this.state.result = result; this.state.resultQuestion = item.question; this.state.resultAssets = assets; this.state.notice = 'Saved analysis retrieved. No new model call was made.'
    } catch (error) { if (generation === this.generation) this.state.error = error.message }
    finally { if (generation === this.generation) { this.state.busy = false; this.emit() } }
  }
}

export function setupGeneralWorkspace({ root, serviceFactory = generalService, storage } = {}) {
  const document = root.ownerDocument
  const element = (tag, text = '', attrs = {}) => {
    const value = document.createElement(tag); value.textContent = text
    for (const [name, setting] of Object.entries(attrs)) value.setAttribute(name, setting)
    return value
  }
  const controller = new GeneralResearchWorkspace({ serviceFactory, storage, changed: render })
  const click = (parent, text, action, disabled = false, id) => {
    const button = element('button', text, { type: 'button', ...(id ? { id } : {}) }); button.disabled = disabled
    button.addEventListener('click', () => { Promise.resolve().then(action).catch(error => { controller.state.error = error.message; render() }) })
    parent.append(button); return button
  }
  const details = (parent, title, data) => {
    const box = element('details'); box.append(element('summary', title), element('pre', JSON.stringify(data, null, 2))); parent.append(box)
  }
  const textList = (parent, title, items) => {
    parent.append(element('h4', title))
    if (!items.length) { parent.append(element('p', 'None supplied. This information remains unresolved.')); return }
    const list = element('ul')
    for (const item of items) list.append(element('li', item))
    parent.append(list)
  }
  function citationButtons(parent, ids) {
    for (const id of ids) click(parent, `Source ${id}`, () => {
      controller.state.citation = id; render()
      document.getElementById('general-citation-panel')?.focus()
    }, false).className = 'secondary citation-link'
  }
  function render() {
    const state = controller.state, limits = controller.limits ?? generalCapabilities(null)
    const connected = Boolean(controller.service), disabled = state.busy || !connected
    root.replaceChildren()
    const status = element('p', state.busy ? 'Working with your selected files…' : state.notice, { id: 'general-status', role: 'status', 'aria-live': 'polite' })
    root.append(status)
    if (state.error) root.append(element('p', state.error, { id: 'general-error', role: 'alert', class: 'errors' }))
    if (!connected) {
      root.append(element('p', 'Connecting to your private workspace. If this is a local owner instance, use Advanced server connection below. A shared demo identity cannot receive private research files.'))
    }
    const upload = element('div', '', { class: 'card' })
    upload.append(element('h3', '1. Add your data or paper'), element('p', 'Choose your own CSV, TSV, JSON, text, Markdown, PNG, JPEG or PDF files when this server supports them. Uploading stores the files for your review; it does not send them to Gemini.'))
    upload.append(element('p', `Up to ${limits.maxFiles} files · ${Math.floor(limits.maxFileBytes / 1024 / 1024)} MiB each · ${Math.floor(limits.maxTotalBytes / 1024 / 1024)} MiB combined · PDFs up to ${limits.maxPdfPages} pages. A filename is not proof that the server can parse its contents.`, { class: 'hint' }))
    const label = element('label', 'Choose files', { class: 'stack' })
    const files = element('input', '', { id: 'research-files', type: 'file', multiple: '', accept: limits.mediaTypes.join(',') })
    files.disabled = disabled || !limits.available
    files.addEventListener('change', () => controller.upload(Array.from(files.files)))
    label.append(files); upload.append(label)
    if (!limits.available) upload.append(element('p', 'General file admission is unavailable on this server. Your existing scientific workspace is still available below.'))
    const assets = element('div', '', { id: 'general-assets' })
    for (const asset of state.assets) {
      const card = element('article', '', { class: 'retained-file' })
      card.append(element('h4', asset.filename), element('p', `${asset.media_type} · ${asset.byte_size.toLocaleString()} bytes · ${asset.pages.length} page${asset.pages.length === 1 ? '' : 's'}`))
      click(card, `Remove ${asset.filename} from selection`, () => controller.removeAsset(asset.id), state.busy).className = 'secondary'
      for (const page of asset.pages) {
        const section = element('details'); section.append(element('summary', `Page ${page.page_number}`))
        if (page.width != null && page.height != null) section.append(element('p', `${page.width} × ${page.height} pixels`))
        const text = page.text_preview ?? page.text ?? ''
        if (typeof text === 'string' && text) section.append(element('pre', text.slice(0, 12000)), element('p', 'Bounded source preview; the server must account for full selected-file coverage separately.', { class: 'hint' }))
        else section.append(element('p', 'No text preview is available for this page. Inspect its citation quotes and original file.'))
        card.append(section)
      }
      const previewTables = asset.preview?.tables ?? asset.tables
      if (Array.isArray(previewTables)) details(card, 'Parsed table preview', previewTables.slice(0, 5))
      details(card, 'Retained source identity and provenance', { id: asset.id, sha256: asset.sha256, provenance: asset.provenance, pages: asset.pages.map(({ page_index, page_number, image_sha256, text_sha256 }) => ({ page_index, page_number, image_sha256, text_sha256 })) })
      assets.append(card)
    }
    upload.append(assets); root.append(upload)

    const question = element('div', '', { class: 'card' })
    question.append(element('h3', '2. Ask about these files'))
    const questionLabel = element('label', 'Your research question', { class: 'stack' })
    const input = element('textarea', '', { id: 'research-question', rows: '4', maxlength: '8000', placeholder: 'What does this evidence suggest, and what information is still missing?' })
    input.value = state.question; input.disabled = disabled
    input.addEventListener('input', () => {
      controller.editQuestion(input.value)
      root.querySelector('[data-general-review]')?.remove()
      status.textContent = 'Question changed. Review the new disclosure before requesting analysis.'
    })
    questionLabel.append(input); question.append(questionLabel)
    const model = limits.model || 'not configured'
    question.append(element('p', `Configured server model: ${model}. ${limits.analysisAvailable ? 'Available for explicitly approved analysis.' : limits.reason || 'Analysis is currently unavailable.'}`))
    if (limits.remaining) question.append(element('p', `Shared application allowance remaining: ${limits.remaining.requests ?? 'unknown'} requests; ${limits.remaining.input_tokens ?? 'unknown'} input tokens; ${limits.remaining.output_tokens ?? 'unknown'} output tokens. Server preflight determines whether the complete selected scope fits.`))
    question.append(element('p', 'The server owner’s free-tier configuration and shared limits apply. There is no paid fallback or separate allowance per workspace.', { class: 'hint' }))
    click(question, 'Review files and question to send', () => controller.prepareReview(), disabled || !state.assets.length, 'general-review-button')
    if (state.review) {
      const review = element('section', '', { class: 'general-disclosure', 'data-general-review': '' })
      review.append(element('h3', '3. Review this exact disclosure'), element('p', state.review.question), element('p', `Provider: Gemini · model: ${state.review.consent.model}`))
      textList(review, 'Selected files', state.review.assets.map(ref => state.assets.find(asset => asset.id === ref.id)?.filename ?? ref.id))
      review.append(element('p', 'The selected files and this question will be sent to the configured Gemini service. Uploading and analysis do not approve or run a mathematical investigation.'))
      const consentLabel = element('label', ' I accept disclosure of these selected files and this exact question to the named Gemini model.', { class: 'stack' })
      const consent = element('input', '', { type: 'checkbox', id: 'general-consent' }); consent.checked = state.accepted; consent.disabled = state.busy
      const analyze = click(review, 'Analyze reviewed files', () => controller.analyze(), state.busy || !state.accepted, 'general-analyze')
      consent.addEventListener('change', () => { controller.accept(consent.checked); analyze.disabled = !consent.checked || state.busy })
      consentLabel.prepend(consent); review.insertBefore(consentLabel, analyze)
      details(review, 'Exact disclosure and operation reference', state.review); question.append(review)
    }
    root.append(question)

    if (state.pending.length) {
      const pending = element('section', '', { class: 'card', id: 'general-pending' }); pending.append(element('h3', 'Requests awaiting a confirmed result'))
      pending.append(element('p', 'No request is retried automatically. Retrying uses its original files, question, model and operation identity, even if the current draft has changed.'))
      for (const operation of state.pending) {
        const box = element('details'); box.append(element('summary', `${operation.status === 'refused' ? 'Refused' : 'Uncertain'}: ${operation.body.question.slice(0, 120)}`))
        details(box, 'Frozen request to inspect before retry', operation.body)
        click(box, 'Retry this same reviewed request', () => controller.analyze(operation.body), state.busy)
        if (operation.status === 'refused') click(box, 'Dismiss refused request', () => controller.dismissRefused(operation.body.client_operation_id), state.busy).className = 'secondary'
        pending.append(box)
      }
      root.append(pending)
    }
    if (state.history.length) {
      const history = element('section', '', { class: 'card', id: 'general-history' }); history.append(element('h3', 'Saved analyses'), element('p', 'Reopening only retrieves a saved result; it does not call Gemini.'))
      for (const item of state.history) click(history, `Reopen: ${item.question.slice(0, 120)}`, () => controller.reopen(item), state.busy).className = 'secondary'
      root.append(history)
    }
    if (state.result) renderResult(state)
  }
  function renderResult(state) {
    const record = state.result, body = record.body
    const result = element('article', '', { class: 'card', id: 'general-result', 'aria-labelledby': 'general-result-title' })
    result.append(element('h3', 'AI analysis — not mathematically verified', { id: 'general-result-title' }), element('p', `Question: ${state.resultQuestion}`), element('p', body.summary))
    if (body.execution_mode === 'controlled' || body.provenance?.execution_mode === 'controlled') result.append(element('p', 'Controlled test response — this is not a live Gemini result.', { class: 'general-control-label' }))
    result.append(element('h4', 'Extracted tables'))
    if (!body.extracted_tables.length) result.append(element('p', 'No table was extracted.'))
    for (const table of body.extracted_tables) {
      const region = element('div', '', { class: 'table-region', role: 'region', 'aria-label': table.title || 'Extracted table', tabindex: '0' })
      const output = element('table'), header = element('thead'), row = element('tr')
      table.columns.slice(0, 12).forEach(column => row.append(element('th', column, { scope: 'col' }))); header.append(row); output.append(header)
      const content = element('tbody')
      for (const values of table.rows.slice(0, 30)) { const row = element('tr'); values.slice(0, 12).forEach(value => row.append(element('td', value === null ? 'Not supplied' : value))); content.append(row) }
      output.append(content); region.append(output); result.append(element('h5', table.title), region)
      result.append(element('p', `Preview: ${Math.min(30, table.rows.length)} of ${table.rows.length} rows; ${Math.min(12, table.columns.length)} of ${table.columns.length} columns. Missing values remain unresolved.`))
      citationButtons(result, table.citation_ids)
    }
    result.append(element('h4', 'Claims and source support'))
    if (!body.claims.length) result.append(element('p', 'No claim was supplied.'))
    for (const claim of body.claims) { const statement = element('div', '', { class: 'general-statement' }); statement.append(element('p', claim.text)); citationButtons(statement, claim.citation_ids); result.append(statement) }
    textList(result, 'Limitations', body.limitations)
    result.append(element('h4', 'Clarifications needed'))
    if (!body.clarifications.length) result.append(element('p', 'No clarification question was supplied. This does not establish completeness.'))
    for (const clarification of body.clarifications) { result.append(element('p', clarification.question)); citationButtons(result, clarification.citation_ids) }
    result.append(element('h4', 'Suggested next steps'))
    for (const next of body.suggested_next_steps) { result.append(element('p', next.text)); citationButtons(result, next.citation_ids) }
    if (state.citation) {
      const citation = body.citations.find(item => item.id === state.citation)
      if (citation) {
        const asset = state.resultAssets.find(item => item.id === citation.asset_id)
        const panel = element('section', '', { id: 'general-citation-panel', tabindex: '-1', class: 'general-citation-panel' })
        panel.append(element('h4', `${asset.filename} · Page ${citation.page_index + 1}`), element('blockquote', citation.quote), element('p', 'This citation identifies source text; it does not certify the claim.'))
        if (citation.bbox) panel.append(element('p', 'Location: normalized coordinates from the top-left corner of this page.'))
        details(panel, 'Exact source/page binding', citation); result.append(panel)
      }
    }
    const supported = body.verification.supported_adapter
    const templates = controller.connection.capabilities?.model_templates ?? []
    if (supported && (supported === 'counterdex.v1' || templates.some(template => template.id === supported))) {
      const mapping = element('section', '', { class: 'general-mapping-review' })
      mapping.append(element('h4', 'Review a supported scientific question'), element('p', 'The engine supports the two-rate concentration model. Review column meanings, units, deterministic hard allowances and model assumptions in the scientific workspace. General AI output has not accepted these inputs or approved computation.'))
      const link = element('a', 'Open the measurement and model review', { href: '#inputs' }); mapping.append(link); result.append(mapping)
    } else result.append(element('p', 'Mathematical verification is unavailable for this general question. The analysis and its source evidence remain useful for review.'))
    click(result, 'Download saved analysis JSON', () => {
      const url = URL.createObjectURL(new Blob([JSON.stringify(record, null, 2)], { type: 'application/json' }))
      const link = element('a', '', { href: url, download: `dr-bean-analysis-${record.id}.json` }); link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
    }).className = 'secondary'
    details(result, 'Analysis identity, provenance and provider attempt', { id: record.id, digest: record.digest, verification: body.verification, provider_attempt_id: body.provider_attempt_id, execution_mode: body.execution_mode })
    root.append(result)
  }
  render()
  return { controller, connectionChanged: connection => controller.connect(connection) }
}
