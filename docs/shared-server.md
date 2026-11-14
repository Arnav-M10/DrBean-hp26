# Shared Dr. Bean development server

The owner runs one API, worker and web process on one Mac. One private `var/gemini.local.json` supplies the owner's Gemini key to the API and worker. Every authorized workspace uses that configuration and the same durable budget. Teammates use a browser and a Dr. Bean access token; they do not receive the Gemini key or need a local installation.

## Owner setup

1. Prepare and start the app using the root README. The optional Gemini configuration stays only on this machine, with permissions `0600`. Confirm the local app works before sharing.
2. Install Cloudflare's official tunnel client. On macOS, `brew install cloudflared` installs it through Homebrew.
3. Run `python3 scripts/dev/share.py start`. It starts a separate loopback gateway on port 4174 and a temporary HTTPS Quick Tunnel. The application on ports 4173 and 8000 keeps running unchanged. The script prints the generated URL. On macOS it also prevents idle sleep while its tunnel process is alive; closing the lid may still suspend the host.
4. Give the URL and a researcher access token to trusted teammates privately. The token is stored locally in `var/auth.json`; it is an app access token, not the Gemini key. The existing prototype researcher token shares an identity and its workspaces among its holders. It is suitable for a trusted team prototype, not separate customer accounts.
5. `python3 scripts/dev/share.py status` retrieves the current URL. `python3 scripts/dev/share.py stop` stops only this script's recorded tunnel/gateway/awake processes and removes the accepted public origin. It leaves the API, worker, store and local app intact.

Stop sharing before stopping the main app. A new sharing session gets a new URL; stop an incomplete/stale sharing session before starting another. The URL works only while the Mac, app and tunnel remain available. This is temporary development hosting, not a production deployment or uptime guarantee.

## Teammate use

1. Open the shared HTTPS URL supplied by the owner.
2. Expand **Server connection** and paste the researcher access token, then click **Connect**.
3. Choose or create a workspace. The server already has the owner's Gemini configuration. Follow the same source review, plan approval and evidence workflow as on the local app.
4. Review each separate consent disclosure before sending an image or question to Gemini. A connection or upload alone makes no model call. Workspaces using one shared identity are visible to everyone with that token.

**Show Gemini call budget** displays application reservations without making a model call. The shared store retains earlier tests and failed/uncertain reservations. Eight requests, 64,000 conservatively reserved input tokens and 16,000 output tokens are the current trial ceilings across that store. A remaining request count alone does not mean sufficient input capacity remains. Budget exhaustion is refused before dispatch; the sharing script neither wipes history nor raises limits. The free-tier flag records the owner's account assertion, not an independent billing check or a Google quota reading.

## Boundary and verification

- API, local web and gateway listen on `127.0.0.1`; only the configured tunnel reaches the gateway.
- Before forwarding, the gateway requires the exact recorded `https://…trycloudflare.com` host, HTTPS forwarding metadata and a matching browser Origin when supplied. Cross-site browser requests and invalid/unavailable origin configuration are refused. No wildcard origin or request-selected upstream is admitted.
- Approved requests go only to the fixed local web port. The existing API proxy and backend still require researcher bearer authentication and workspace authorization. Cookies and arbitrary forwarded headers are not passed through.
- The gateway and tunnel receive the launcher's sanitized environment. They never read the Gemini configuration, auth file or database. Credentials are never placed in URLs or sharing logs. Keys and `var/` files remain excluded from Git.
- Sharing checks use ordinary HTTP reads; no provider request is needed. `node --test` in `apps/web` verifies approved-origin forwarding, rejection of wrong origins/hosts/plain HTTP metadata, missing-config refusal, bearer preservation, cookie stripping and continued authentication refusal.

Local integration checks also exercised this gateway against the running API: an authenticated workspace read succeeded, an unauthenticated read returned 401, and a foreign Origin returned 403. These checks started no public tunnel or model request. Public HTTPS connectivity must be verified after the owner approves activating the external tunnel; local checks alone do not establish that qualification.

Cloudflare documents temporary URLs, client installation prerequisites and preview limitations in its [Quick Tunnels guide](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/). A Quick Tunnel is reachable by anyone with its URL; the app's access token remains required for research data and operations. Share the token only with the intended researchers.
