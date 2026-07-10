# 元宝主动服务 Demo

> 当前仓库是功能原型基线，不是可长期无人值守运行的正式版主动式 Agent。基线状态见 [`docs/BASELINE.md`](docs/BASELINE.md)，完整改造路线见 [`docs/PROACTIVE_AGENT_REFACTOR_PLAN.md`](docs/PROACTIVE_AGENT_REFACTOR_PLAN.md)。

面向元宝 C 端用户的**主动式 AI 服务**创新方案。通过"感知-预判-服务"三层管线架构，让 AI 从被动响应升级为主动协作者，在**搜索问答、写作、翻译、文档总结、生图、腾讯会议**六大日常场景中，无需用户触发即可实时识别机会点并主动提供服务。

## 核心特性

- **主动服务气泡系统**：以非侵入式悬浮卡片展示 AI 主动建议，支持采纳/忽略，带来源场景标签与置信度指示器
- **六大主动服务场景**：搜索追问预判、写作素材先行、无感翻译、上传即总结、场景感知生图、自动创建腾讯会议
- **上下文感知面板**：实时展示 AI 对用户活动、关注点、情绪的理解，以及 Agent 任务执行时间线
- **误报过滤机制**：规则引擎第一层 + LLM 奖励模型第二层，降低打扰
- **用户偏好学习**：记录采纳/忽略反馈，动态调整触发阈值
- **Token 消耗追踪**：实时展示主动服务的 Token 与成本

## 能力状态

| 能力 | 当前状态 | 说明 |
| --- | --- | --- |
| 普通对话与流式回复 | 已实现 | 依赖已配置的模型 API |
| 搜索与来源整理 | 部分实现 | 多源搜索已接入，仍需统一超时、引用校验和降级 |
| 旅游规划与日程 | 已实现（被动） | 可生成计划和写入内部日程，主动天气守护尚未实现 |
| 腾讯会议 | 部分实现 | 需要本机安装并授权 `tmeet`，确认闭环将在 M2 改造 |
| 生图 | 部分实现 | 需要独立额度，确认和任务持久化将在 M2 改造 |
| 翻译 | 已实现（被动） | 当前默认翻译为中文 |
| 论文搜索与阅读 | 部分实现 | 搜索、下载、阅读可用，文件持久恢复将在 M1 改造 |
| 通用文件上传即总结 | 未实现 | 当前聊天上传入口尚未传输真实文件 |
| 后台主动感知与通知 | 未实现 | 调度、Collector、去重和免打扰将在 M3 改造 |
| 偏好学习与完整成本面板 | 未实现 | 数据模型和交互将在 M5–M6 改造 |

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Vite 5 + React 18 + TypeScript 5 |
| UI | TDesign React（唯一 UI 框架）+ tdesign-icons-react |
| 状态管理 | React Context + useReducer |
| 后端 | Python 3.11+ + FastAPI + WebSockets |
| 数据库 | SQLite（aiosqlite 异步） |
| LLM | 混元 + DeepSeek（OpenAI 兼容接口；混元负责对话/视觉/生图，DeepSeek 负责意图识别和结构化任务） |
| 外部 API | 腾讯地图、腾讯会议 tmeet CLI、arXiv、搜狗/WSA 搜索 |

## 架构

```
用户活动 → [感知层]上下文采集 → [预判层]意图预测+机会检测
        → [过滤层]奖励模型过滤 → [服务层]工具调度+服务生成
        → WebSocket 推送 → TDesign 气泡展示
```

后端采用**事件驱动 + 技能编排型 Agent** 架构：

- `agent/orchestrator.py`：统一处理事件、意图识别、执行策略、技能分发与运行日志
- `agent/context.py` / `events.py` / `policy.py` / `runtime.py`：会话上下文、事件模型、权限策略、执行记录
- `skills/`：每个场景一个 Skill，继承 `BaseSkill`，声明能力、触发词、权限等级与执行入口
- `services/`：混元/DeepSeek、搜索、地图、会议、论文等外部服务封装
- `api/`：REST 路由与 WebSocket 端点，负责协议接入，不再承担核心 Agent 决策
- `scenarios/scenario_type.py`：`ScenarioType` 枚举

### 扩展新场景（三步）

1. 在 `scenarios/scenario_type.py` 的 `ScenarioType` 新增枚举值
2. 在 `skills/` 继承 `BaseSkill` 实现新 Skill 类，并声明 `permission_level`
3. 在 `agent/__init__.py` 注册技能，并在 `api/websocket.py` 的 handler map 绑定执行函数

## 快速开始

### 后端

```bash
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.lock
cp .env.example .env      # 按需填入混元、DeepSeek、地图、搜索等密钥
./venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

> 当前代码默认不返回模拟数据；未配置真实密钥时会返回明确错误。`MOCK_MODE` 预留给后续离线演示模式。

### 前端

```bash
cd frontend
npm install
npm run dev               # 默认 http://localhost:5173，已配置 /api 与 /ws 代理
```

### 质量检查

```bash
# 后端
cd backend
python -m unittest discover -s tests -v

# 前端
cd frontend
npm run lint
npm test
npm run build
```

## 演示方式

1. 左侧选择场景，输入框上方提供一键示例
2. 输入内容并发送，右侧面板将实时展示：
   - **AI 上下文理解**（意图/关注点/情绪/关键词）
   - **Agent 任务时间线**（检测中→分析中→生成建议中→已推送）
   - **主动服务建议卡片**（滑入动画，可采纳/忽略）
3. 采纳的建议会回填到对话流；忽略后 5 分钟内不再推送同类建议

## 目录结构

```
backend/
├── main.py                 # FastAPI 入口
├── config.py               # 配置（读取 .env）
├── api/                    # REST 路由 + WebSocket 端点
├── agent/                  # 事件、上下文、策略、运行时、编排器
├── skills/                 # 技能层（BaseSkill + 场景 Skill）
├── services/               # LLM / 搜索 / 地图 / 会议 / 论文等服务
├── database/               # SQLite 连接、建表、仓储
├── models/schemas.py       # Pydantic 模型
├── prompts/templates.py    # LLM 提示词（含禁令式设计）
└── scenarios/scenario_type.py  # 枚举
frontend/
└── src/
    ├── components/         # chat / travel / paper / profile / common
    ├── hooks/              # useWebSocket
    ├── services/           # api / websocket
    ├── store/              # AppContext（Context + useReducer）
    └── types/              # 全局类型
```

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `HUNYUAN_API_KEY` / `HUNYUAN_BASE_URL` / `HUNYUAN_MODEL` | 混元对话/视觉模型 |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` | DeepSeek 意图识别、结构化任务、搜索总结 |
| `HUNYUAN_IMAGE_API_KEY` / `HUNYUAN_IMAGE_BASE_URL` / `HUNYUAN_IMAGE_MODEL` | 混元文生图 |
| `TENCENT_MAP_KEY` | 腾讯位置服务 |
| `WSA_API_KEY` / `WSA_BASE_URL` | WSA 搜索兜底（可选） |
| `tmeet auth login` | 腾讯会议通过 tmeet CLI 授权 |
| `MOCK_MODE` | 预留离线演示开关（当前核心链路未实现模拟数据） |
