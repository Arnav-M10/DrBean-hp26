import { readFile, open } from 'node:fs/promises'
import { constants } from 'node:fs'
import { createServer, request as upstreamRequest } from 'node:http'
import { timingSafeEqual } from 'node:crypto'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const SESSION_COOKIE = '__Host-bean_session'
const TOKEN = /^[A-Za-z0-9_-]{43}$/
const PROXY_HEADER = 'x-bean-vercel-proxy'
const CLEAR_COOKIE = `${SESSION_COOKIE}=""; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Strict`
const SAFE_HEADERS = { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY' }

export function shareOrigin(value) {
  if (typeof value !== 'string' || !/^https:\/\/[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com$/.test(value)) {
    throw new Error('A specific HTTPS Quick Tunnel origin is required.')
  }
  return new URL(value)
}

async function gatewaySecret(file) {
  const handle = await open(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK)
  try {
    const info = await handle.stat()
    if (!info.isFile() || info.uid !== process.getuid() || (info.mode & 0o777) !== 0o600 || info.size > 1024) throw new Error('Invalid gateway credential file.')
    const record = JSON.parse(await handle.readFile('utf8'))
    if (record.version !== 1 || !TOKEN.test(record.secret) || Object.keys(record).sort().join(',') !== 'secret,version') throw new Error('Invalid gateway credential file.')
    return record.secret
  } finally { await handle.close() }
}

// This is a separate hop credential, never the API's gateway or provider key.
// Read on each proxied request so a private, atomic config replacement rotates
// the credential without restarting the scientific API or changing its origin.
async function proxyConfig(file) {
  const handle = await open(file, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK)
  try {
    const info = await handle.stat()
    if (!info.isFile() || info.uid !== process.getuid() || (info.mode & 0o777) !== 0o600 || info.size > 1024) throw new Error('Invalid proxy configuration.')
    const record = JSON.parse(await handle.readFile('utf8'))
    if (Object.keys(record).sort().join(',') !== 'origin,secret,version' || record.version !== 1
      || typeof record.secret !== 'string' || !TOKEN.test(record.secret)
      || typeof record.origin !== 'string'
      || !/^https:\/\/(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}$/.test(record.origin)) throw new Error('Invalid proxy configuration.')
    const origin = new URL(record.origin)
    if (origin.origin !== record.origin || origin.hostname.endsWith('.localhost')) throw new Error('Invalid proxy configuration.')
    return { origin, secret: record.secret }
  } finally { await handle.close() }
}

function browserCookie(value) {
  if (value === undefined) return undefined
  if (typeof value !== 'string' || value.length > 8192) throw new Error('Invalid session cookie.')
  const cookies = value.split(';').map(part => part.trim()).filter(part => part.split('=', 1)[0] === SESSION_COOKIE)
  if (!cookies.length) return undefined
  if (cookies.length !== 1 || !TOKEN.test(cookies[0].slice(SESSION_COOKIE.length + 1)) || !cookies[0].startsWith(`${SESSION_COOKIE}=`)) throw new Error('Invalid session cookie.')
  return cookies[0]
}

function responseCookie(values) {
  if (values === undefined) return undefined
  if (!Array.isArray(values) || values.length !== 1 || values[0].length > 1024) throw new Error('Invalid upstream session cookie.')
  const [pair, ...parts] = values[0].split(';').map(part => part.trim())
  if (!pair.startsWith(`${SESSION_COOKIE}=`)) throw new Error('Invalid upstream session cookie.')
  const value = pair.slice(SESSION_COOKIE.length + 1), attributes = new Map()
  for (const part of parts) {
    const index = part.indexOf('='), name = (index < 0 ? part : part.slice(0, index)).toLowerCase()
    if (attributes.has(name) || !['path', 'secure', 'httponly', 'samesite', 'max-age', 'expires'].includes(name)) throw new Error('Invalid upstream session cookie.')
    attributes.set(name, index < 0 ? '' : part.slice(index + 1))
  }
  if (attributes.get('path') !== '/' || attributes.get('secure') !== '' || attributes.get('httponly') !== ''
    || attributes.get('samesite')?.toLowerCase() !== 'strict'
    || (!TOKEN.test(value) && !(['', '""'].includes(value) && attributes.get('max-age') === '0'))
    || !/^\d{1,5}$/.test(attributes.get('max-age') ?? '') || Number(attributes.get('max-age')) > 86400
    || (attributes.has('expires') && !Number.isFinite(Date.parse(attributes.get('expires'))))) throw new Error('Invalid upstream session cookie.')
  return values
}

function repeatedHeader(request, names) {
  const counts = new Map()
  for (let index = 0; index < request.rawHeaders.length; index += 2) {
    const name = request.rawHeaders[index].toLowerCase()
    if (names.includes(name)) counts.set(name, (counts.get(name) ?? 0) + 1)
  }
  return [...counts.values()].some(count => count > 1)
}

export function createShareGateway({ originFile, gatewayFile, proxyFile = join(dirname(originFile), 'vercel-proxy.json'), webPort = 4173, apiPort = 8000 }) {
  for (const port of [webPort, apiPort]) if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid loopback upstream port.')
  return createServer(async (request, response) => {
    let origin
    try {
      const raw = await readFile(originFile, 'utf8')
      if (raw.length > 1024) throw new Error('Oversize origin record.')
      origin = shareOrigin(JSON.parse(raw).origin)
    } catch {
      response.writeHead(503, SAFE_HEADERS).end('Shared link is not ready.')
      return
    }
    // A Vercel alias is admitted only with a separate server-injected proof and
    // exact configured browser host. An attempted alias never falls back to the
    // ordinary tunnel path, including when its private config is unavailable.
    let browserOrigin = origin, viaProxy = false
    if (request.headers[PROXY_HEADER] !== undefined) {
      let config
      try { config = await proxyConfig(proxyFile) } catch {
        response.writeHead(503, SAFE_HEADERS).end('Public proxy is not ready.')
        return
      }
      const supplied = request.headers[PROXY_HEADER]
      if (typeof supplied !== 'string' || !TOKEN.test(supplied)
        || !timingSafeEqual(Buffer.from(supplied), Buffer.from(config.secret))
        || request.headers['x-forwarded-host'] !== config.origin.host) {
        response.writeHead(403, SAFE_HEADERS).end()
        return
      }
      browserOrigin = config.origin
      viaProxy = true
    }
    // Cloudflare terminates HTTPS; only the exact operator-approved boundary is
    // accepted. No request can choose an upstream or supply its trusted headers.
    const site = request.headers['sec-fetch-site']
    // A visitor may follow the public page link from another site. Only the
    // top-level entry document gets this exception; its API and subresource
    // requests must still originate from the approved page.
    const entryNavigation = ['GET', 'HEAD'].includes(request.method)
      && ['/', '/index.html', '/workspace-preview/', '/workspace-preview/index.html', '/study', '/study/', '/study/index.html', '/study/app', '/study/app.html'].includes(request.url?.split('?')[0])
      && request.headers['sec-fetch-mode'] === 'navigate' && request.headers['sec-fetch-dest'] === 'document'
    if (request.headers.host !== origin.host || request.headers['x-forwarded-proto'] !== 'https'
      || (request.headers['x-forwarded-host'] && request.headers['x-forwarded-host'] !== browserOrigin.host)
      || (request.headers.origin !== undefined && request.headers.origin !== browserOrigin.origin)
      || (site && !['same-origin', 'none'].includes(site) && !(entryNavigation && ['cross-site', 'same-site'].includes(site)))
      || (viaProxy && site && site !== 'same-origin' && !entryNavigation)
      || (request.method === 'POST' && (request.headers.origin !== browserOrigin.origin || (site && site !== 'same-origin')))
      || repeatedHeader(request, ['host', 'origin', 'x-forwarded-proto', 'x-forwarded-host', 'sec-fetch-site', PROXY_HEADER])) {
      response.writeHead(403, SAFE_HEADERS).end()
      return
    }
    if (!['GET', 'HEAD', 'POST'].includes(request.method)
      || !request.url?.startsWith('/') || request.url.startsWith('//') || request.url.includes('\\')) {
      response.writeHead(405, SAFE_HEADERS).end()
      return
    }
    const isApi = request.url.startsWith('/api/bean/v1/'), port = isApi ? apiPort : webPort
    const headers = { host: `127.0.0.1:${port}` }
    if (isApi) {
      let cookie
      try { cookie = browserCookie(request.headers.cookie) } catch {
        response.writeHead(401, { ...SAFE_HEADERS, 'Set-Cookie': CLEAR_COOKIE }).end('Invalid browser session.')
        return
      }
      try { headers['x-bean-shared-gateway'] = await gatewaySecret(gatewayFile) } catch {
        response.writeHead(503, SAFE_HEADERS).end('Shared access is not ready.')
        return
      }
      headers['x-bean-shared-origin'] = origin.origin
      if (cookie) headers.cookie = cookie
      // The API retains its exact existing canonical tunnel boundary. A public
      // browser origin is translated only after every proxy/origin check above.
      if (request.headers.origin) headers.origin = origin.origin
      for (const name of ['content-type', 'idempotency-key', 'x-source-name']) {
        const value = request.headers[name]
        if (value !== undefined) {
          if (typeof value !== 'string' || value.length > (name === 'idempotency-key' ? 128 : 255) || !/^[\x20-\x7e]+$/.test(value)
            || (name === 'x-source-name' && /[/\\]/.test(value))) {
            response.writeHead(400, SAFE_HEADERS).end('Invalid request metadata.')
            return
          }
          headers[name] = value
        }
      }
    }
    const upstream = upstreamRequest({ hostname: '127.0.0.1', port,
      method: request.method, path: request.url, headers }, result => {
      const safe = { ...SAFE_HEADERS }
      try {
        const cookie = isApi ? responseCookie(result.headers['set-cookie']) : undefined
        if (cookie) safe['Set-Cookie'] = cookie
      } catch {
        result.resume()
        response.writeHead(502, SAFE_HEADERS).end('Invalid shared server response.')
        return
      }
      for (const name of ['content-type', 'content-disposition', 'x-artifact-sha256', 'x-request-id']) {
        if (result.headers[name]) safe[name] = result.headers[name]
      }
      response.writeHead(result.statusCode, safe)
      result.pipe(response)
    })
    upstream.setTimeout(75000, () => upstream.destroy())
    upstream.on('error', () => {
      if (!response.headersSent) response.writeHead(502, { ...SAFE_HEADERS, 'Content-Type': 'application/json' })
      response.end(JSON.stringify({ code: 'shared_backend_unavailable', message: 'The shared server is temporarily unavailable.' }))
    })
    request.on('aborted', () => upstream.destroy())
    request.pipe(upstream)
  })
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const port = Number(process.argv[2] ?? 4174)
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error('Invalid sharing port.')
  const originFile = process.env.BEAN_SHARE_ORIGIN_FILE, gatewayFile = process.env.BEAN_SHARE_GATEWAY_FILE
  if (!originFile || !gatewayFile) throw new Error('BEAN_SHARE_ORIGIN_FILE and BEAN_SHARE_GATEWAY_FILE are required.')
  const server = createShareGateway({ originFile, gatewayFile,
    webPort: Number(process.env.BEAN_SHARE_WEB_PORT ?? 4173), apiPort: Number(process.env.BEAN_SHARE_API_PORT ?? 8000) })
  server.listen(port, '127.0.0.1', () => console.log(`Dr. Bean sharing gateway on 127.0.0.1:${server.address().port}`))
}
