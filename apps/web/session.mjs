import { ApiError, BeanApi } from './api.mjs'

// The session secret lives exclusively in the secure HttpOnly cookie. Callers
// receive an authenticated transport and nonsecret workspace metadata only.
export async function bootstrapSharedSession(fetcher = globalThis.fetch.bind(globalThis)) {
  const api = new BeanApi(null, fetcher, { mode: 'browser_session' })
  let session
  try { session = await api.json('/shared-session') } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
  if (session?.mode !== 'browser_session' || session.authenticated !== true || session.credentials !== 'server_managed'
    || typeof session.workspace_id !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(session.workspace_id)
    || Object.keys(session).sort().join(',') !== 'authenticated,credentials,mode,workspace_id') {
    throw new ApiError('malformed', 'The server did not establish a private browser session.')
  }
  return { api, session: Object.freeze(session) }
}
