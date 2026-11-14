// Requests follow apps/api/bean_api/main.py and generated DB-SC-1 schemas.
// The server validates semantics and owns every record identity and digest.

export const MAX_JSON_BYTES = 8 * 1024 * 1024       // largest JSON body this client will parse
export const MAX_DOWNLOAD_BYTES = 16 * 1024 * 1024  // largest artifact this client will hold in memory

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
  #keys = new Map()
  constructor(token, fetcher = globalThis.fetch.bind(globalThis)) { this.#token = token; this.fetcher = fetcher }
  async request(path, body) {
    const serialized = body === undefined ? undefined : JSON.stringify(body)
    const headers = { Authorization: `Bearer ${this.#token}` }
    if (serialized !== undefined) {
      headers['Content-Type'] = 'application/json'
      // One operation key per distinct request. A retry of the same request reuses it, so an
      // uncertain outcome can be resolved without creating a second operation.
      const operation = path + '\n' + serialized
      if (!this.#keys.has(operation)) this.#keys.set(operation, crypto.randomUUID())
      headers['Idempotency-Key'] = this.#keys.get(operation)
    }
    let response
    try {
      response = await this.fetcher(`/api/bean/v1${path}`, {
        method: serialized === undefined ? 'GET' : 'POST', headers, body: serialized,
        credentials: 'omit', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(15000),
      })
    } catch {
      // Never resent automatically. The person decides; the same key is reused if they retry.
      throw serialized === undefined
        ? new ApiError('unreachable', 'No answer from the local backend. Nothing was changed. Check that it is running, then try again.')
        : new ApiError('uncertain', 'No answer arrived, so this request may or may not have been accepted. Trying again is safe: it repeats the same operation and cannot create a second one.')
    }
    if (!response.ok) {
      let error = {}
      try { error = parseJson(await readBounded(response, 65536)) } catch { /* keep the status-only message */ }
      const fields = Array.isArray(error.field_paths) ? error.field_paths.slice(0, 50) : []
      throw new ApiError('rejected', `${error.code || response.status}: ${error.message || 'The request was refused.'}${fields.length ? ` Fields: ${fields.join(', ')}.` : ''}${error.current_revision_id ? ` Current revision: ${error.current_revision_id}.` : ''}${error.request_id ? ` Request: ${error.request_id}.` : ''}`,
        { status: response.status, code: error.code, fieldPaths: fields, currentRevisionId: error.current_revision_id, requestId: error.request_id })
    }
    return response
  }
  async json(path, body) { return parseJson(await readBounded(await this.request(path, body), MAX_JSON_BYTES)) }
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
