import { access, readFile, readdir } from 'node:fs/promises'
import { constants } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const miniappRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const argument = (name) => {
  const index = process.argv.indexOf(name)
  return index >= 0 ? String(process.argv[index + 1] || '').trim() : ''
}
const apiBase = (
  argument('--api')
  || process.env.FLORIS_MINIAPP_API_BASE_URL
  || process.env.TARO_APP_API_BASE_URL
  || 'https://miniapp-floris.jlutx.com'
).replace(/\/+$/, '')
const blobUploadOrigin = (
  process.env.FLORIS_MINIAPP_BLOB_UPLOAD_ORIGIN
  || 'https://1331509262-zone-3sgh18wrmisi.blob-nocache.edgeone.site'
).replace(/\/+$/, '')

const checks = []
const check = (ok, label, detail) => {
  checks.push({ ok, label, detail })
  console.log(`${ok ? '✓' : '✗'} ${label}${detail ? `：${detail}` : ''}`)
}

async function javascriptFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const nested = await Promise.all(entries.map((entry) => {
    const path = resolve(directory, entry.name)
    if (entry.isDirectory()) return javascriptFiles(path)
    return entry.isFile() && entry.name.endsWith('.js') ? [path] : []
  }))
  return nested.flat()
}

const project = JSON.parse(await readFile(resolve(miniappRoot, 'project.config.json'), 'utf8'))
const miniprogramRoot = String(project.miniprogramRoot || '').replace(/^\.\//, '').replace(/\/+$/, '')
check(
  miniprogramRoot === 'dist',
  '微信工程输出目录',
  miniprogramRoot === 'dist' ? 'dist/' : String(project.miniprogramRoot || '未设置'),
)

let privateConfig = null
try {
  privateConfig = JSON.parse(await readFile(resolve(miniappRoot, 'project.private.config.json'), 'utf8'))
} catch {
  // The private file is intentionally ignored by Git.
}
const appId = String(privateConfig?.appid || '').trim()
const validAppId = /^wx[0-9A-Za-z]{16}$/.test(appId)
check(
  validAppId,
  '真实小程序 AppID',
  validAppId
    ? '格式有效'
    : appId
      ? '格式不正确'
      : '缺少 miniapp/project.private.config.json',
)

let built = true
let builtAppConfig = null
try {
  const appConfigPath = resolve(miniappRoot, 'dist', 'app.json')
  await access(appConfigPath, constants.R_OK)
  builtAppConfig = JSON.parse(await readFile(appConfigPath, 'utf8'))
} catch {
  built = false
}
check(built, '小程序构建产物', built ? 'dist/app.json 可读取' : '请先运行 npm run build:weapp')
let browserDecoderFree = false
if (built) {
  try {
    const files = await javascriptFiles(resolve(miniappRoot, 'dist'))
    const sources = await Promise.all(files.map((file) => readFile(file, 'utf8')))
    browserDecoderFree = sources.every((source) => (
      !source.includes('TextDecoder')
      && !source.includes('fast-text-encoding')
    ))
  } catch {
    browserDecoderFree = false
  }
}
check(
  browserDecoderFree,
  '微信真机 UTF-8 解码兼容',
  browserDecoderFree
    ? '构建产物不依赖浏览器 TextDecoder'
    : '构建产物仍包含 TextDecoder 或旧 polyfill',
)
const locationPermissionDescription = String(
  builtAppConfig?.permission?.['scope.userLocation']?.desc || '',
).trim()
const locationPermissionDescriptionLength = Array.from(locationPermissionDescription).length
check(
  locationPermissionDescriptionLength > 0 && locationPermissionDescriptionLength <= 30,
  '微信位置权限说明',
  locationPermissionDescriptionLength > 0
    ? `${locationPermissionDescriptionLength}/30 字`
    : 'dist/app.json 中缺少 scope.userLocation.desc',
)
const requiredPrivateInfos = Array.isArray(builtAppConfig?.requiredPrivateInfos)
  ? builtAppConfig.requiredPrivateInfos
  : []
check(
  requiredPrivateInfos.includes('getLocation'),
  '微信定位隐私声明',
  requiredPrivateInfos.includes('getLocation')
    ? 'requiredPrivateInfos 已声明 getLocation'
    : 'dist/app.json 中缺少 getLocation',
)
check(apiBase.startsWith('https://'), '后端使用 HTTPS', apiBase)

try {
  const response = await fetch(`${apiBase}/wechat-auth`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ code: 'floris-miniapp-preflight-invalid-code' }),
    signal: AbortSignal.timeout(12_000),
  })
  const body = await response.json().catch(() => ({}))
  const missing = response.status === 503 && body?.error === '微信登录尚未配置'
  const reachedWeChat = response.status === 401 && body?.error === '微信登录失败，请重试'
  check(
    reachedWeChat,
    'Makers 微信登录配置',
    missing
      ? '缺少 WECHAT_MINIAPP_APP_ID / WECHAT_MINIAPP_APP_SECRET / MINIAPP_SESSION_SECRET'
      : reachedWeChat
        ? '服务端已尝试调用微信 jscode2session'
        : `返回 HTTP ${response.status}`,
  )
} catch (error) {
  check(false, 'Makers 微信登录配置', String(error?.message || error))
}

console.log('\n微信公众平台合法域名：')
console.log(`- request 合法域名：${apiBase}`)
console.log(`- request 合法域名（Makers Blob 预签名 PUT）：${blobUploadOrigin}`)
console.log(`- downloadFile 合法域名：${apiBase}`)

if (checks.some((item) => !item.ok)) process.exitCode = 1
