# 测试与测试 Case 启动

本文是当前版本的测试入口事实源。生产运行时只有 EdgeOne Makers，不需要也不能启动旧 FastAPI。

比赛主动机会、自动记忆、自然语言日程和文档上传闭环见 [CONTEST_SOLUTION.md](./CONTEST_SOLUTION.md)。

## 1. 安装依赖

要求 Node.js 22、Python 3.11+ 和 EdgeOne CLI 1.6.7+。在仓库根目录执行：

```bash
npm ci
npm --prefix frontend ci
```

Python Agent 测试推荐使用虚拟环境，并安装根依赖：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

`.venv` 只供本地测试，不提交仓库。

## 2. 完整自动化回归

在仓库根目录执行：

```bash
npm test
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build -- --mode edgeone
python -m unittest discover -s agents/_tests -v
python -m unittest discover -s tools/tests -v
git diff --check
```

当前分支 2026-07-23 的已验证结果：Cloud Functions/Schedule/验收持久化 21 项、前端 Vitest 85 项（17 个测试文件）、Python Agent 144 项、迁移工具 2 项均通过；ESLint、TypeScript/Vite 构建和 `git diff --check` 通过。Python 新增直接回答零搜索、新闻/论文/地点三类查询调用审计和同轮 Provider 去重；前端新增 URL-only 与显式“来源”两种行内小字引用、进度文案、媒体去重与刷新后定位恢复测试。原有地图、腾讯会议、搜索媒体、流式 Markdown、主动机会和历史消息回归仍全部保留。Provider 脱敏实测见 [`PROVIDER_HEALTH_2026-07-22.md`](PROVIDER_HEALTH_2026-07-22.md)。运行 Python 测试前必须激活 `.venv`；系统 Python 缺依赖属于本地环境错误。主包体积警告是已知非阻断优化项。

搜索调用次数要在 Makers 控制台日志中验证：按本次请求时间范围搜索 `rich_search turn_audit`，正常冷查询应为 `invocations=1 provider_calls=1`；即使模型误发重复工具调用，`provider_calls` 仍必须保持 1；相同查询命中缓存时为 0。再用 `rich_search provider_call` 交叉核对。浏览器 Network 只看到外层 `POST /chat`，不能据此推断内部工具次数。

主动提醒窗口与断网恢复的验收要点：

- 先通过聊天产生 4 条不同的操作提醒，左栏和顶栏最多显示 4 条；第 5 条操作提醒会替换其中一条，历史 Event/Run 仍保留在 Makers Store。
- 让账户存在至少一条安全自动记忆，等待网页保持可见 10 分钟；控制台应看到一次 `memory_window` 检查。窗口有操作提醒时，记忆提醒可替换操作提醒；窗口全是记忆提醒时不新增；没有安全记忆时不新增。
- 断网后等待 20 秒，回答框应显示“网络有波动，正在从 Makers 已保存的进度恢复…”，而不是永久停在思考；恢复最多等待 2 分钟。点击停止会立即解除输入框锁定，网络恢复后再向 Makers 发送一次停止请求。
- EdgeOne Schedule 当前官方最小间隔为一天，不能把 `edgeone.json` 写成每 10 分钟 Cron；10 分钟检查只在网页在线时执行，关闭网页由每日 Schedule 兜底。

本轮重点人工回归位于测试站 CORE-04、SEARCH-01、SEARCH-05 和 TRAVEL-04：分别检查流式划词复制不抖、行内来源不抢跑、追问与回答并行且同宽，以及首次授权位置后刷新仍能显示地图。定位使用浏览器 5 分钟位置缓存并监听地图容器尺寸变化；失败时页面必须提供可点击的重试，而不是静默无响应。

## 3. 启动完整测试站（推荐）

此方式同时启动静态前端、Cloud Functions 和 Python Agents，能够验证测试结果、备注、编辑审计与图片/视频证据的 Makers Blob 持久化。

