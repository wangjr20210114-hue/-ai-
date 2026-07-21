import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const target = path.join(root, 'frontend/public/test-cases/cases.json');
const cases = JSON.parse(fs.readFileSync(target, 'utf8'));

const faultCases = new Set(['CORE-08', 'SEARCH-03', 'PRO-05', 'PRO-08', 'SEC-02', 'AUTH-02', 'AUTH-03', 'CONNECT-01', 'MEET-02', 'MIG-01']);
const readOnlyCases = new Set(['CORE-01', 'CORE-04', 'CORE-06', 'SEARCH-02', 'OPS-01', 'OPS-02', 'OPS-03', 'LIMIT-01', 'LIMIT-02', 'LIMIT-03', 'LIMIT-04']);

const specialSteps = {
  'CORE-04': [
    '【目标网页】点击左栏“＋ 新建对话”，确认输入区上方“联网搜索”已开启；输入“最近 AI 有什么新进展”并只发送一次。',
    '【目标网页】等待“正在搜索/正在思考”结束并出现完整回答；打开回答中的至少 2 个来源，核对标题、发布日期与回答陈述一致。',
    '【浏览器 Network】按开始时间筛选 messages；点开对应 POST /messages，请求状态应为 200，Response/Preview 中不应出现 role、KeyError 或 Traceback。',
    '【Makers 控制台】打开当前 Deployment → Agents → messages → 日志，时间范围设为“发送前 2 分钟至回答后 2 分钟”；搜索框依次查“role”“/messages”和请求 ID。',
    '【Makers 控制台】确认该请求有开始和正常结束日志，且 role 搜索无错误；若只有业务正文包含 role 字样，不算故障。',
    '【目标网页】刷新页面，重新打开该会话；核对用户问题、AI 回答、来源卡片均完整且没有重复。',
  ],
  'CORE-08': [
    '【安全确认】只使用 Preview，并新建标题含 TEST-ERROR 的测试会话；不要修改 Production 的模型、Provider、Key 或环境变量。',
    '【目标网页】先发送“TEST-准备屏蔽，只回答：准备完成”并等回答成功；在 Network 筛选“/chat”，找到 Method 为 POST、Status 为 200 的真实请求。',
    '【Network】右键这条 POST /chat → Block request/屏蔽请求；不要点 Add condition，也不要手填旧版路径通配符。',
    '【Request conditions/请求条件】确认底部抽屉自动打开、按真实请求生成 URL Pattern，且 Enable blocking and throttling/启用屏蔽和限速已自动勾选。',
    '【目标网页】发送“测试错误恢复，请只回答成功”；在 Network 确认 POST /chat 变红且 Status 为“(blocked:devtools)”，同时页面停止“正在思考”并显示中文失败提示。',
    '【Request conditions/请求条件】点击刚生成规则右侧的删除按钮，再取消 Enable blocking and throttling；必须删除规则，因为关闭 DevTools 后规则仍会保存。',
    '【目标网页】在同一会话重新发送“测试错误恢复，请只回答成功”；等待成功回答，然后刷新页面。',
    '【目标网页】核对失败记录不会变成空白 AI 气泡或伪装为成功；成功问题与回答只出现一次，界面不暴露 Provider 原始堆栈、role、KeyError。',
  ],
  'SEARCH-03': [
    '【正常分支】在普通 Preview 新建 TEST-SEARCH 会话，发送“比较 DeepSeek 和混元最新公开能力”；逐个打开来源，记录失效链接但不要在生产修改 Provider。',
    '【安全说明】rich_search 是 POST /chat 内部的服务端工具调用，Network 中没有可单独屏蔽的 /rich_search；不要使用 Request conditions 屏蔽 /chat 来冒充“仅搜索失败”。',
    '【安全降级分支】在 Makers 控制台新建“专用故障注入 Preview”，确认页面明确显示 Preview；不要编辑现有 Production Deployment。',
    '【Makers 控制台】仅在该专用 Preview 的环境变量中，把 WSA_API_KEY 临时设为字面值 invalid-for-acceptance，保存后重新部署 Preview；不要查看、复制或记录真实密钥值。',
    '【专用故障 Preview 网页】新建会话并发送同一问题；观察搜索失败时是否返回边界说明或无来源回答，而不是白屏、无限思考或伪造来源。',
    '【Makers 控制台】测试结束立即删除临时无效值，并从正常配置重新创建 Preview；打开 /system 确认 search Provider 状态恢复。',
    '【验收站】正常分支和降级分支分别上传截图；若无法创建隔离 Preview，把降级分支标为“阻塞”，不要在 Production 操作。',
  ],
  'PRO-05': [
    '【目标 Preview 网页】创建标题 TEST-WEATHER 的未来日程，从候选列表选择带 place_id 的地点；打开主动服务并手动触发一次检查。',
    '【运行记录】打开最新 Run，核对 Observation 中的地点、时间和天气事实；无风险天气时允许不产生通知，但不得编造风险。',
    '【安全失败分支】只在本地运行或专用故障 Preview 把 TENCENT_MAP_SERVER_KEY 临时设为 invalid-for-acceptance，再触发一次 TEST-WEATHER 检查。',
    '【运行记录】确认失败分支只记录 Provider 诊断，Run 可结束且不会生成虚构天气通知。',
    '【恢复】立即恢复专用 Preview 配置并重新部署；打开 /system 确认 map Provider 恢复。无法隔离配置时跳过失败注入并标“阻塞”，绝不改 Production。',
  ],
  'PRO-07': [
    '【Makers 控制台】进入目标项目 → 当前 Deployment → Schedules，确认存在 proactive-daily-scan，Cron 为 0 8 * * *，时区 Asia/Shanghai。',
    '【目标网页】07:50 前打开 /system，记录 scheduler.last_tick、Deployment ID 和当前北京时间；准备一条带 TEST-CRON 前缀的可扫描日程。',
    '【浏览器】关闭目标应用的所有标签页；测试站可保持打开，因为它不会调用 /api/proactive-tick。',
    '【Makers 控制台】08:05 后进入日志分析，把时间范围设为 07:55—08:05，先筛选 /api/proactive-tick、来源 Cloud Functions，再筛选 /proactive、来源 Agents 和 2xx/5xx 状态。',
    '【目标网页】重新打开 /system 和主动运行记录；确认 last_tick 推进、出现平台触发的 Run，且同一 dedup_key 没有重复通知。',
    '【验收站】上传 Schedule 配置、函数日志和 Run 三张截图；当天无法等待 08:00 时标“阻塞”，不要临时把生产 Cron 改成高频。',
  ],
  'SEC-02': [
    '【安全说明】不要通过断网、杀进程或修改生产 Provider 来制造真实副作用的“结果未知”；该分支使用仓库内置 Mock 自动化验证。',
    '【本地终端】进入仓库根目录，运行：python -m unittest agents._tests.test_workspace.WorkspaceUnitTests.test_provider_unknown_result_requires_manual_reconciliation。',
    '【本地终端】确认输出 Ran 1 test 且 OK；该测试使用内存 FakeStore，不调用腾讯会议、生图、地图或任何真实 Provider。',
    '【本地终端】再运行：python -m unittest agents._tests.test_workspace.WorkspaceUnitTests.test_expired_execution_requires_reconciliation_and_never_retries。',
    '【验收站】上传终端结果截图；只有两条测试均通过，才能将本用例记为通过。没有本地仓库/终端时标“阻塞”，禁止拿 Production 试错。',
  ],
  'OPS-02': [
    '【Makers 控制台】进入项目 → 部署管理 → 目标 Preview → 构建日志；搜索 error、failed、route，确认构建成功且无路由生成失败。',
    '【Makers 控制台】分别打开 Cloud Functions、Agents、Schedules 页签，按列表逐项计数并截图；数量以当前基线文档为准，不只看首页 200。',
    '【目标网页/浏览器 Network】依次访问 /auth/user、/system，并从应用触发 /messages；检查 Content-Type，动态路由应返回 JSON 或 SSE，而不是 text/html 的 index.html。',
    '【仓库只读检查】在代码搜索 Uvicorn、FastAPI、WebSocket；确认它们只存在 legacy/backend 或说明文档，不参与 edgeone.json 的生产构建入口。',
    '【验收站】记录实际函数/Agent/Schedule 数量和任一差异；数量不符或动态路由返回 HTML 时标失败并阻断生产。',
  ],
};

