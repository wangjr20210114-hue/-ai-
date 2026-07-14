# 元宝 Agent · EdgeOne Makers

本仓库只维护 EdgeOne Makers 生产架构。旧 `backend/` 单体 FastAPI、SQLite、本地 WebSocket、论文库、主动式本地 Runtime 和双运行时兼容层已在 2026-07-14 删除，避免生产代码继续依赖不可达的 `/api/*`。独立部署的 `place-service/` 仅提供地点数据，不是主应用回退后端。

## 当前能力

| 能力 | 实现 |
| --- | --- |
| 主对话 | `agents/chat/index.py`，LangGraph + SSE |
| 模型 | 腾讯混元 Token Plan，密钥来自 `ctx.env` |
| 联网与图文回答 | Makers 平台工具 + 视觉相关性/广告审核 |
| 对话恢复 | LangGraph Checkpointer，`agents/messages/index.py` 回读 |
| 长期旅行偏好与日程 | LangGraph Store，`agents/travel/index.py` 提供 CRUD |
| 地点与路线 | 私有地点服务优先，腾讯地图 WebService 兜底 |
| 浏览器地图 | 运行时读取 JS Key，失败时显示明确降级提示 |
| 文件 | `cloud-functions/files/index.js` 签名后直传 Makers Blob |
| 前端 | React + Vite，仅使用 Makers SSE/Agent/Function 路由 |

## 目录

```text
agents/
├── chat/                 # POST /chat
├── messages/             # POST /messages
├── travel/               # POST /travel
└── stop/                 # POST /stop
cloud-functions/
└── files/                # /files，Blob 签名、读取与删除
frontend/                 # React + Vite Makers 客户端
place-service/            # 独立 PostgreSQL/PostGIS 地点服务
tests/                    # Makers Agent 回归测试
docs/                     # 当前架构说明
edgeone.json              # Makers 构建与 Agent 配置
requirements.txt          # Agent 运行依赖
```

## 环境变量

把 `.env.example` 中的变量配置到 Makers 项目，不要提交真实值。

| 变量 | 用途 | 必需性 |
| --- | --- | --- |
| `HUNYUAN_API_KEY` | 腾讯混元 Token Plan | 是 |
| `HUNYUAN_BASE_URL` | 模型 API 地址，已有默认值 | 否 |
| `HUNYUAN_MODEL` | 模型名，默认 `hy3` | 否 |
| `WSA_API_KEY` | 联网搜索 | 使用联网搜索时是 |
| `PLACE_API_BASE_URL` | 私有地点服务地址 | 可用默认生产地址 |
| `PLACE_API_TOKEN` | 私有地点服务认证 | 使用地点专库时是 |
| `TENCENT_MAP_SERVER_KEY` | 地点搜索与道路路线 | 使用腾讯路线时是 |
| `VITE_TENCENT_MAP_KEY` | 浏览器腾讯地图 JS Key；由 `/travel` 运行时返回 | 显示底图时是 |

服务端 Key 与浏览器 JS Key 必须分开创建。JS Key 需要配置生产域名白名单；SDK、鉴权或瓦片加载失败时，前端保留路线示意图，并提示检查权限、白名单或额度。

## 旅行数据链路

1. 服务端按上海时区解析明确日期和“今天/明天/后天”等相对日期。
2. 地点查询按数据时效选择私有库或腾讯地图，并只保留可验证坐标。
3. 结构化行程先写入 Store，再回读确认。
4. `travel_plan` 把已落库日程推送到前端，日历立即切换目标日期。
5. 地图只消费所选日期的日程；有至少两个有效地点时绘制路线，否则按位置授权规则显示当前位置或授权按钮。
6. 模型可自由组织回答，但必须完整包含已落库的日期、时间和地点；遗漏时仅追加数据摘要，不替换整篇回答。

## 本地开发

主应用本地开发同样使用 Makers dev server，不再提供旧单体 FastAPI/Vite 代理模式。

```powershell
edgeone makers link
edgeone makers env pull
npm run dev:makers
```

如需本地运行地点服务：

```powershell
npm run setup:travel-local
npm run dev:travel-local
```

## 检查与部署

```powershell
npm run verify:makers
edgeone makers env ls
edgeone makers deploy --json
```

`verify:makers` 依次检查地点规则、Makers Agent、前端测试、Lint 和两种 Vite 构建。完整运行契约见 [EdgeOne Makers 改造说明](docs/EDGEONE_MAKERS_MIGRATION.md)，富媒体安全链路见 [结构化图文回答](docs/RICH_ANSWER_ARCHITECTURE.md)。

## 维护边界

- 不为主应用重新引入 FastAPI、SQLite、本地 WebSocket 或按域名切换的第二运行时；`place-service/` 只保持独立地点数据边界。
- Agent 状态只使用 Makers Checkpointer/Store；文件只使用 Makers Blob。
- 新增结构化业务能力时优先扩展 Agent/Cloud Function，确需关系数据再单独选择托管数据库。
- 删除能力时同步删除不可达组件、API、类型、样式、依赖和过期文档，避免保留“以后可能用”的影子实现。