首次 clone 或切换 Makers 项目后：

```bash
edgeone whoami
edgeone makers link
edgeone makers env pull
```

然后启动：

```bash
edgeone makers dev
```

打开 CLI 输出地址下的 `/test-cases/`，通常为：

```text
http://127.0.0.1:8088/test-cases/
```

判断是否完整启动成功：

1. 页面显示当前范围测试用例（包含主动机会、文档主动总结、冷却反馈与 Apple 风格动效验收）。
2. 顶部同步状态显示“已同步”，而不是“离线模式”。
3. 修改任一测试结果或备注后版本号递增。
4. 刷新页面后数据仍存在；另一台主机使用同一 Makers 环境时能看到更新。
5. 上传图片或视频证据后，刷新仍可打开附件。

若端口不是 8088，以 CLI 实际输出为准。仓库已经没有 Uvicorn/FastAPI 服务，测试只启动 EdgeOne Makers 本地运行时。

## 4. 只启动静态测试页面

只检查表格、步骤文字、筛选和布局时可以使用 Vite：

```bash
npm --prefix frontend run dev
```

访问：

```text
http://127.0.0.1:5173/test-cases/index.html
```

Vite 不应用 `edgeone.json` 中的 `/test-cases/` rewrite，因此必须使用上面的 `index.html` 完整路径。此模式没有 `/acceptance` Cloud Function，页面会进入离线模式：文本结果只保存在当前浏览器 `localStorage`，无法验证跨主机同步、编辑审计或证据上传。它不能代替完整 Makers 验收。

## 5. 启动线上 Preview 测试站

当前 `ai-active-agent` 是 GitHub Provider 项目，发布步骤为：

1. 把目标分支推送到 GitHub。
2. 打开 EdgeOne 控制台 → Makers → `ai-active-agent` → 构建部署。
3. 点击“新建部署”，选择目标分支，确认环境为“预览”。
4. 等待状态变为“成功”，核对提交 SHA。
5. 点击“预览”，复制平台生成的完整 3 小时签名链接。
6. 在该链接路径后打开 `/test-cases/`。如果原链接带 `eo_token` 和 `eo_time`，必须保留查询参数；页面会自动把它们带到 `/acceptance` 和证据请求。

示例仅表示 URL 结构，不能复制占位 Token：

```text
https://<deployment>.edgeone.cool/test-cases/?eo_token=<平台签名>&eo_time=<到期时间>
```

不要把签名链接、Cookie 或 Provider Key 写进备注、截图、JSON 导出或 GitHub。

默认 `edgeone.cool` 域名的签名只在 3 小时内有效，适合 Preview 和临时生产验收，不是长期公开网址。跨主机共享的 Makers Blob 数据不会因此丢失；若要任何主机长期直接访问和编辑，必须在 Makers“域名管理”绑定自定义域名并完成 DNS/HTTPS 校验。

## 6. 测试数据边界

- Preview 使用 `TEST-` 前缀的会话、日程、文件夹和临时文件。
- Production 只做只读冒烟，不执行故障注入、网络阻断、无效 Provider 或付费批量测试。
- 测试结果、备注和审计保存在 Makers Blob `yuanbao-acceptance-shared/v2/state.json`。
- 图片证据上限 20MB，视频证据上限 100MB；证据位于 `v2/evidence/<CASE-ID>/`。
- 多台主机要填写不同的“当前主机名称”以便审计；按个人单编辑者设计，最后一次保存生效，不提供多人同时编辑冲突合并。
- 自动记忆内容不在网页展示；MEM-01/02 通过跨会话行为验收。清理只能在专用 Preview 使用“设置 → 主动策略与预算 → 自动记忆控制 → 清除全部自动记忆”，禁止在 Production 清除正式数据。

每个用例的逐步操作、预期结果和恢复方式以测试站页面为准，持久化实现细节见 [`ACCEPTANCE_SITE.md`](ACCEPTANCE_SITE.md)。