function genericPrelude(test) {
  return [
    `【Makers 控制台】进入项目 ai-active-agent → 部署管理，定位本轮 ${test.releaseBlocker ? '阻断验收' : '功能验收'}使用的 Deployment；确认环境标签为 Preview，并复制 Deployment ID。`,
    '【验收站】顶部“测试环境”选择 Preview，填写刚复制的 Deployment ID、测试人和当前主机名称；等待同步状态显示“已同步”。',
    '【目标网页】从该 Deployment 点击“预览”并在新标签打开；确认地址属于目标部署，不要用 Production 地址执行写入、故障注入或付费测试。',
    '【浏览器工具】按 F12（macOS 可按 ⌥⌘I）打开开发者工具；Network 勾选 Preserve log/保留日志，清空 Network 与 Console 后开始本用例。',
  ];
}

function genericFinish(test) {
  return [
    `【验收站】回到 ${test.id}，按实际结果选择“通过/失败/阻塞/不适用”；备注写明实际现象、关键请求状态和复现条件，不要填写密钥。`,
    '【验收站】在“证据”上传页面截图、Network/Console 截图或短录屏；等待提示已保存到 Makers Blob，再刷新测试站确认附件仍可打开。',
  ];
}

function cleanupFor(test) {
  const cleanup = ['如果本用例使用过 Request conditions/请求条件，删除创建的规则并关闭 Enable blocking and throttling；如果调整过 Network throttling，则恢复为 No throttling/不限速，确认浏览器网络正常。'];
  if (test.module === '日程' || test.module === '地点与旅行' || test.module === '主动服务') cleanup.push('删除标题含 TEST- 的日程、通知或临时工作流；保留运行记录用于审计。');
  if (test.module === '阅读与论文') cleanup.push('从阅读库移除本用例上传的非敏感测试 PDF；不要删除其他文件。');
  if (test.module === '记忆与学习') cleanup.push('删除本用例创建的 TEST- 记忆/规则，并把预算、免打扰和策略恢复为测试前值。');
  if (test.module === '身份与隔离') cleanup.push('退出测试账号并关闭无痕窗口；只删除带 TEST- 前缀的测试用户数据。');
  if (test.module === 'AI 生图') cleanup.push('保留生成 Action 作为证据；如有删除入口，仅删除本轮 TEST- 图片版本。');
  cleanup.push('刷新目标网页做一次冒烟检查：应用仍可连接、新建普通会话可用；异常时立即标记失败。');
  return cleanup;
}

