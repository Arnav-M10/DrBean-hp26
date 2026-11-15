import { cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const PUBLIC_ORIGIN = 'https://drbean.study'

export function validateEnvironment(env) {
  const upstream = env.DRBEAN_UPSTREAM_ORIGIN
  if (typeof upstream !== 'string' || !/^https:\/\/[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com$/.test(upstream)) {
    throw new Error('Set DRBEAN_UPSTREAM_ORIGIN to the exact active HTTPS Quick Tunnel origin, without a path or trailing slash.')
  }
  if (!/^[A-Za-z0-9_-]{43}$/.test(env.DRBEAN_PROXY_SECRET ?? '')) {
    throw new Error('Set DRBEAN_PROXY_SECRET to the private gateway proxy credential before deploying.')
  }
  if (env.DRBEAN_PUBLIC_ORIGIN && env.DRBEAN_PUBLIC_ORIGIN !== PUBLIC_ORIGIN) {
    throw new Error('This deployment is configured for https://drbean.study. Update the gateway and routing together to change the public origin.')
  }
}

export async function build({ directory = new URL('./', import.meta.url), env = process.env } = {}) {
  validateEnvironment(env)
  const base = typeof directory === 'string' ? directory : fileURLToPath(directory)
  let html = await readFile(resolve(base, 'site/index.html'), 'utf8')
  if ((html.match(/href="app" data-start/g) || []).length !== 3) {
    throw new Error('Landing-page Start links changed; review the build before deploying.')
  }
  // Absolute canonical links keep requests on drbean.study even when someone
  // initially visits a Vercel deployment alias. They are same-origin on the domain.
  html = html.replaceAll('href="app" data-start', `href="${PUBLIC_ORIGIN}/study/app" data-start`)
  html = html.replace(/<script>[\s\S]*?<\/script>/, '')
  html = html.replaceAll(
    'Bring files and a question. Dr. Bean checks the claim with exact math and finds the one reading that would settle it.',
    'Bring files and a question. For supported models, Dr. Bean checks the claim with exact math and compares possible next measurements.'
  )
  const output = resolve(base, 'public')
  await rm(output, { recursive: true, force: true })
  await mkdir(output, { recursive: true })
  await cp(resolve(base, 'site'), output, { recursive: true })
  await writeFile(resolve(output, 'index.html'), html)
  // Neither the upstream address nor the proxy credential is serialized into assets.
  console.log('Built Dr. Bean landing page with canonical study links.')
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await build()
