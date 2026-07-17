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

保存完整 JSON 输出中的 Deployment ID 和 Preview URL。当前项目的 Preview 端点存在“静态页面回退覆盖动态路由”的已知平台问题：必须确认 `/auth/user` 返回 JSON、`/workspace` 返回 JSON 后，才可把 Preview 判定为通过；仅根页面 200 不算验收。

若 Preview 同样回退为 `index.html`，请在 Makers 控制台查看该 Deployment 的 Cloud Function/Agent 路由和调用日志；确认后才可以执行会替换当前线上版本的生产发布：

```bash
edgeone makers deploy --env production --json
```

## 6. 必测清单

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
