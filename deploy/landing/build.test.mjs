import { test } from 'node:test'
import assert from 'node:assert/strict'
import { cp, mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { build, validateEnvironment } from './build.mjs'

const env = { DRBEAN_UPSTREAM_ORIGIN: 'https://bean-hosting-test.trycloudflare.com', DRBEAN_PROXY_SECRET: 'p'.repeat(43) }
const config = JSON.parse(await readFile(new URL('./vercel.json', import.meta.url), 'utf8'))

test('deployment refuses absent, malformed or untrusted configuration', () => {
  validateEnvironment(env)
  for (const upstream of ['', 'http://bean.trycloudflare.com', 'https://bean.trycloudflare.com/',
    'https://bean.trycloudflare.com/study', 'https://bean.trycloudflare.com.evil.test',
    'https://localhost', 'https://user:secret@bean.trycloudflare.com']) {
    assert.throws(() => validateEnvironment({ ...env, DRBEAN_UPSTREAM_ORIGIN: upstream }))
  }
  for (const secret of ['', undefined, 'short', 'x'.repeat(44), ' '.repeat(43)]) {
    assert.throws(() => validateEnvironment({ ...env, DRBEAN_PROXY_SECRET: secret }))
  }
  assert.throws(() => validateEnvironment({ ...env, DRBEAN_PUBLIC_ORIGIN: 'https://evil.test' }))
})

test('only the application paths are proxied and request secrets cannot be supplied by the visitor', () => {
  const route = config.routes[0], pattern = new RegExp(`^${route.src}`)
  for (const path of ['/study', '/study/', '/study/app', '/study/app.mjs', '/study/vendor/katex/katex.min.js',
    '/api/bean/v1/shared-session/current', '/api/bean/v1/workspaces/ws/research-assets',
    '/session.mjs', '/api.mjs', '/exact.mjs', '/general-workspace.mjs', '/comparison-api.mjs']) {
    const match = pattern.exec(path)
    assert(match, path)
    assert.equal('/' + match[1], path)
  }
  for (const path of ['/', '/index.html', '/home.mjs', '/styles.css', '/results.mjs', '/fonts/test.woff2',
    '/.env', '/study-old', '/api/admin', '/api/bean/v11/workspaces', '/api.mjs/anything']) assert(!pattern.test(path), path)
  assert.equal(route.dest, '${DRBEAN_UPSTREAM_ORIGIN}/$1')
  assert.deepEqual(route.env, ['DRBEAN_UPSTREAM_ORIGIN'])
  assert.equal(route.headers['Cache-Control'], 'no-store')
  assert.equal(route.headers['Vercel-CDN-Cache-Control'], 'no-store')
  assert.deepEqual(route.transforms, [{ type: 'request.headers', op: 'set', target: { key: 'x-bean-vercel-proxy' }, args: '$DRBEAN_PROXY_SECRET', env: ['DRBEAN_PROXY_SECRET'] }])
  assert.equal(config.functions, undefined)
})

test('landing points at the canonical app and public output contains neither secret nor tunnel address', async t => {
  const directory = await mkdtemp(join(tmpdir(), 'bean-landing-build-'))
  t.after(() => rm(directory, { recursive: true, force: true }))
  await cp(new URL('./site/', import.meta.url), join(directory, 'site'), { recursive: true })
  await writeFile(join(directory, '.env.local'), 'PRIVATE_DO_NOT_COPY=yes')
  await build({ directory, env })
  const html = await readFile(join(directory, 'public/index.html'), 'utf8')
  assert.equal((html.match(/href="https:\/\/drbean\.study\/study\/app" data-start/g) || []).length, 3)
  assert(!html.includes("location.replace('app'"))
  assert(html.includes('For supported models'))
  assert(html.includes('synthetic, from a saved run'))
  const files = await readdir(join(directory, 'public'), { recursive: true, withFileTypes: true })
  for (const file of files.filter(file => file.isFile())) {
    const bytes = await readFile(join(file.parentPath, file.name))
    assert(!bytes.includes(Buffer.from(env.DRBEAN_PROXY_SECRET)))
    assert(!bytes.includes(Buffer.from(env.DRBEAN_UPSTREAM_ORIGIN)))
    assert(!bytes.includes(Buffer.from('PRIVATE_DO_NOT_COPY')))
  }
})
