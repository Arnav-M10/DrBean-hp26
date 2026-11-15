# Dr. Bean custom-domain deployment

This project serves the public landing page on Vercel and proxies the existing research app through the same domain. **Start a study stays at `https://drbean.study/study/app`.** The Python API, scientific worker, database and Gemini configuration remain on the Mac. No provider credential is uploaded to Vercel.

## Vercel project settings

Connect the existing `dr-bean` project to `Arnav-M10/DrBean-hp26`:

| Setting | Value |
| --- | --- |
| Production branch | `main` |
| Root directory | `deploy/landing` |
| Framework preset | Other |
| Build command | `node build.mjs` |
| Output directory | `public` |

Configure these **Production** environment variables before deploying:

- `DRBEAN_UPSTREAM_ORIGIN`: the exact active `https://….trycloudflare.com` origin, without a trailing slash or path.
- `DRBEAN_PROXY_SECRET`: the separate 43-character random proxy credential from the gateway's owner-only `vercel-proxy.json`. This is not a Gemini key, API owner token or existing gateway credential. Store it as sensitive on Vercel.
- `DRBEAN_PUBLIC_ORIGIN` is optional and, when set, must be `https://drbean.study`.

These are project environment variables, not committed JSON values. Route `env` expansion injects the upstream at request time and a request-header transform replaces any visitor-supplied proxy header with the private project value. No environment value is written into browser assets. The build checks configuration without printing it.

The sharing gateway must have the custom-domain support and matching private proxy configuration installed first. Its independent hop secret, exact public origin, canonical tunnel identity, browser Origin and fetch-metadata checks remain active. Authenticated cookies are Secure, HttpOnly, host-only and SameSite Strict.

## Routing

The landing assets are static. Only `/study`, `/study/*`, `/api/bean/v1/*` and the five explicitly listed root application modules are proxied. No serverless function receives uploaded bodies. Private responses remain `no-store`; the worker still runs asynchronously behind the existing API.

The landing button uses the canonical public hostname. A visitor who opens a Vercel deployment alias therefore enters the app at `drbean.study` too. Arbitrary preview hostnames are not authorized app origins.

The landing illustration is a saved synthetic example and remains labelled accordingly. `ASSET_SOURCE.json` records the curated source snapshot. Update `site/` when changing this landing page; Git pushes affecting unrelated `apps/web` source do not automatically regenerate this snapshot. Live `/study/*` files are served from the running backend's web checkout, not copied into the Vercel bundle.

## Operational limits

- Keep the Mac, its network, API, web process, worker and sharing tunnel running.
- Restarting a Quick Tunnel can change its hostname. Update `DRBEAN_UPSTREAM_ORIGIN` in the Vercel project and redeploy. The custom browser address remains the same.
- Existing sessions on the temporary Cloudflare hostname do not transfer automatically to `drbean.study`; those server records remain preserved. Keep exports from old sessions when needed.
- Deployment and ordinary page/session checks make no model calls. Explicit analysis actions retain the application's consent and budget requirements.
- Do not copy `.vercel`, `.env*`, databases, local research uploads or machine-specific launcher scripts into Git.

## Verification

Run `node --test build.test.mjs` for build, routing and public-output checks. After deployment, verify from a fresh browser profile that the URL stays on `drbean.study`, session creation and reload work, an uploaded public/synthetic file is retained, private files cannot be read from another profile, and evidence downloads retain their hashes. Live model execution is a separate test.

Official references: [Vercel external rewrites and secret headers](https://vercel.com/docs/routing/rewrites), [route environment-variable expansion](https://vercel.com/docs/project-configuration/vercel-json#using-environment-variables-in-routes).
