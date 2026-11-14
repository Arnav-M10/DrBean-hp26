// Requests follow apps/api/bean_api/main.py and generated DB-SC-1 schemas.
// The server validates semantics and owns every record identity and digest.

export const MAX_JSON_BYTES = 8 * 1024 * 1024       // largest JSON body this client will parse
export const MAX_DOWNLOAD_BYTES = 16 * 1024 * 1024  // largest artifact this client will hold in memory

export function liveGeminiAvailable(capabilities) {
  return capabilities?.gemini?.dispatch_enabled === true
    && capabilities.gemini.execution_mode === 'live'
    && typeof capabilities.gemini.model === 'string' && capabilities.gemini.model.length > 0
}

// kind 'rejected': the server answered and refused; nothing was accepted.
// kind 'uncertain': a mutation was sent and no answer arrived; it may have been accepted.
// kind 'unreachable': a read got no answer; nothing changed.
// kind 'too_large' / 'malformed': the answer could not be used safely.
export class ApiError extends Error {
  constructor(kind, message, detail = {}) { super(message); this.name = 'ApiError'; this.kind = kind; Object.assign(this, detail) }
}

async function readBounded(response, limit) {
  const tooLarge = () => new ApiError('too_large', `The server response is larger than this page accepts (${limit} bytes).`)
  if (Number(response.headers.get('Content-Length')) > limit) throw tooLarge()
  if (!response.body?.getReader) {
    const bytes = new Uint8Array(await response.arrayBuffer())
    if (bytes.length > limit) throw tooLarge()
    return bytes
  }
  const reader = response.body.getReader(), chunks = []
  let total = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    total += value.length
    if (total > limit) { await reader.cancel(); throw tooLarge() }
    chunks.push(value)
  }
  const bytes = new Uint8Array(total)
  let offset = 0
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length }
  return bytes
}

function parseJson(bytes) {
  try { return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)) } catch {
    throw new ApiError('malformed', 'The server response was not valid JSON.')
  }
}

