# 测试与测试 Case 启动

本文是当前版本的测试入口事实源。生产运行时只有 EdgeOne Makers，不需要也不能启动旧 FastAPI。

搜索、自动记忆、自然语言日程 CRUD 与主动提醒同步的专项实测记录见 [SEARCH_MEMORY_CALENDAR_VERIFICATION_2026-07-20.md](./SEARCH_MEMORY_CALENDAR_VERIFICATION_2026-07-20.md)。

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

当前分支 2026-07-21 的已验证结果：Cloud Functions/Schedule 适配/平台约束 20 项、前端 Vitest 44 项、Python Agent 111 项、迁移工具 2 项均通过；ESLint、TypeScript/Vite 构建、`edgeone makers build` 和 `git diff --check` 通过。运行 Python 测试前必须先激活上一步创建的 `.venv`；直接使用未安装依赖的系统 Python 会报 `langchain_core` 缺失，这属于本地环境错误而不是代码失败。主包体积警告是已知非阻断优化项。

搜索调用次数要在 Makers 控制台日志中验证：按本次请求时间范围搜索 `rich_search provider_call`，同一轮应恰好 1 条；第二个相同查询命中缓存时会出现 `rich_search cache_hit`。浏览器 Network 只看到外层 `POST /chat`，不能据此推断内部工具次数。

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

1. 页面显示 67 条测试用例。
2. 顶部同步状态显示“已同步”，而不是“离线模式”。
3. 修改任一测试结果或备注后版本号递增。
4. 刷新页面后数据仍存在；另一台主机使用同一 Makers 环境时能看到更新。
5. 上传图片或视频证据后，刷新仍可打开附件。

若端口不是 8088，以 CLI 实际输出为准。不要另外启动 `backend/`、Uvicorn 或 FastAPI。

## 4. 只启动静态测试页面

只检查表格、步骤文字、筛选和布局时可以使用 Vite：

```bash
npm --prefix frontend run dev
```

访问：

```text
http://127.0.0.1:5173/test-cases/index.html
```

Vite 不应用 `edgeone.json` 中的 `/test-cases/` rewrite，因此必须使用上面的 `index.html` 完整路径。此模式没有 `/acceptance` Cloud Function，页面会进入离线模式：文本结果只保存在当前浏览器 `localStorage`，无法验证跨主机同步、冲突检测、编辑审计或证据上传。它不能代替完整 Makers 验收。

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

不要把签名链接、Cookie、同步密钥或 Provider Key 写进备注、截图、JSON 导出或 GitHub。

## 6. 测试数据边界

- Preview 使用 `TEST-` 前缀的会话、日程、文件夹和临时文件。
- Production 只做只读冒烟，不执行故障注入、网络阻断、无效 Provider 或付费批量测试。
- 测试结果、备注和审计保存在 Makers Blob `yuanbao-acceptance-shared/v2/state.json`。
- 图片证据上限 20MB，视频证据上限 100MB；证据位于 `v2/evidence/<CASE-ID>/`。
- 多台主机要填写不同的“当前主机名称”；遇到 HTTP 409 先同步最新记录再重新填写。
- 自动记忆内容不在网页展示；MEM-01/02 通过跨会话行为验收。清理只能在专用 Preview 使用“设置 → 主动策略与预算 → 自动记忆控制 → 清除全部自动记忆”，禁止在 Production 清除正式数据。

每个用例的逐步操作、预期结果和恢复方式以测试站页面为准，持久化实现细节见 [`ACCEPTANCE_SITE.md`](ACCEPTANCE_SITE.md)。
