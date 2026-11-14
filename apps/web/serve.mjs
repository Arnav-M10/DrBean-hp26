import { readFile, open } from 'node:fs/promises';
import { constants } from 'node:fs';
import { createServer, request as upstreamRequest } from 'node:http';

const host = '127.0.0.1';
const port = Number(process.argv[2] ?? 4173);
const apiPort = Number(process.env.BEAN_WEB_API_PORT ?? 8000);
const gatewayFile = process.env.BEAN_LOCAL_GATEWAY_FILE;
const SESSION_COOKIE = 'bean_local_session';
const TOKEN = /^[A-Za-z0-9_-]{43}$/;
const CLEAR_COOKIE = `${SESSION_COOKIE}=""; Max-Age=0; Path=/; HttpOnly; SameSite=Strict`;
const SAFE_HEADERS = { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY' };

async function gatewaySecret() {
  if (!gatewayFile) throw new Error('Local access is not configured.');
  const handle = await open(gatewayFile, constants.O_RDONLY | constants.O_NOFOLLOW | constants.O_NONBLOCK);
  try {
    const info = await handle.stat();
    if (!info.isFile() || info.uid !== process.getuid() || (info.mode & 0o777) !== 0o600 || info.size > 1024) throw new Error('Invalid local access configuration.');
    const record = JSON.parse(await handle.readFile('utf8'));
    if (record?.version !== 1 || !TOKEN.test(record.secret) || Object.keys(record).sort().join(',') !== 'secret,version') throw new Error('Invalid local access configuration.');
    return record.secret;
  } finally { await handle.close(); }
}

function browserCookie(value) {
  if (value === undefined) return undefined;
  if (typeof value !== 'string' || value.length > 8192) throw new Error('Invalid browser session.');
  const matches = value.split(';').map(part => part.trim()).filter(part => part.split('=', 1)[0] === SESSION_COOKIE);
  if (!matches.length) return undefined;
  if (matches.length !== 1 || !matches[0].startsWith(`${SESSION_COOKIE}=`) || !TOKEN.test(matches[0].slice(SESSION_COOKIE.length + 1))) throw new Error('Invalid browser session.');
  return matches[0];
}

function responseCookie(values) {
  if (values === undefined) return undefined;
  if (!Array.isArray(values) || values.length !== 1 || values[0].length > 1024) throw new Error('Invalid upstream session cookie.');
  const [pair, ...parts] = values[0].split(';').map(part => part.trim());
  if (!pair.startsWith(`${SESSION_COOKIE}=`)) throw new Error('Invalid upstream session cookie.');
  const value = pair.slice(SESSION_COOKIE.length + 1), attributes = new Map();
  for (const part of parts) {
    const index = part.indexOf('='), name = (index < 0 ? part : part.slice(0, index)).toLowerCase();
    if (attributes.has(name) || !['path', 'httponly', 'samesite', 'max-age', 'expires'].includes(name)) throw new Error('Invalid upstream session cookie.');
    attributes.set(name, index < 0 ? '' : part.slice(index + 1));
  }
  if (attributes.get('path') !== '/' || attributes.get('httponly') !== '' || attributes.get('samesite')?.toLowerCase() !== 'strict'
    || (!TOKEN.test(value) && !(['', '""'].includes(value) && attributes.get('max-age') === '0'))
    || !/^\d{1,5}$/.test(attributes.get('max-age') ?? '') || Number(attributes.get('max-age')) > 86400
    || (attributes.has('expires') && !Number.isFinite(Date.parse(attributes.get('expires'))))) throw new Error('Invalid upstream session cookie.');
  return values;
}

function repeatedHeader(request) {
  const counts = new Map();
  for (let index = 0; index < request.rawHeaders.length; index += 2) {
    const name = request.rawHeaders[index].toLowerCase();
    if (['host', 'origin', 'sec-fetch-site', 'content-type', 'idempotency-key', 'x-source-name'].includes(name)) counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return [...counts.values()].some(count => count > 1);
}
const routes = new Map([
  ['/workspace-preview/', ['../../workspace-preview/index.html', 'text/html']],
  ['/workspace-preview/research-ui.mjs', ['../../workspace-preview/research-ui.mjs', 'text/javascript']],
  ['/workspace-preview/research-view.mjs', ['../../workspace-preview/research-view.mjs', 'text/javascript']],
  ['/workspace-preview/comparison.html', ['../../workspace-preview/comparison.html', 'text/html']],
  ['/research-api.mjs', ['research-api.mjs', 'text/javascript']],
  ['/workspace-preview/index.html', ['../../workspace-preview/index.html', 'text/html']],
  ['/workspace-preview/comparison.mjs', ['../../workspace-preview/comparison.mjs', 'text/javascript']],
  ['/workspace-preview/comparison-core.mjs', ['../../workspace-preview/comparison-core.mjs', 'text/javascript']],
  ['/workspace-preview/comparison-view.mjs', ['../../workspace-preview/comparison-view.mjs', 'text/javascript']],
  ['/workspace-preview/comparison.css', ['../../workspace-preview/comparison.css', 'text/css']],
  ['/workspace-preview/saved-example.html', ['../../workspace-preview/saved-example.html', 'text/html']],
  ['/workspace-preview/app.mjs', ['../../workspace-preview/app.mjs', 'text/javascript']],
  ['/workspace-preview/styles.css', ['../../workspace-preview/styles.css', 'text/css']],
  ['/workspace-preview/reference.json', ['../../workspace-preview/reference.json', 'application/json']],
  ['/workspace-preview/examples/synthetic.request.json', ['../../fixtures/model-comparison/synthetic.request.json', 'application/json']],
  ['/workspace-preview/examples/synthetic.response.json', ['../../fixtures/model-comparison/synthetic.response.json', 'application/json']],
  ['/workspace-preview/examples/request.schema.json', ['../../fixtures/model-comparison/request.schema.json', 'application/json']],
  ['/workspace-preview/examples/result.schema.json', ['../../fixtures/model-comparison/result.schema.json', 'application/json']],
  ['/comparison-api.mjs', ['comparison-api.mjs', 'text/javascript']],
  ['/examples/controlled-source.png', ['../../fixtures/intake/clean.png', 'image/png']],
  ['/', ['index.html', 'text/html']],
  ['/index.html', ['index.html', 'text/html']],
  ['/app.mjs', ['app.mjs', 'text/javascript']],
  ['/motion.mjs', ['motion.mjs', 'text/javascript']],
  ['/exact.mjs', ['exact.mjs', 'text/javascript']],
  ['/question.mjs', ['question.mjs', 'text/javascript']],
  ['/api.mjs', ['api.mjs', 'text/javascript']],
  ['/session.mjs', ['session.mjs', 'text/javascript']],
  ['/general-workspace.mjs', ['general-workspace.mjs', 'text/javascript']],
  ['/research.mjs', ['research.mjs', 'text/javascript']],
  ['/manual.mjs', ['manual.mjs', 'text/javascript']],
  ['/source-workflow.mjs', ['source-workflow.mjs', 'text/javascript']],
  ['/assistant-workflow.mjs', ['assistant-workflow.mjs', 'text/javascript']],
  ['/workflow.mjs', ['workflow.mjs', 'text/javascript']],
  ['/design.mjs', ['design.mjs', 'text/javascript']],
  ['/followup-workflow.mjs', ['followup-workflow.mjs', 'text/javascript']],
  ['/design-workflow.mjs', ['design-workflow.mjs', 'text/javascript']],
  ['/result-view.mjs', ['result-view.mjs', 'text/javascript']],
  ['/styles.css', ['styles.css', 'text/css']],
]);

if (!Number.isInteger(port) || port < 0 || port > 65535) {
  throw new Error('Choose a local port between 0 and 65535.');
}
if (!Number.isInteger(apiPort) || apiPort < 1 || apiPort > 65535) {
  throw new Error('BEAN_WEB_API_PORT must be a loopback API port between 1 and 65535.');
}

const server = createServer(async (request, response) => {
  // Fixed loopback upstream with a separate, server-controlled session boundary.
  if (request.url.startsWith('/api/bean/v1/')) {
    const expectedHost = `127.0.0.1:${server.address().port}`;
    const origin = `http://${expectedHost}`, site = request.headers['sec-fetch-site'];
    if (request.headers.host !== expectedHost ||
        (request.headers.origin && request.headers.origin !== origin) ||
        (site && !['same-origin', 'none'].includes(site)) ||
        (request.method === 'POST' && (request.headers.origin !== origin || (site && site !== 'same-origin'))) || repeatedHeader(request)) {
      response.writeHead(403, SAFE_HEADERS).end(); return;
    }
    if (!['GET', 'POST'].includes(request.method) || request.url.includes('\\')) {
      response.writeHead(405).end(); return;
    }
    // Never forward Authorization, arbitrary cookies, gateway proofs or forwarded
    // headers supplied by a visitor. Operator bearer access stays on the API.
    const headers = {};
    let cookie;
    try { cookie = browserCookie(request.headers.cookie); } catch {
      response.writeHead(401, { ...SAFE_HEADERS, 'Content-Type': 'application/json', 'Set-Cookie': CLEAR_COOKIE });
      response.end(JSON.stringify({ code: 'invalid_browser_session', message: 'This browser session is no longer available. Start a new private session to continue.' }));
      return;
    }
    for (const key of ['content-type', 'idempotency-key', 'x-source-name']) {
      const value = request.headers[key];
      if (value !== undefined) {
        if (typeof value !== 'string' || value.length > (key === 'idempotency-key' ? 128 : 255) || !/^[\x20-\x7e]+$/.test(value)
          || (key === 'x-source-name' && /[/\\]/.test(value))) {
          response.writeHead(400, SAFE_HEADERS).end(); return;
        }
        headers[key] = value;
      }
    }
    try { headers['x-bean-local-gateway'] = await gatewaySecret(); } catch {
      response.writeHead(503, { ...SAFE_HEADERS, 'Content-Type': 'application/json' });
      response.end(JSON.stringify({ code: 'local_access_unavailable', message: 'Private browser access is not ready. Restart the application and try again.' }));
      return;
    }
    headers['x-bean-local-origin'] = origin;
    if (cookie) headers.cookie = cookie;
    if (request.headers.origin) headers.origin = request.headers.origin;
    if (site) headers['sec-fetch-site'] = site;
    const upstream = upstreamRequest({ hostname: '127.0.0.1', port: apiPort,
      path: request.url, method: request.method, headers }, result => {
      const safeHeaders = { ...SAFE_HEADERS };
      try {
        const cookie = responseCookie(result.headers['set-cookie']);
        if (cookie) safeHeaders['Set-Cookie'] = cookie;
      } catch {
        result.resume();
        response.writeHead(502, { ...SAFE_HEADERS, 'Content-Type': 'application/json' });
        response.end(JSON.stringify({ code: 'local_response_invalid', message: 'The server could not confirm a private browser session.' }));
        return;
      }
      for (const key of ['content-type', 'content-disposition', 'x-artifact-sha256', 'x-request-id']) {
        if (result.headers[key]) safeHeaders[key] = result.headers[key];
      }
      response.writeHead(result.statusCode, safeHeaders);
      result.pipe(response);
    });
    const providerOperation = /^\/api\/bean\/v1\/workspaces\/[^/]+\/(intake-proposals|assistant-turns|research-analyses)$/.test(request.url);
    upstream.setTimeout(providerOperation ? 75000 : 15000, () => upstream.destroy());
    upstream.on('error', () => {
      if (!response.headersSent) response.writeHead(502, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
      response.end(JSON.stringify({ code: 'backend_unavailable', message: 'The application server is temporarily unavailable. Try connecting again shortly.' }));
    });
    request.on('aborted', () => upstream.destroy());
    request.pipe(upstream);
    return;
  }
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    response.writeHead(405, { Allow: 'GET, HEAD' }).end();
    return;
  }

  const [path] = request.url.split('?');
  if (path === '/workspace-preview/research-service.json') {
    const bytes = Buffer.from(JSON.stringify({ schema_version: 'DB-RESEARCH-CONNECTION-1', available: true, mode: 'private_session', module: '/research-api.mjs' }));
    response.writeHead(200, { ...SAFE_HEADERS, 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': bytes.length });
    response.end(request.method === 'HEAD' ? undefined : bytes); return;
  }
  if (path === '/workspace-preview/comparison-service.json') {
    // Only this application server declares the trusted transport. A standalone
    // static preview cannot acquire API authority by changing this manifest;
    // the connector still confirms the private session and backend capability.
    const bytes = Buffer.from(JSON.stringify({
      schema_version: 'DB-MODEL-COMPARISON-CONNECTION-1', available: true,
      mode: 'private_session', module: '/comparison-api.mjs',
      request_schema: 'DB-MODEL-COMPARISON-1', result_schema: 'DB-MODEL-COMPARISON-RESULT-1',
    }));
    response.writeHead(200, { ...SAFE_HEADERS, 'Content-Type': 'application/json; charset=utf-8', 'Content-Length': bytes.length });
    response.end(request.method === 'HEAD' ? undefined : bytes);
    return;
  }
  const file = routes.get(path);
  if (!file) {
    response.writeHead(404).end();
    return;
  }

  const [filename, contentType] = file;
  try {
    const bytes = await readFile(new URL(filename, import.meta.url));
    response.writeHead(200, {
      'Cache-Control': 'no-store',
      'Content-Length': bytes.length,
      'Content-Type': `${contentType}; charset=utf-8`,
      'X-Content-Type-Options': 'nosniff',
    });
    response.end(request.method === 'HEAD' ? undefined : bytes);
  } catch (error) {
    response.writeHead(error.code === 'ENOENT' ? 404 : 500).end();
  }
});

server.listen(port, host, () => {
  console.log(`Dr. Bean local preview at http://${host}:${server.address().port}`);
});
