// Optional post-assertion screenshots for the existing real-science runners.
// Never imported by the application; no pixel-golden or scientific assertion.
import { mkdir } from 'node:fs/promises'
import { resolve, join } from 'node:path'

export async function captureDesign(page, name) {
  if (!process.env.BEAN_DESIGN_CAPTURE_DIR) return
  const directory = resolve(process.env.BEAN_DESIGN_CAPTURE_DIR)
  await mkdir(directory, { recursive: true })
  await page.screenshot({ path: join(directory, `${name}.png`), fullPage: true })
}
