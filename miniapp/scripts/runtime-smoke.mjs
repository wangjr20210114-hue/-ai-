import { createRequire } from 'node:module'
import { mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const automator = require('miniprogram-automator')
const MiniProgramModule = require('miniprogram-automator/out/MiniProgram.js')

// Current WeChat DevTools removed the CLI version flag used by automator.
MiniProgramModule.default.prototype.checkVersion = async function checkVersion() {}

const scriptDirectory = dirname(fileURLToPath(import.meta.url))
const projectPath = resolve(scriptDirectory, '..')
const outputPath = resolve(projectPath, '.artifacts', 'runtime-smoke')
const cliPath = '/Applications/wechatwebdevtools.app/Contents/MacOS/cli'
const delay = (milliseconds) => new Promise((resolveDelay) => setTimeout(resolveDelay, milliseconds))

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

/**
 * Taro renders a virtual tree into page.data.root. New WeChat DevTools builds
 * currently leave automator's CSS element query waiting forever, while the
 * official App.callFunction channel remains healthy. Dispatching through the
 * page's own `eh` handler exercises the same native event path as a real tap or
 * input without reaching into React component state.
 */
async function dispatch(miniProgram, className, type, detail = {}) {
  return miniProgram.evaluate((input) => {
    const page = getCurrentPages()[0]
    const visit = (node) => {
      if (!node || typeof node !== 'object') return null
      if (String(node.cl || '').split(/\s+/).includes(input.className)) return node
      for (const child of node.cn || []) {
        const found = visit(child)
        if (found) return found
      }
      return null
    }
    const node = visit(page.data.root)
    if (!node) return { ok: false, reason: 'missing', className: input.className }
    const target = {
      id: node.uid || node.sid,
      dataset: { sid: node.sid },
      offsetLeft: 0,
      offsetTop: 0,
    }
    page.eh({
      type: input.type,
      timeStamp: Date.now(),
      target,
      currentTarget: target,
      detail: input.detail,
      touches: [],
      changedTouches: [],
      mark: {},
    })
    return { ok: true, sid: node.sid }
  }, { className, type, detail })
}

async function runtimeState(miniProgram) {
  return miniProgram.evaluate(() => {
    const page = getCurrentPages()[0]
    const messages = []
    let stopVisible = false
    let sendDisabled = true

    const textOf = (node) => {
      if (!node || typeof node !== 'object') return ''
      if (node.nn === '9' && typeof node.v === 'string') return node.v
      if (String(node.cl || '').split(/\s+/).includes('markdown-message')) {
        return String(node.p1 || '')
          .replace(/<[^>]+>/g, ' ')
          .replace(/&nbsp;/g, ' ')
      }
      return (node.cn || []).map(textOf).join(' ')
    }

    const visit = (node) => {
      if (!node || typeof node !== 'object') return
      const classes = String(node.cl || '').split(/\s+/).filter(Boolean)
      if (classes.includes('stop-button')) stopVisible = true
      if (classes.includes('send-button') && !classes.includes('stop-button')) {
        sendDisabled = Boolean(node.p2)
      }
      if (classes.includes('message-row')) {
        messages.push({
          text: textOf(node).replace(/\s+/g, ' ').trim(),
          failed: classes.includes('failed-bubble')
            || JSON.stringify(node).includes('failed-bubble'),
        })
      }
      for (const child of node.cn || []) visit(child)
    }
    visit(page.data.root)
    return {
      route: page.route,
      stopVisible,
      sendDisabled,
      messages,
    }
  })
}

async function durableState(miniProgram) {
  return miniProgram.evaluate(() => new Promise((resolveState) => {
    const session = wx.getStorageSync('floris.miniapp.session.v1') || {}
    const conversationId = wx.getStorageSync('floris.miniapp.active-conversation.v1')
    wx.request({
      url: 'https://miniapp-floris.jlutx.com/messages',
      method: 'POST',
      timeout: 12_000,
      header: {
        'content-type': 'application/json',
        'x-floris-client': 'wechat-miniapp',
        Authorization: `Bearer ${session.token || ''}`,
        'makers-conversation-id': conversationId,
      },
      data: { conversation_id: conversationId },
      complete(result) {
        const data = result.data || {}
        resolveState({
          conversationId,
          statusCode: result.statusCode || 0,
          run: data.run || null,
          messages: (data.messages || []).map((message) => ({
            role: message.role,
            content: String(message.content || '').slice(0, 240),
            clarification: Boolean(message.clarification),
            actionCount: Array.isArray(message.workspaceActions)
              ? message.workspaceActions.length
              : 0,
          })),
        })
      },
    })
  }))
}

async function waitFor(miniProgram, predicate, timeout = 30_000, interval = 100) {
  const deadline = Date.now() + timeout
  let state = await runtimeState(miniProgram)
  while (Date.now() < deadline) {
    if (predicate(state)) return state
    await delay(interval)
    state = await runtimeState(miniProgram)
  }
  const durable = await durableState(miniProgram).catch(() => null)
  throw new Error(`等待运行状态超时：${JSON.stringify({ state, durable })}`)
}

async function inputAndSend(miniProgram, value) {
  const input = await dispatch(miniProgram, 'composer-input', 'input', {
    value,
    cursor: value.length,
    keyCode: 0,
  })
  assert(input.ok, '找不到聊天输入框')
  await delay(120)
  const sent = await dispatch(miniProgram, 'send-button', 'tap')
  assert(sent.ok, '找不到发送按钮')
}

await mkdir(outputPath, { recursive: true })

const miniProgram = await automator.launch({
  cliPath,
  projectPath,
})

try {
  const exceptions = []
  const consoleLogs = []
  miniProgram.on('exception', (error) => exceptions.push(error))
  miniProgram.on('console', (entry) => {
    consoleLogs.push(entry)
    if (JSON.stringify(entry).includes('Makers stop confirmation')) {
      process.stdout.write(`[runtime-console] ${JSON.stringify(entry)}\n`)
    }
  })
  await delay(5_000)

  const initial = await runtimeState(miniProgram)
  assert(initial.route === 'pages/index/index', `首页路由异常：${initial.route}`)

  const fresh = await dispatch(miniProgram, 'side-new-conversation', 'tap')
  assert(fresh.ok, '找不到新建对话按钮')
  await delay(300)

  await inputAndSend(
    miniProgram,
    '请写一段约五百字的橘猫故事，用五个自然段流式输出。',
  )
  const streaming = await waitFor(
    miniProgram,
    (state) => state.stopVisible,
    10_000,
    50,
  )
  const beforeStop = streaming.messages.at(-1)?.text || ''
  const stopped = await dispatch(miniProgram, 'stop-button', 'tap')
  assert(stopped.ok, '流式生成期间找不到停止按钮')

  const settled = await waitFor(
    miniProgram,
    (state) => !state.stopVisible,
    8_000,
    80,
  )
  await delay(1_500)
  const afterQuietWindow = await runtimeState(miniProgram)
  const afterStop = afterQuietWindow.messages.at(-1)?.text || ''
  assert(!afterQuietWindow.stopVisible, '停止后仍处于生成状态')
  assert(
    afterStop.length <= beforeStop.length + 24,
    '用户停止后回答仍在自动续写',
  )

  await inputAndSend(miniProgram, '1+1 等于几？只回答结果。')
  const completed = await waitFor(
    miniProgram,
    (state) => (
      !state.stopVisible
      && state.messages.at(-2)?.text.includes('1+1')
      && /\b2\b/.test(state.messages.at(-1)?.text || '')
    ),
    45_000,
    120,
  )
  assert(!completed.messages.at(-1)?.failed, '停止后的下一轮回答失败')
  assert(
    completed.messages.at(-2)?.text.includes('1+1'),
    '停止后的下一轮用户消息没有进入会话',
  )

  await miniProgram.reLaunch('/pages/index/index')
  const restored = await waitFor(
    miniProgram,
    (state) => (
      !state.stopVisible
      && state.messages.some((message) => message.text.includes('1+1'))
      && /\b2\b/.test(state.messages.at(-1)?.text || '')
    ),
    25_000,
    150,
  )
  assert(
    restored.messages.filter((message) => message.text.includes('1+1')).length === 1,
    '重新进入后出现重复用户消息',
  )

  const nextConversation = await dispatch(miniProgram, 'side-new-conversation', 'tap')
  assert(nextConversation.ok, '恢复测试前无法新建对话')
  await delay(300)
  const recoveryPrompt = '请写一个四段的橘猫旅行故事，每段至少八十字。'
  await inputAndSend(miniProgram, recoveryPrompt)
  await waitFor(miniProgram, (state) => state.stopVisible, 10_000, 50)

  // Re-entering the mini program closes only the native subscriber. Makers'
  // detached producer must continue the same run and /messages must restore it
  // without creating another model request.
  await miniProgram.reLaunch('/pages/index/index')
  const recovered = await waitFor(
    miniProgram,
    (state) => (
      !state.stopVisible
      && (state.messages.at(-1)?.text || '').length > 180
    ),
    120_000,
    250,
  )
  assert(!recovered.messages.at(-1)?.failed, '刷新后的同一轮回答恢复为失败')
  assert(
    recovered.messages.filter((message) => message.text.includes(recoveryPrompt)).length === 1,
    '刷新恢复创建了重复用户消息',
  )
  assert(exceptions.length === 0, `微信运行时异常：${JSON.stringify(exceptions)}`)

  const screenshotPath = resolve(outputPath, 'chat-stop-and-resume.png')
  await miniProgram.screenshot({ path: screenshotPath })
  const recoveryScreenshotPath = resolve(outputPath, 'chat-reload-recovery.png')
  await miniProgram.screenshot({ path: recoveryScreenshotPath })
  process.stdout.write(`${JSON.stringify({
    ok: true,
    stoppedAnswerLength: afterStop.length,
    resumedAnswer: completed.messages.at(-1)?.text,
    recoveredAnswerLength: recovered.messages.at(-1)?.text.length,
    screenshot: screenshotPath,
    recoveryScreenshot: recoveryScreenshotPath,
  }, null, 2)}\n`)
} finally {
  miniProgram.disconnect()
}
