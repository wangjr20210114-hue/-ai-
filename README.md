# 元宝主动式 Agent

> 当前版本：**本地单用户主动式 Agent + 结构化图文回答（v4.2.0）**
> 目标：在个人电脑上长期运行，可靠地感知事件、判断机会、遵守权限、征得确认、执行操作、恢复任务并向用户解释结果。

本仓库已经从"LLM 意图分类 + WebSocket 固定工具调用"的功能原型，改造成以 **Event → Run → Plan → Policy → PendingAction → Executor → Observation/Notification** 为主线的持久化 Agent。它适合本机个人助手场景，但仍不是多用户云服务，也不应未经额外安全建设直接暴露到公网。

## 当前已实现

| 领域 | 状态 | 说明 |
| --- | --- | --- |
| 固定本地身份、会话和消息 | 已实现 | 刷新、重连和后端重启后可恢复 |
| PDF 上传和文件恢复 | 已实现 | 签名校验、大小/页数限制、SHA-256 去重、持久索引 |
| Event / Run / Observation | 已实现 | 全链路持久化、状态机、审计时间线、启动恢复 |
| 不可变 PendingAction | 已实现 | 版本确认、快照哈希、唯一幂等键、过期和取消 |
| 单一 Executor | 已实现 | side_effect=True 的技能通过 ActionExecutor 执行 |
| Supervisor 与 Scheduler | 已实现 | 租约领取、失败恢复、启动扫描、优雅关闭 |
| 主动 Collector | 已实现 | 日程临近/逾期/冲突、旅行天气风险、文件上传事件 |
| 主动通知策略 | 已实现 | 去重、冷却、静默时段、每日上限、来源与原因 |
| ChatSkill 联网搜索 | 已实现 | 默认开启联网搜索增强，输入栏可切换开关 |
| 结构化图文回答 | 已实现 | 来源、图片和正文分离；模型只引用稳定 ID，前端安全解析、交错展示并提供图片出处 |
| ChatSkill follow_ups | 已实现 | 所有 Skill 生成"猜你想继续问"追问，基于 BaseSkill 共享方法 |
| 搜索 404 过滤 | 已实现 | HEAD/GET 双检 + 中文错误页面内容检测（知乎"荒原"等） |
| 生图确认执行 | 已实现 | 独立额度消耗属于外部副作用，先展示不可变确认卡片，再由唯一 Executor 调用混元 API |
| 会议直接创建 | 已实现 | AUTO 模式，直接创建会议；支持"改到""调整"等修改已有会议 |
| 记忆、反馈和预算 | 已实现 | 记忆需确认，反馈幂等，日/月预算可配置 |
| 长任务取消 | 已实现 | 用户取消会中止模型流并持久化；断线不会自动取消 |
| 本地安全 | 已实现 | 本地随机访问令牌、REST/WS 同源鉴权、SSRF 防护 |
| 备份和恢复 | 已实现 | 在线 SQLite 快照、文件哈希清单、重启时原子恢复 |
| 健康与可观测性 | 已实现 | Supervisor 心跳/队列/周期维护、启动恢复报告、请求 ID 与耗时日志 |

## 条件可用与剩余边界

- 模型、搜索、arXiv、腾讯地图、混元生图和腾讯会议仍依赖真实 Key、额度、外网或本机 CLI。
- 会议与生图使用 `provider_calls` 外部调用账本：若 Provider 成功响应已落库但 Action 尚未提交，系统可在租约恢复时自动补全成功状态；若连成功响应也未收到，则保守标记为人工核对，不盲目重试。
- 主动感知目前覆盖内部日程、旅行天气和文件上传；邮件、系统日历、浏览器活动、企业消息等外部 Collector 尚未接入。
- 旅游规划仍以领域服务和 REST 交互为主，还不是可逐步骤断点恢复的通用工作流引擎。
- 长模型任务在进程重启后可以按 Run 策略重新排队或明确失败，但不会从已生成的 token 位置继续生成。
- 当前是固定 `local-user` 的本地产品，不提供云端多租户、组织权限和远程账户体系。
- 前端生产构建通过，但主包仍有大于 500KB 的非阻塞警告，后续应按论文阅读器、地图和 Agent 管理面板进行动态拆包。

## 核心架构

```text
Transport (REST / WebSocket / Collector)
                │
                ▼
       AgentApplicationService
                │
                ▼
Event → Run → IntentRouter → Plan → PolicyEngine
                                      │
                      ┌───────────────┴───────────────┐
                      │                               │
                 自动执行                        需要确认
                      │                               │
                      ▼                               ▼
                 Single Executor              PendingAction
                      ▲                               │
                      └──────── Supervisor ◀─────────┘
                                      │
                        Observation / Notification
```

依赖方向：

```text
api / collectors
      ↓
application
      ↓
agent / skills / policy
      ↓
repositories / provider services
```

`api/websocket.py` 不再包含搜索、论文、翻译或模型调用逻辑；业务必须通过 Application Service、Skill 和唯一 Executor 进入。

## 目录结构

