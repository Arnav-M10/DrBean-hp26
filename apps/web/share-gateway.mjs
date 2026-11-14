import { readFile, open } from 'node:fs/promises'
import { constants } from 'node:fs'
import { createServer, request as upstreamRequest } from 'node:http'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export function shareOrigin(value) {
  if (typeof value !== 'string' || !/^https:\/\/[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com$/.test(value)) {
    throw new Error('A specific HTTPS Quick Tunnel origin is required.')
  }
  return new URL(value)
}

async function demoToken(file) {
  const handle = await open(file, constants.O_RDONLY | constants.O_NOFOLLOW)
  try {
    const info = await handle.stat()
    if (!info.isFile() || info.uid !== process.getuid() || (info.mode & 0o777) !== 0o600 || info.size > 1024) throw new Error('Invalid demo credential file.')
    const token = JSON.parse(await handle.readFile('utf8')).token
    if (typeof token !== 'string' || !/^[A-Za-z0-9_-]{32,128}$/.test(token)) throw new Error('Invalid demo credential.')
    return token
  } finally { await handle.close() }
}

export function createShareGateway({ originFile, accessFile, webPort = 4173 }) {
  if (!Number.isInteger(webPort) || webPort < 1 || webPort > 65535) throw new Error('Invalid loopback web port.')
  return createServer(async (request, response) => {
    let origin
    try {
      const raw = await readFile(originFile, 'utf8')
      if (raw.length > 1024) throw new Error('Oversize origin record.')
      origin = shareOrigin(JSON.parse(raw).origin)
    } catch {
      response.writeHead(503, { 'Cache-Control': 'no-store' }).end('Shared link is not ready.')
      return
    }
    // Only the exact operator-approved HTTPS tunnel may reach this boundary.
    // Never trust arbitrary forwarded hosts or let a browser select an upstream.
    if (request.headers.host !== origin.host || request.headers['x-forwarded-proto'] !== 'https'
      || (request.headers.origin && request.headers.origin !== origin.origin)
      || request.headers['sec-fetch-site'] === 'cross-site') {
      response.writeHead(403, { 'Cache-Control': 'no-store' }).end()
      return
    }
    if (!['GET', 'HEAD', 'POST'].includes(request.method)
      || !request.url?.startsWith('/') || request.url.startsWith('//') || request.url.includes('\\')) {
      response.writeHead(405, { 'Cache-Control': 'no-store' }).end()
      return
    }
    let token
    if (request.url.startsWith('/api/bean/v1/')) {
      try { token = await demoToken(accessFile) } catch {
        response.writeHead(503, { 'Cache-Control': 'no-store' }).end('Shared demo is not ready.')
        return
      }
      if (request.url === '/api/bean/v1/shared-session' && request.method === 'GET') {
        response.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' })
        response.end(JSON.stringify({ mode: 'shared_demo', shared_data: true, credentials: 'server_managed' }))
        return
      }
    }
    const localHost = `127.0.0.1:${webPort}`
    const headers = { host: localHost }
    // A public visitor can use only the isolated demo identity. Ignore any
    // browser-supplied owner token; neither credential is returned to the browser.
    if (token) headers.authorization = `Bearer ${token}`
    for (const name of ['content-type', 'idempotency-key']) {
      if (request.headers[name]) headers[name] = request.headers[name]
    }
    if (request.headers.origin) headers.origin = `http://${localHost}`
    const upstream = upstreamRequest({ hostname: '127.0.0.1', port: webPort,
      method: request.method, path: request.url, headers }, result => {
      const safe = { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
        'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY' }
      for (const name of ['content-type', 'content-disposition', 'x-artifact-sha256', 'x-request-id']) {
        if (result.headers[name]) safe[name] = result.headers[name]
      }
      response.writeHead(result.statusCode, safe)
      result.pipe(response)
    })
    upstream.setTimeout(75000, () => upstream.destroy())
    upstream.on('error', () => {
      if (!response.headersSent) response.writeHead(502, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' })
      response.end(JSON.stringify({ code: 'shared_backend_unavailable', message: 'The shared server is temporarily unavailable.' }))
    })
    request.on('aborted', () => upstream.destroy())
    request.pipe(upstream)
  })
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const port = Number(process.argv[2] ?? 4174)
  if (!Number.isInteger(port) || port < 0 || port > 65535) throw new Error('Invalid sharing port.')
  const originFile = process.env.BEAN_SHARE_ORIGIN_FILE
  if (!originFile) throw new Error('BEAN_SHARE_ORIGIN_FILE is required.')
  const accessFile = process.env.BEAN_SHARE_ACCESS_FILE
  if (!accessFile) throw new Error('BEAN_SHARE_ACCESS_FILE is required.')
  const server = createShareGateway({ originFile, accessFile })
  server.listen(port, '127.0.0.1', () => console.log(`Dr. Bean sharing gateway on 127.0.0.1:${server.address().port}`))
}
