# EdgeOne Makers 部署与验收

## 1. 前置条件

- EdgeOne CLI `>= 1.6.7`。
- 已创建或关联 Makers 项目。
- Node.js 22。
- Python 3.11 用于与 CI 对齐的本地 Agent 测试。
- 个人部署默认 `single_user`，不需要数据库。
- 只有 `multi_user` 模式需要创建 Neon 并执行 `db/001_users.sql`。

## 2. 环境变量

### 所有模式必需

- `AI_GATEWAY_API_KEY`
- `AI_GATEWAY_BASE_URL`
- `AI_GATEWAY_MODEL`（可省略，代码有 Makers 默认模型）
- `AUTH_MODE=single_user`（个人部署推荐）

### 仅多用户模式必需

- `AUTH_MODE=multi_user`
- `DATABASE_URL`
- `JWT_SECRET`，至少 32 字符
- `PROACTIVE_SCHEDULE_SECRET`，至少 32 字符

### 业务 Provider

- `WSA_API_KEY`
- `TENCENT_MAP_SERVER_KEY`
- `VITE_TENCENT_MAP_KEY`
- `HUNYUAN_IMAGE_API_KEY`
- `HUNYUAN_VISION_API_KEY`（可复用生图 Key 时可省略）
- 腾讯会议五项凭据均为最后阶段可选连接器；未配置时不暴露会议创建工具，不影响部署。

一次性数据迁移可配置 `LEGACY_IMPORT_SECRET`，验收后必须删除。完整步骤见 [`DATA_MIGRATION.md`](DATA_MIGRATION.md)。

真实值只配置在 Makers 环境，不提交 `.env`。

## 3. 本地发布检查

```bash
python -m compileall -q agents
python -m unittest discover -s agents/_tests -v
python -m unittest discover -s tools/tests -v
node --test cloud-functions/_jwt.test.js cloud-functions/platform-reuse.test.js
cd frontend
npm ci
npm test
npm run lint
npm run build -- --mode edgeone
```

## 4. 本地 Makers 联调

```bash
edgeone whoami
edgeone makers link
edgeone makers env pull
edgeone makers dev
```

使用 CLI 输出的统一代理地址验证静态前端、Agent 和 Cloud Functions，不单独启动 FastAPI。

## 5. Preview 部署

```bash
edgeone makers env ls
edgeone makers deploy --env preview --json
```

推荐先把目标 Git 分支关联到 Makers 项目，再从控制台创建 Preview；平台 Git 构建链会执行 `edgeone makers ci` 并登记 Functions、Agents 和 Schedule。必须确认控制台“函数”和“Agents”页签有实际路由，并确认应用从“连接中”切换为“已连接”；仅根页面 200 不算验收。

若动态路径回退为 `index.html`，先检查构建日志中 `generate-routes` 是否完成。Makers 当前要求 Schedule 最短间隔为 1 天；违反限制会在生成 `routes.json` 前退出，只留下静态资源。Preview 验收通过后才可以执行会替换当前线上版本的生产发布：

```bash
edgeone makers deploy --env production --json
```

未绑定自定义域名时，默认 `edgeone.cool` 地址启用访问保护。请从 Deployment 的“预览”按钮获取 3 小时链接进行验收；需要长期公开访问时再绑定自定义域名。

### 发布纪律

1. 功能修改只进入独立验收分支，先生成 Preview；生产分支不得作为调试环境。
2. 打开 Preview 的 `/test-cases/index.html`，填写 Deployment ID，逐项执行测试站中的生产阻断用例。
3. 测试结果、请求 ID、截图名和问题记录在测试站中，并导出 JSON 留档。
4. 任一生产阻断用例失败或阻塞时禁止合并生产分支；修复后必须重新构建 Preview 并从相关模块开始回归。
5. 只有自动化、Preview 人工验收和测试记录同时通过，才允许发布生产；生产发布后只做非破坏性冒烟回归。

## 6. 必测清单

下列清单的可执行步骤、测试数据、预期结果和证据要求以静态测试站 `/test-cases/index.html` 为准；测试站同时记录需配置、平台待验证、部分实现和未实现能力，不能用“不适用”掩盖应当阻断生产的失败项。

1. 单用户模式无需登录即可使用全部核心功能；多用户模式再测注册、登录、退出和未登录 401。
2. 多用户模式测试 A/B 用户会话、Workspace、Blob、Memory、Proactive 和连接器互不可见。
3. 对话流式输出、5 秒心跳、停止和刷新恢复。
4. 联网搜索来源、图片和严格今日日期过滤。
5. 地点、地图、路线和日程确认。
6. 腾讯会议仅在连接器配置后测试；不作为个人核心 Preview 阻塞项。
7. 文生图、图生图、版本轮播、单图/ZIP 下载。
8. PDF 上传、阅读库、论文检索、全文助读。
9. 浏览器关闭跨整点后 `last_tick` 推进且提醒不重复。
10. `/system` 无待核对 Action，Makers Trace 可看到对应 Run。

## 7. 回滚

- 保留部署前稳定 Deployment ID。
- Schema 变更只允许向前兼容和幂等执行。
- Preview 验收失败时回滚部署，不删除 Blob、Store、Neon 或旧 SQLite 数据。
- Provider 凭据切换失败时关闭对应能力入口并显示明确配置状态，不能回退到外部 FastAPI。