```text
backend/
├── application/                  # 应用用例：Action、通知、主动事件、记忆、反馈、预算
├── agent/
│   ├── collectors/               # 日程、文件、旅行天气 Collector
│   ├── policy/                   # 确定性权限、风险与通知策略
│   ├── cancellation.py           # 显式长任务取消
│   ├── executor.py               # 唯一执行入口
│   ├── orchestrator.py           # 分类、计划、策略和排队
│   ├── scheduler.py              # 持久定时任务调度
│   └── supervisor.py             # Run/Job 后台监督与恢复
├── api/                          # 薄 REST / WebSocket 传输层
├── database/repositories/        # SQLite 状态唯一写入边界
├── security/                     # 本地访问令牌
├── observability/                # 请求 ID、耗时与结构化日志
├── services/
│   ├── model_gateway.py          # 统一模型调用、错误和 Usage
│   ├── safe_http.py              # URL/DNS/重定向/大小安全策略
│   └── backup_service.py         # 校验备份和重启恢复
├── skills/                       # 版本化 Skill 与副作用输入模型
└── tests/
frontend/src/
├── components/profile/           # Action Center、记忆预算、健康与备份
├── services/auth.ts              # 本地令牌引导
├── services/api.ts               # REST 客户端
└── services/websocket.ts         # 带令牌的 WebSocket 客户端
```

## 新增 Skill 的强制规则

1. 在 `skills/` 中继承 `BaseSkill`，声明 schema、权限、风险、失败策略和 `side_effect`。
2. 纯读取 Skill 可实现 `execute` 或 `stream`；不得直接依赖 WebSocket。
3. 有副作用的 Skill 必须定义版本化 `action_input_model`、生成不可变快照和稳定幂等键，并只实现 `execute_action`。
4. 在 `agent/__init__.py` 的组合根注册；不得再向 WebSocket 增加业务 handler。
5. 新增状态只能由 Repository 在事务中更新，并同时写 Observation。
6. 至少增加成功、失败、重复请求、并发冲突、取消/恢复或副作用核对测试。

## 快速开始

### 后端

```bash
cd backend
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\pip install -r requirements.lock
# Linux/macOS:
./.venv/bin/pip install -r requirements.lock

copy .env.example .env   # Windows；Linux/macOS 使用 cp
# 按需配置模型、地图、搜索和生图 Key

# Windows PowerShell
.\.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8000
# Linux/macOS
./.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

首次启动会在 `.agent/access-token` 生成本地随机令牌。前端会通过仅允许回环客户端和白名单 Origin 的 Setup 接口自动获取，所有 `/api/*` 和 WebSocket 随后使用同一令牌。

### 前端

```bash
cd frontend
npm ci
npm run dev
```

默认访问 `http://127.0.0.1:5173`。Vite 将 `/api` 和 `/ws` 代理到本机后端。

## 质量检查

```bash
# 后端：当前 52 个 unittest
cd backend
python -m unittest discover -s tests -v

# 前端：当前 5 个 Vitest + ESLint + TypeScript/Vite
cd frontend
npm test -- --run
npm run lint
npm run build
```

图文回答的协议、信任边界、扩展方式和架构审查见
[`docs/RICH_ANSWER_ARCHITECTURE.md`](docs/RICH_ANSWER_ARCHITECTURE.md)。

## 管理与恢复

右侧"我的"面板提供：

- **Agent Activity Center**：待确认 Action、通知、Run 时间线、Scheduler 状态和任务取消。
- **Agent Intelligence**：记忆提案确认/拒绝、长期记忆删除、日/月预算。
- **系统安全与恢复**：健康检查、完整备份导出、备份校验与暂存恢复。

恢复不会在服务运行中替换数据库。上传备份后，系统先验证 ZIP 路径、哈希、文件清单和 SQLite 完整性；下次启动时再原子替换数据库和托管文件，并在 `.agent/restore-safety/` 保存恢复前副本。备份明确不包含 `.env`、API Key 和本地访问令牌。

## 主要环境变量

| 变量 | 说明 |
| --- | --- |
| `APP_HOST` / `APP_PORT` | 默认 `127.0.0.1:8000` |
| `CORS_ORIGINS` | 允许的本地前端 Origin |
| `DB_PATH` | SQLite 数据库路径 |
| `FILE_STORAGE_DIR` | 托管 PDF 文件目录 |
| `LOCAL_AUTH_ENABLED` | 是否启用本地访问令牌，默认开启 |
| `LOCAL_ACCESS_TOKEN` | 可选固定令牌；默认自动生成 |
| `AGENT_STATE_DIR` | 本地令牌、备份和待恢复文件目录，默认 `./.agent` |
| `LOCAL_TOKEN_PATH` | 自动生成令牌的保存路径 |
| `HUNYUAN_*` | 混元文本、视觉和生图配置 |
| `DEEPSEEK_*` | DeepSeek 配置 |
| `TENCENT_MAP_KEY` | 腾讯地图配置 |
| `WSA_*` | 搜索兜底配置 |
| `DAILY_COST_BUDGET_CNY` | 初始每日预算默认值 |

不要提交 `.env`、数据库、上传文件、`.agent/`、虚拟环境、`node_modules` 或构建产物。