for (const test of cases) {
  if (test.detailVersion >= 2) continue;
  const originalSteps = specialSteps[test.id] || test.steps.map(step => `【目标网页】${step.replace(/[。；]$/, '')}。`);
  test.detailVersion = 2;
  test.safety = faultCases.has(test.id) ? {
    environment: '仅本地或专用 Preview；Production 禁止故障注入、无效 Key、断网副作用和破坏性操作。',
    impact: '使用 TEST- 前缀会话/日程/账号和临时 Preview 配置；不读取、不复制、不在备注中记录真实密钥。',
    rollback: '先恢复临时配置并重新部署 Preview，再通过 /system 和一轮普通对话确认服务恢复；无法隔离时标“阻塞”。',
  } : readOnlyCases.has(test.id) ? {
    environment: '优先 Preview；Production 仅允许只读查看，不修改配置或数据。',
    impact: '只读取部署、日志和页面状态；日志截图需遮挡 Token、Cookie、密钥和个人信息。',
    rollback: '关闭日志筛选和测试标签，不需要修改业务配置。',
  } : {
    environment: '在目标 Preview 执行；Production 只做已证明无副作用的只读回归。',
    impact: '所有新建数据使用 TEST- 前缀，只操作本轮创建的数据；不得修改真实用户记录。',
    rollback: '按“测试后清理”删除 TEST- 数据，恢复临时开关，并完成一次普通对话冒烟检查。',
  };
  test.preconditions = [
    '已在 Makers 控制台确认目标 Deployment 为 Preview，并记录 Deployment ID。',
    '测试站显示“已同步”，当前主机名称和测试人已填写。',
    ...test.preconditions,
  ];
  test.steps = [...genericPrelude(test), ...originalSteps, ...genericFinish(test)];
  test.expected = [
    ...test.expected,
    '除用例明确要求的受控失败外，相关请求无意外 4xx/5xx，Console 无新增未捕获异常。',
    '结果、备注、最后编辑主机/时间和上传证据在刷新后仍存在，并可从另一台主机同步看到。',
  ];
  test.cleanup = cleanupFor(test);
}

fs.writeFileSync(target, `${JSON.stringify(cases, null, 2)}\n`);
