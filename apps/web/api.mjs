// Requests follow apps/api/bean_api/main.py and generated DB-SC-1 schemas.
// The server validates semantics and owns every record identity and digest.
export class BeanApi {
  #token
  #keys = new Map()
  constructor(token, fetcher = globalThis.fetch.bind(globalThis)) { this.#token = token; this.fetcher = fetcher }
  async request(path, body) {
    const serialized = body === undefined ? undefined : JSON.stringify(body)
    const headers = { Authorization: `Bearer ${this.#token}` }
    if (serialized !== undefined) {
      headers['Content-Type'] = 'application/json'
      const operation = path + '\n' + serialized
      if (!this.#keys.has(operation)) this.#keys.set(operation, crypto.randomUUID())
      headers['Idempotency-Key'] = this.#keys.get(operation)
    }
    const response = await this.fetcher(`/api/bean/v1${path}`, {
      method: serialized === undefined ? 'GET' : 'POST', headers, body: serialized,
      credentials: 'omit', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(15000),
    })
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(`${error.code || response.status}: ${error.message || 'API request failed.'}${error.field_paths?.length ? ` Fields: ${error.field_paths.join(', ')}.` : ''}${error.current_revision_id ? ` Current revision: ${error.current_revision_id}.` : ''}${error.request_id ? ` Request: ${error.request_id}.` : ''}`)
    }
    return response
  }
  async json(path, body) { return (await this.request(path, body)).json() }
  async download(path, expected = {}) {
    const response = await this.request(path)
    const bytes = await response.arrayBuffer()
    const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('')
    if (response.headers.get('X-Artifact-SHA256') !== digest) throw new Error('Download byte digest mismatch; no file saved.')
    if ((expected.sha256 && expected.sha256 !== digest) || (expected.byte_size !== undefined && expected.byte_size !== bytes.byteLength)) {
      throw new Error('Download does not match the selected evidence reference; no file saved.')
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