export class BeanApi {
  #token
  #mode
  #keys = new Map()
  #connectionFailure = () => {}
  constructor(token, fetcher = globalThis.fetch.bind(globalThis), { mode = 'local_bearer' } = {}) {
    if (!['local_bearer', 'browser_session'].includes(mode)) throw new Error('Unsupported connection mode.')
    if (mode === 'browser_session' && token) throw new Error('Browser sessions cannot use bearer credentials.')
    this.#token = token; this.#mode = mode; this.fetcher = fetcher
  }
  setConnectionFailureHandler(handler) {
    if (typeof handler !== 'function') throw new TypeError('A connection failure handler must be a function.')
    this.#connectionFailure = handler
  }
  #notifyConnectionFailure(error) {
    // Notification is presentation only. A broken observer cannot change the
    // original request outcome or trigger a transport retry here.
    try { Promise.resolve(this.#connectionFailure(error)).catch(() => {}) } catch { /* preserve the request error */ }
  }
  async request(path, body, mediaType = 'application/json', operationKey, extraHeaders = {}, { raw = false } = {}) {
    if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//') || path.includes('\\')) throw new Error('A local API path is required.')
    const structuredJson = mediaType === 'application/json' && !raw
    const serialized = body === undefined ? undefined : structuredJson ? JSON.stringify(body) : body
    const headers = {}
    for (const [name, value] of Object.entries(extraHeaders)) {
      if (name !== 'X-Source-Name' || typeof value !== 'string' || value.length > 255 || !/^[\x20-\x7e]+$/.test(value) || /[/\\]/.test(value)) throw new Error('Invalid source filename metadata.')
      headers[name] = value
    }
    if (this.#token) headers.Authorization = `Bearer ${this.#token}`
    if (serialized !== undefined) {
      if (typeof mediaType !== 'string' || mediaType.length > 255 || !/^[\x20-\x7e]+$/.test(mediaType)) throw new Error('Invalid source media type.')
      headers['Content-Type'] = mediaType
      // One operation key per distinct request. A retry of the same request reuses it, so an
      // uncertain outcome can be resolved without creating a second operation.
      const identity = structuredJson ? serialized : Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', serialized)), b => b.toString(16).padStart(2, '0')).join('')
      const operation = path + '\n' + mediaType + '\n' + identity + '\n' + JSON.stringify(extraHeaders)
      if (!this.#keys.has(operation)) this.#keys.set(operation, crypto.randomUUID())
      headers['Idempotency-Key'] = operationKey ?? this.#keys.get(operation)
    }
    let response
    try {
      response = await this.fetcher(`/api/bean/v1${path}`, {
        method: serialized === undefined ? 'GET' : 'POST', headers, body: serialized,
        credentials: this.#mode === 'browser_session' ? 'same-origin' : 'omit', cache: 'no-store', redirect: 'error',
        signal: AbortSignal.timeout(/^\/workspaces\/[^/]+\/(intake-proposals|assistant-turns|research-analyses)$/.test(path) ? 75000 : 15000),
      })
    } catch {
      // Never resent automatically. The person decides; the same key is reused if they retry.
      const error = serialized === undefined
        ? new ApiError('unreachable', 'No answer from the local backend. Nothing was changed. Check that it is running, then try again.')
        : new ApiError('uncertain', 'No answer arrived, so this request may or may not have been accepted. Trying again is safe: it repeats the same operation and cannot create a second one.')
      this.#notifyConnectionFailure(error)
      throw error
    }
    if (!response.ok) {
      let error = {}
      try { error = parseJson(await readBounded(response, 65536)) } catch { /* keep the status-only message */ }
      const fields = Array.isArray(error.field_paths) ? error.field_paths.slice(0, 50) : []
      const refusal = new ApiError('rejected', `${error.code || response.status}: ${error.message || 'The request was refused.'}${fields.length ? ` Fields: ${fields.join(', ')}.` : ''}${error.current_revision_id ? ` Current revision: ${error.current_revision_id}.` : ''}${error.request_id ? ` Request: ${error.request_id}.` : ''}`,
        { status: response.status, code: error.code, fieldPaths: fields, currentRevisionId: error.current_revision_id, requestId: error.request_id })
      if (response.status === 401) this.#notifyConnectionFailure(refusal)
      throw refusal
    }
    return response
  }
  async json(path, body, operationKey) { return parseJson(await readBounded(await this.request(path, body, 'application/json', operationKey), MAX_JSON_BYTES)) }
  async assistantTurn(workspace, body) {
    if (typeof body.client_operation_id !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(body.client_operation_id)) throw new Error('A bounded assistant operation identity is required.')
    return parseJson(await readBounded(await this.request(`/workspaces/${encodeURIComponent(workspace)}/assistant-turns`, body, 'application/json', body.client_operation_id), MAX_JSON_BYTES))
  }
  async researchAnalysis(workspace, body) {
    if (typeof body.client_operation_id !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(body.client_operation_id)) throw new Error('A bounded research operation identity is required.')
    return parseJson(await readBounded(await this.request(`/workspaces/${encodeURIComponent(workspace)}/research-analyses`, body, 'application/json', body.client_operation_id), MAX_JSON_BYTES))
  }
  async uploadResearchAsset(workspace, file, operationId) {
    if (operationId !== undefined && (typeof operationId !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(operationId))) throw new Error('A bounded upload operation identity is required.')
    if (!Number.isInteger(file.size) || file.size < 1 || file.size > 5242880) throw new Error('Choose a research file up to 5 MiB.')
    const bytes = await file.arrayBuffer()
    if (bytes.byteLength !== file.size) throw new Error('The research file changed while it was read.')
    // File type is only an admission hint: the server inspects the original bytes.
    const type = file.type || 'application/octet-stream', headers = {}
    // The optional wire filename is printable ASCII. Unicode names remain in the
    // page; the server supplies a safe fallback name without altering file bytes.
    if (typeof file.name === 'string' && file.name.length <= 255 && /^[\x20-\x7e]+$/.test(file.name) && !/[/\\]/.test(file.name)) headers['X-Source-Name'] = file.name
    return parseJson(await readBounded(await this.request(`/workspaces/${encodeURIComponent(workspace)}/research-assets`, bytes, type, operationId, headers, { raw: true }), MAX_JSON_BYTES))
  }
  async uploadSource(workspace, file, origin) {
    if (!['image/png', 'image/jpeg'].includes(file.type) || file.size < 1 || file.size > 5242880) throw new Error('Choose a PNG or JPEG up to 5 MiB.')
    if (!['synthetic', 'public'].includes(origin)) throw new Error('Declare synthetic or public source origin.')
    return parseJson(await readBounded(await this.request(`/workspaces/${encodeURIComponent(workspace)}/source-assets?origin=${origin}&retention=retain`, await file.arrayBuffer(), file.type), MAX_JSON_BYTES))
  }
  // A matching digest shows the bytes arrived intact and are the selected object; it is not a scientific check.
  async download(path, expected = {}) {
    const response = await this.request(path)
    const bytes = (await readBounded(response, MAX_DOWNLOAD_BYTES)).buffer
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('')
    if (response.headers.get('X-Artifact-SHA256') !== digest) throw new ApiError('malformed', 'Download byte digest mismatch; no file saved.')
    if ((expected.sha256 && expected.sha256 !== digest) || (expected.byte_size !== undefined && expected.byte_size !== bytes.byteLength)) {
      throw new ApiError('malformed', 'Download does not match the selected evidence reference; no file saved.')
    }
    return { bytes, digest }
  }
}
export function baselineAvailable(capabilities) {
  return capabilities?.contract_version === 'DB-SC-1' && capabilities?.policy_version === 'GF-2'
    && capabilities.science?.available === true && capabilities.science?.baseline_discovery === true
}

export function baselineExplanation(result) {
  if (['review', 'recheck'].includes(result.native_replay?.operation)) {
    if (result.verification !== 'valid' || result.expected_binding !== 'matches' || result.replay !== 'passed') {
      return 'Follow-up checking is incomplete or its evidence does not match. Inspect the recorded candidate states and reason before drawing a conclusion.'
    }
    return 'This follow-up rechecked the two previously selected candidates against the revised observations. Review each candidate below. Excluding both leaves other parameter assignments unexamined and does not establish global model inconsistency.'
  }
  if (result.scientific_outcome === 'certified_counterexample' && result.verification === 'valid'
      && result.expected_binding === 'matches' && result.replay === 'passed') {
    return 'A freshly checked parameter assignment is compatible with the reviewed hard bounds and has ke strictly outside the closed claim. The claim is challenged under these assumptions; this does not identify the true physical model.'
  }
  if (result.scientific_outcome === 'no_counterexample_found') {
    return 'The bounded search found no checked counterexample. This does not prove that every compatible parameter assignment lies inside the claim.'
  }
  if (result.scientific_outcome === 'numerical_candidate') {
    return 'The search returned a numerical candidate. Its numerical fit alone does not establish a checked counterexample.'
  }
  if (result.scientific_outcome === 'unsupported') return 'This investigation is unsupported by the configured scientific runtime. No scientific conclusion was established.'
  return 'Read the scientific outcome and checking states separately. Incomplete or unsuccessful checking does not prove the claim.'
}
