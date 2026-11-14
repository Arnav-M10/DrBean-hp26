// Trusted application transport only. The static preview imports this module
// solely after its same-origin manifest declares connected mode available.
import { ApiError } from './api.mjs'
import { bootstrapSharedSession, readConnection } from './session.mjs'

const ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/
const HEX = /^[a-f0-9]{64}$/
const defaultFetch = (...args) => globalThis.fetch(...args)

function malformed(message) { return new ApiError('malformed', message) }
function identifier(value) {
  if (typeof value !== 'string' || !ID.test(value)) throw malformed('Invalid comparison record identity.')
  return encodeURIComponent(value)
}

// DB-SC-1's canonical byte profile, used here only to check transport binding.
// Digest agreement never establishes scientific correctness or exact proof.
export function comparisonCanonical(value, depth = 0) {
  if (depth > 32) throw malformed('Comparison JSON exceeds its nesting limit.')
  if (value === null || typeof value === 'boolean') return JSON.stringify(value)
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value) || value < 0 || Object.is(value, -0)) throw malformed('Use decimal strings for scientific values.')
    return JSON.stringify(value)
  }
  if (typeof value === 'string') {
    if (!value.isWellFormed()) throw malformed('Invalid comparison text encoding.')
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) return '[' + value.map(item => comparisonCanonical(item, depth + 1)).join(',') + ']'
  if (value && Object.getPrototypeOf(value) === Object.prototype) {
    const keys = Object.keys(value).sort()
    if (keys.some(key => !/^[\x00-\x7f]*$/.test(key))) throw malformed('Comparison schema keys must be ASCII.')
    return '{' + keys.map(key => JSON.stringify(key) + ':' + comparisonCanonical(value[key], depth + 1)).join(',') + '}'
  }
  throw malformed('Invalid comparison JSON value.')
}

async function digest(value) {
  const bytes = new TextEncoder().encode(comparisonCanonical(value))
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), byte => byte.toString(16).padStart(2, '0')).join('')
}
function immutable(value) {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(immutable)
    Object.freeze(value)
  }
  return value
}

async function checkedRecord(record, workspaceId, { id, request } = {}) {
  if (!record || record.kind !== 'model_comparison' || record.workspace_id !== workspaceId
    || !ID.test(record.id ?? '') || (id !== undefined && record.id !== id)
    || record.body?.schema_version !== 'DB-MODEL-COMPARISON-RESULT-1'
    || !['completed', 'unsupported', 'fit_failed', 'budget_exceeded'].includes(record.body.status)
    || record.body.exact_verification !== 'not_performed'
    || record.body.request?.schema_version !== 'DB-MODEL-COMPARISON-1'
    || !HEX.test(record.body.input_digest ?? '') || !HEX.test(record.body.source_digest ?? '')
    || !HEX.test(record.digest ?? '')) throw malformed('The comparison response does not match this private workspace and contract.')
  if ((request && comparisonCanonical(request) !== comparisonCanonical(record.body.request))
    || await digest(record.body.request) !== record.body.input_digest
    || await digest(record.body) !== record.digest) throw malformed('The comparison response does not match its reviewed input or recorded bytes.')
  return immutable(record)
}

export async function connectComparison({ startNew = false, fetcher = defaultFetch, sessionOptions = {} } = {}) {
  const { api, session } = await bootstrapSharedSession(fetcher, { ...sessionOptions, startNew })
  const capabilities = (await readConnection(api, '/capabilities', sessionOptions.delay)).model_comparison
  if (capabilities?.available !== true || capabilities.contract_version !== 'DB-MODEL-COMPARISON-1'
    || capabilities.result_contract_version !== 'DB-MODEL-COMPARISON-RESULT-1'
    || capabilities.execution_mode !== 'numerical_offline' || capabilities.provider_calls !== 0
    || capabilities.verification !== 'not_performed') {
    throw new ApiError('not_available', 'This application server does not provide the supported offline numerical comparison workflow.')
  }
  const workspaceId = session.workspace_id
  const path = `/workspaces/${identifier(workspaceId)}/model-comparisons`
  return Object.freeze({
    workspaceId, session, capabilities: immutable(capabilities),
    // Each invocation is a person-authorized operation. No mutation is retried
    // automatically. Repeating identical bytes reuses BeanApi's operation key.
    async submit(request, { operationKey } = {}) {
      if (request?.schema_version !== 'DB-MODEL-COMPARISON-1' || request.approval !== 'approved_for_this_request'
        || request.review?.reviewed !== true) throw new ApiError('review_required', 'Review these inputs and explicitly approve this numerical comparison before submitting.')
      const snapshot = JSON.parse(comparisonCanonical({ instrument: null, ...request }))
      if (new TextEncoder().encode(comparisonCanonical(snapshot)).length > 131072) throw new ApiError('too_large', 'Comparison input exceeds 128 KiB.')
      if (operationKey !== undefined && (typeof operationKey !== 'string' || !/^[\x21-\x7e]{1,128}$/.test(operationKey))) throw malformed('Invalid comparison operation key.')
      return checkedRecord(await api.json(path, snapshot, operationKey), workspaceId, { request: snapshot })
    },
    async list() {
      const records = await api.json(path)
      if (!Array.isArray(records)) throw malformed('The server did not return comparison history.')
      return Promise.all(records.map(record => checkedRecord(record, workspaceId)))
    },
    async get(id) { return checkedRecord(await api.json(`${path}/${identifier(id)}`), workspaceId, { id }) },
    async download(record) {
      await checkedRecord(record, workspaceId)
      const downloaded = await api.download(`${path}/${identifier(record.id)}/download`)
      let packet
      try { packet = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(downloaded.bytes)) } catch { throw malformed('The comparison export is not valid UTF-8 JSON.') }
      if (packet?.schema_version !== 'DB-MODEL-COMPARISON-EXPORT-1') throw malformed('Unsupported comparison export contract.')
      await checkedRecord(packet.result, workspaceId, { id: record.id, request: record.body.request })
      if (comparisonCanonical(packet.result) !== comparisonCanonical(record)) throw malformed('The download does not match the selected comparison record.')
      return { ...downloaded, filename: `${record.id}.json`, record }
    },
    setConnectionFailureHandler(handler) { api.setConnectionFailureHandler(handler) },
  })
}
