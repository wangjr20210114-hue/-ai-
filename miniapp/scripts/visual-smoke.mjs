import { createRequire } from 'node:module'
import { mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const automator = require('miniprogram-automator')
// Newer devtools CLIs no longer support `-v`; skip the automator's version
// probe so it can launch against them.
const MiniProgramModule = require('miniprogram-automator/out/MiniProgram.js')
MiniProgramModule.default.prototype.checkVersion = async function checkVersion() {}
const scriptDirectory = dirname(fileURLToPath(import.meta.url))
const projectPath = resolve(scriptDirectory, '..')
const outputPath = resolve(projectPath, '.artifacts', 'visual-smoke')
const cliPath = '/Applications/wechatwebdevtools.app/Contents/MacOS/cli'

const routes = [
  ['chat', '/pages/index/index', 'tab'],
  ['calendar', '/pages/calendar/index', 'tab'],
  ['library', '/pages/library/index', 'tab'],
  ['proactive', '/pages/proactive/index', 'tab'],
  ['settings', '/pages/settings/index', 'tab'],
  ['reader', '/pages/reader/index', 'page'],
]
const requestedRoutes = new Set(process.argv.slice(2))
const selectedRoutes = requestedRoutes.size
  ? routes.filter(([name]) => requestedRoutes.has(name))
  : routes

await mkdir(outputPath, { recursive: true })

const miniProgram = await automator.launch({
  cliPath,
  projectPath,
})

try {
  miniProgram.on('exception', (error) => {
    process.stderr.write(`[miniapp exception] ${JSON.stringify(error)}\n`)
  })

  // Newer developer tools create the simulator webview asynchronously.
  // Let the initial route settle before asking the automator for page metadata.
  await new Promise((resolveDelay) => setTimeout(resolveDelay, 5000))

  for (const [name, route, routeType] of selectedRoutes) {
    if (routeType === 'tab') {
      await miniProgram.switchTab(route)
    } else {
      await miniProgram.reLaunch(route)
    }
    const page = await miniProgram.currentPage()
    await page.waitFor(1600)
    const screenshotPath = resolve(outputPath, `${name}.png`)
    await miniProgram.screenshot({ path: screenshotPath })
    process.stdout.write(`${name}: ${screenshotPath}\n`)
  }
} finally {
  await miniProgram.close()
}
