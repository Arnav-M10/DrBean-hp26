import { ApiError, BeanApi } from './api.mjs'

const defaultFetch = (...args) => globalThis.fetch(...args)
const pending = new WeakMap()
const markerKey = 'dr-bean.private-workspace.v1'
const memoryMarkers = new WeakMap()
let unavailableStorageMarker = null
const pause = ms => new Promise(resolve => setTimeout(resolve, ms))
function browserStorage() { try { return globalThis.localStorage } catch { return undefined } }

function metadata(session) {
  if (session?.mode !== 'browser_session' || session.authenticated !== true || session.credentials !== 'server_managed'
    || typeof session.workspace_id !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(session.workspace_id)
    || Object.keys(session).sort().join(',') !== 'authenticated,credentials,mode,workspace_id') {
    throw new ApiError('malformed', 'The server did not establish a private browser session.')
  }
  return Object.freeze(session)
}

// Only these nonissuing connection reads may retry. Science, consent, session
// issuance/rotation and model requests never enter this helper.
export async function readConnection(api, path, delay = pause) {
  if (!['/shared-session/current', '/capabilities', '/workspaces'].includes(path)) throw new Error('Not a connection read.')
  for (let attempt = 0; ; attempt++) {
    try { return await api.json(path) } catch (error) {
      if (attempt >= 2 || !(error.kind === 'unreachable' || [502, 503, 504].includes(error.status))) throw error
      await delay([250, 750][attempt])
    }
  }
}

function recovery(message, code) {
  return new ApiError('session_recovery', message, { code, mayStartNew: true })
}

// Credentials live only in the HttpOnly cookie. The marker contains a workspace
// identifier (or "pending"), never authentication. It prevents a cleared/expired
// cookie or lost issuance response from silently replacing earlier research.
export function bootstrapSharedSession(fetcher = defaultFetch, {
  storage = browserStorage(), locks = globalThis.navigator?.locks, delay = pause, startNew = false,
} = {}) {
  if (pending.has(fetcher)) return pending.get(fetcher)
  const connect = async () => {
    const api = new BeanApi(null, fetcher, { mode: 'browser_session' })
    const memory = () => storage ? memoryMarkers.get(storage) ?? null : unavailableStorageMarker
    const remembered = () => { try { return storage?.getItem(markerKey) ?? memory() } catch { return memory() } }
    const remember = (value, required = false) => {
      try {
        if (value === null) storage?.removeItem(markerKey); else storage?.setItem(markerKey, value)
        if (required && (!storage || storage.getItem(markerKey) !== value)) throw new Error('Storage unavailable')
      } catch {
        if (required) throw new ApiError('session_recovery', 'Allow cookies and site storage for this site, then retry connection. A private workspace has not been created.', { code: 'session_storage_unavailable' })
      }
      if (storage) memoryMarkers.set(storage, value); else unavailableStorageMarker = value
    }
    let current
    try { current = metadata(await readConnection(api, '/shared-session/current', delay)) } catch (error) {
      if (error.status === 401 && error.code === 'browser_session_missing') {
        if (remembered() && !startNew) throw recovery('This browser no longer has access to its previous workspace. Retry to check an existing session, or start a new private workspace. Earlier research is retained on the server; it is not transferred to the new workspace.', 'session_lost')
      } else if (error.status === 401) {
        remember(remembered() || 'lost')
        if (!startNew) throw recovery('This private session has expired or been revoked. Earlier research is retained on the server. Start a new private workspace to continue.', 'session_expired')
        // The refused current request clears the stale cookie. Issuance below
        // still validates the cookie and fails closed if the browser retained it.
      } else { throw error }
    }
    if (current) {
      remember(current.workspace_id)
      return { api, session: current }
    }
    const previous = remembered()
    remember('pending', true)
    let issued
    try { issued = metadata(await api.json('/shared-session')) } catch (error) {
      if (error.kind === 'unreachable' || error.kind === 'malformed' || error.kind === 'too_large' || error.status >= 500) {
        throw recovery('The connection response did not arrive intact. A workspace may already exist. Retry connection to check the browser session before starting a new workspace.', 'session_uncertain')
      }
      remember(previous)
      throw error
    }
    remember(issued.workspace_id)
    let confirmed
    try { confirmed = metadata(await readConnection(api, '/shared-session/current', delay)) } catch (error) {
      if (error.status === 401) throw recovery('The browser did not retain its private session. Allow cookies for this site, then retry. A new workspace requires your explicit choice.', 'session_cookie_unavailable')
      throw error
    }
    if (confirmed.workspace_id !== issued.workspace_id) throw recovery('The browser session changed while connecting. Retry to read the current session before continuing.', 'session_changed')
    return { api, session: confirmed }
  }
  // Secure-context Web Locks serialize first visits across tabs. The in-flight
  // promise also prevents duplicate requests in this page without Web Locks.
  const task = Promise.resolve().then(() => locks?.request
    ? locks.request('dr-bean-private-session', connect) : connect())
  pending.set(fetcher, task)
  task.finally(() => { if (pending.get(fetcher) === task) pending.delete(fetcher) }).catch(() => {})
  return task
}
