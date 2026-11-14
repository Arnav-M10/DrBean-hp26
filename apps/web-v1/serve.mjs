import { readFile } from 'node:fs/promises';
import { createServer, request as upstreamRequest } from 'node:http';

const host = '127.0.0.1';
const port = Number(process.argv[2] ?? 4173);
const apiPort = Number(process.env.BEAN_WEB_API_PORT ?? 8000);
// Front end v1 (lab-notebook theme). Presentation files come from this folder; every
// behaviour module is served unchanged from apps/web, so both front ends share one logic.
const types = { '.html': 'text/html', '.mjs': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml' }
const routes = new Map([
  ['/examples/controlled-source.png', ['../../fixtures/intake/clean.png', 'image/png']],
  ...[['/', 'index.html'], ['/index.html', 'index.html'], ...['styles.css', 'motion.mjs', 'story.mjs', 'figure.mjs'].map(f => [`/${f}`, f])]
    .map(([path, file]) => [path, [file, types[file.slice(file.lastIndexOf('.'))]]]),
  ...['app.mjs', 'exact.mjs', 'question.mjs', 'api.mjs', 'session.mjs', 'general-workspace.mjs', 'research.mjs', 'manual.mjs',
      'source-workflow.mjs', 'assistant-workflow.mjs', 'workflow.mjs', 'design.mjs', 'followup-workflow.mjs', 'design-workflow.mjs']
    .map(f => [`/${f}`, [`../web/${f}`, 'text/javascript']]),
]);

if (!Number.isInteger(port) || port < 0 || port > 65535) {
  throw new Error('Choose a local port between 0 and 65535.');
}
if (!Number.isInteger(apiPort) || apiPort < 1 || apiPort > 65535) {
  throw new Error('BEAN_WEB_API_PORT must be a loopback API port between 1 and 65535.');
}

const server = createServer(async (request, response) => {
  // Fixed loopback upstream. Never proxy cookies, redirects, or arbitrary destinations.
  if (request.url.startsWith('/api/bean/v1/')) {
    const expectedHost = `127.0.0.1:${server.address().port}`;
    if (request.headers.host !== expectedHost ||
        (request.headers.origin && request.headers.origin !== `http://${expectedHost}`) ||
        request.headers['sec-fetch-site'] === 'cross-site') {
      response.writeHead(403).end(); return;
    }
    if (!['GET', 'POST'].includes(request.method) || request.url.includes('\\')) {
      response.writeHead(405).end(); return;
    }
    // Browser sessions belong to the HTTPS gateway, which reaches the API
    // directly. This local bearer-only transport has no trusted session hop.
    if (request.method === 'GET' && request.url.split('?')[0] === '/api/bean/v1/shared-session') {
      response.writeHead(404, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
      response.end(JSON.stringify({ code: 'shared_access_unavailable', message: 'Private browser sessions are available through the shared HTTPS link.' }));
      return;
    }
    const headers = {};
    const sourceName = request.headers['x-source-name'];
    if (sourceName !== undefined && (typeof sourceName !== 'string' || sourceName.length > 255 || !/^[\x20-\x7e]+$/.test(sourceName) || /[/\\]/.test(sourceName))) {
      response.writeHead(400).end(); return;
    }
    for (const key of ['authorization', 'content-type', 'idempotency-key', 'x-source-name']) {
      if (request.headers[key]) headers[key] = request.headers[key];
    }
    const upstream = upstreamRequest({ hostname: '127.0.0.1', port: apiPort,
      path: request.url, method: request.method, headers }, result => {
      const safeHeaders = { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' };
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
      response.end(JSON.stringify({ code: 'backend_unavailable', message: `Start the local API on 127.0.0.1:${apiPort}.` }));
    });
    request.pipe(upstream);
    return;
  }
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    response.writeHead(405, { Allow: 'GET, HEAD' }).end();
    return;
  }

  const [path] = request.url.split('?');
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
  console.log(`Dr. Bean front end v1 at http://${host}:${server.address().port}`);
});
