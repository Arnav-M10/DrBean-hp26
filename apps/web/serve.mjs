import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';

const host = '127.0.0.1';
const port = Number(process.argv[2] ?? 4173);
const routes = new Map([
  ['/', ['index.html', 'text/html']],
  ['/index.html', ['index.html', 'text/html']],
  ['/app.mjs', ['app.mjs', 'text/javascript']],
  ['/exact.mjs', ['exact.mjs', 'text/javascript']],
  ['/question.mjs', ['question.mjs', 'text/javascript']],
  ['/styles.css', ['styles.css', 'text/css']],
]);

if (!Number.isInteger(port) || port < 0 || port > 65535) {
  throw new Error('Choose a local port between 0 and 65535.');
}

const server = createServer(async (request, response) => {
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
  console.log(`Dr. Bean local preview at http://${host}:${server.address().port}`);
});
