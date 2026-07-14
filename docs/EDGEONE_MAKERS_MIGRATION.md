# EdgeOne Makers 改造说明

## 状态

迁移已完成。主应用现在只有一条可执行产品链路：React/Vite → EdgeOne Makers Agent/Cloud Function → LangGraph Store/Blob。旧 `backend/` 单体 FastAPI、SQLite 和 WebSocket 实现已删除，不再承担兼容或回退职责。独立 `place-service/` 仍以 FastAPI 暴露 PostGIS 地点查询，但不承载主应用 API、会话或前端回退。

## 平台映射

| 需求 | 当前实现 |
| --- | --- |
| 流式对话 | `agents/chat/index.py` + SSE |
| 模型 | `agents/chat/_llm.py` 直连混元 Token Plan |
| 联网搜索 | `ctx.tools` 注入平台搜索与页面读取工具 |
| 图像筛选 | `_rich_search.py` 并发调用视觉模型审核实际画面 |
| 短期状态 | LangGraph Checkpointer |
| 长期偏好/日程 | LangGraph Store |
| 对话恢复 | `agents/messages/index.py` |
| 取消 | AbortSignal + `agents/stop/index.py` |
| 文件 | Cloud Function 签名，浏览器直传 Makers Blob |
| 地点 | 独立 `place-service/` PostGIS 服务 + 腾讯地图 WebService |
| 地图 | 日历为单一数据源，腾讯 JS SDK 运行时配置 |

## 运行链路

```text
React/Vite
  ├─ POST /chat ─────────────► LangGraph Agent ─► 混元 / Makers Tools
  ├─ POST /messages ─────────► Checkpointer 恢复
  ├─ POST /travel ───────────► Store 日程 / 地点 / 路线
  ├─ POST /stop ─────────────► 取消当前运行
  └─ POST /files + signed PUT ► Makers Blob

地点：Agent ─► 私有 PostGIS ─► 腾讯地图兜底
地图：所选日期日程 ─► /travel daily_route ─► 腾讯 JS SDK 可视化
```

## 必须保持的契约

- `/chat`、`/messages`、`/travel` 和 `/stop` 携带 `makers-conversation-id`。
- Agent 只从 `ctx.env` 读取环境变量，不读取进程环境。
- SSE 事件包括 `ai_response`、`search_progress`、`tool_call`、`tool_result`、`map_places`、`travel_plan`、`follow_ups`、`usage`、`ping`、`error_message`，以 `[DONE]` 结束。
- `travel_plan` 只发送已写入并回读确认的日程；回答、日历与地图必须引用同一组地点。
- 浏览器地图 Key 由 `/travel` 的 `public_map_config` 在运行时返回，不能把服务端 WebService Key 当作构建变量注入。
- 地图只读取当前日历日期：有可连线路线时显示路线；无路线但已授权位置时显示当前位置；两者都没有时显示位置授权按钮。
- 富媒体 URL 必须存在于当前消息的可信搜索元数据中；图片只有通过视觉相关性与广告审核才能展示。
- 回答正文不承载追问区；追问作为独立 `follow_ups` 事件显示。

## 已删除的旧边界

2026-07-14 清理了以下不可达实现：

- `backend/` 单体 FastAPI、SQLite、WebSocket、Collector、旧技能与其测试；
- 前端本地 token、WebSocket transport 和 `/api/*` 回退分支；
- 旧旅行表单、计划卡、平行路线图；
- 论文库/PDF.js 阅读器；Blob PDF 上传保留；
- Action/记忆/预算/备份调试面板；
- 对应类型、CSS、`pdfjs-dist` 依赖和历史实施文档。

仍有效的 Makers Agent 测试迁移到根目录 `tests/`。

`place-service/` 是独立部署的地点数据服务，也是仓库中唯一保留的 FastAPI 边界；前端和 Agent 不把它当作旧 `/api/*` 兼容后端。

## 开发与部署

```powershell
npm run dev:makers
npm run verify:makers
edgeone makers deploy --json
```

不要用普通 Vite dev server 模拟生产路由；Makers dev server 才会注入 Agent、Store、平台工具、Function 和环境变量。
