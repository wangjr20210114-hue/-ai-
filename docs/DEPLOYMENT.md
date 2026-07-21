# EdgeOne Makers 部署与验收

## 1. 前置条件

- EdgeOne CLI `>= 1.6.7`。
- 已创建或关联 Makers 项目。
- Node.js 22。
- Python 3.11 用于与 CI 对齐的本地 Agent 测试。
- 固定个人单所有者部署，不需要应用数据库或身份环境变量。

## 2. 环境变量

### 必需

- `AI_GATEWAY_API_KEY`
- `AI_GATEWAY_BASE_URL`
- `AI_GATEWAY_MODEL`（可省略，代码有 Makers 默认模型）

### 业务 Provider

- `WSA_API_KEY`
- `TENCENT_MAP_SERVER_KEY`
- `VITE_TENCENT_MAP_KEY`
- `HUNYUAN_IMAGE_API_KEY`
- `HUNYUAN_VISION_API_KEY`（可复用生图 Key 时可省略）
- `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_WORKERS_AI_TOKEN`（推荐的每日免费额度视觉/生图降级）
- `DASHSCOPE_API_KEY`、`GEMINI_API_KEY`（可选的视觉理解后备，不承担当前免费生图）
- 腾讯会议为最后阶段可选 Skill；个人部署只需从官方 AI Skill 页面取得 `TENCENT_MEETING_TOKEN` 并保存到 Preview 环境变量，不需要企业五项凭据。未配置时不暴露会议创建工具，不影响部署。

默认搜索硬预算为 SearchPro 10 秒、页面媒体 5 秒、视觉审核 7 秒，可用 `RICH_SEARCH_PROVIDER_TIMEOUT_SECONDS`、`RICH_SEARCH_MEDIA_TIMEOUT_SECONDS`、`RICH_SEARCH_VISION_TIMEOUT_SECONDS` 在 Preview 调整。免费视觉 Provider 的额度与配置步骤见 [`VISUAL_PROVIDER_FALLBACK.md`](VISUAL_PROVIDER_FALLBACK.md)。

一次性数据迁移可配置 `LEGACY_IMPORT_SECRET`，验收后必须删除。完整步骤见 [`DATA_MIGRATION.md`](DATA_MIGRATION.md)。

真实值只配置在 Makers 环境，不提交 `.env`。

## 3. 本地发布检查

```bash
. .venv/bin/activate
python -m compileall -q agents
python -m unittest discover -s agents/_tests -v
python -m unittest discover -s tools/tests -v
npm test
npm --prefix frontend ci
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build -- --mode edgeone
git diff --check
```

测试站启动和完整回归说明见 [`TESTING.md`](TESTING.md)。

## 4. 本地 Makers 联调

```bash
edgeone whoami
edgeone makers link
edgeone makers env pull
edgeone makers dev
```

使用 CLI 输出的统一代理地址验证静态前端、Agent 和 Cloud Functions，不单独启动 FastAPI。

## 5. Preview 部署

当前 `ai-active-agent` 是 GitHub Provider 项目。`edgeone makers deploy` 只支持 Upload Provider，对本项目执行会返回“project has Provider 'Github'”并拒绝本地目录或 ZIP 直传。

正确流程：

```bash
git push -u origin <当前分支>
```

1. 打开 EdgeOne 控制台 → Makers → `ai-active-agent` → 构建部署。
2. 点击“新建部署”，选择刚推送的目标分支。
3. 核对环境为“预览”、提交 SHA 与本地提交一致，再点击确定。
4. 平台 Git 构建链会执行前端构建并登记 Cloud Functions、Agents 和 Schedule。
5. 等待状态为“成功”，确认“函数”和“Agents”页签有实际路由。
6. 点击“预览”取得 3 小时签名链接；确认应用从“连接中”切换为“已连接”。仅根页面 200 不算验收。

若动态路径回退为 `index.html`，先检查构建日志中 `generate-routes` 是否完成。Makers 当前要求 Schedule 最短间隔为 1 天；违反限制会在生成 `routes.json` 前退出，只留下静态资源。

Preview 验收通过后，只有获得明确生产发布授权，才能在控制台创建或提升 Production Deployment。生产发布不能作为调试步骤，也不能由文档更新自动触发。

未绑定自定义域名时，默认 `edgeone.cool` 地址启用访问保护。请从 Deployment 的“预览”按钮获取 3 小时链接进行验收；需要长期公开访问时再绑定自定义域名。

### 发布纪律

1. 功能修改只进入独立验收分支，先生成 Preview；生产分支不得作为调试环境。
2. 打开 Preview 的 `/test-cases/`，填写 Deployment ID，逐项执行测试站中的生产阻断用例。
3. 测试结果、请求 ID、截图名和问题记录在测试站中，并导出 JSON 留档。
4. 任一生产阻断用例失败或阻塞时禁止合并生产分支；修复后必须重新构建 Preview 并从相关模块开始回归。
5. 只有自动化、Preview 人工验收和测试记录同时通过，才允许发布生产；生产发布后只做非破坏性冒烟回归。

## 6. 必测清单

下列清单的可执行步骤、测试数据、预期结果和证据要求以静态测试站 `/test-cases/` 为准；测试站同时记录需配置、平台待验证、部分实现和未实现能力，不能用“不适用”掩盖应当阻断生产的失败项。

1. 无需登录即可使用个人工作区全部核心功能。
2. 对话流式输出、5 秒心跳、停止和刷新恢复。
3. 联网搜索来源、图片、可持久化搜索设置和严格今日日期过滤。
4. 地点、地图、路线和日程确认。
5. 腾讯会议仅在连接器配置后测试；不作为个人核心 Preview 阻塞项。
6. 文生图、图生图、版本轮播、单图/ZIP 下载。
7. PDF 上传、阅读库、论文检索、全文助读。
8. 浏览器关闭跨整点后 `last_tick` 推进且提醒不重复。
9. `/system` 无待核对 Action，Makers Trace 可看到对应 Run。

## 7. 回滚

- 保留部署前稳定 Deployment ID。
- Schema 变更只允许向前兼容和幂等执行。
- Preview 验收失败时回滚部署，不删除 Blob、Store 或旧 SQLite 数据。
- Provider 凭据切换失败时关闭对应能力入口并显示明确配置状态，不能回退到外部 FastAPI。
