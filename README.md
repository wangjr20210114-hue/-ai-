# 元宝主动服务 Demo

面向元宝 C 端用户的**主动式 AI 服务**创新方案。通过"感知-预判-服务"三层管线架构，让 AI 从被动响应升级为主动协作者，在**搜索问答、写作、翻译、文档总结、生图、腾讯会议**六大日常场景中，无需用户触发即可实时识别机会点并主动提供服务。

## 核心特性

- **主动服务气泡系统**：以非侵入式悬浮卡片展示 AI 主动建议，支持采纳/忽略，带来源场景标签与置信度指示器
- **六大主动服务场景**：搜索追问预判、写作素材先行、无感翻译、上传即总结、场景感知生图、自动创建腾讯会议
- **上下文感知面板**：实时展示 AI 对用户活动、关注点、情绪的理解，以及 Agent 任务执行时间线
- **误报过滤机制**：规则引擎第一层 + LLM 奖励模型第二层，降低打扰
- **用户偏好学习**：记录采纳/忽略反馈，动态调整触发阈值
- **Token 消耗追踪**：实时展示主动服务的 Token 与成本

## 技术栈

| 层 | 技术 |
| --- | --- |
| 前端 | Vite 5 + React 18 + TypeScript 5 |
| UI | TDesign React（唯一 UI 框架）+ tdesign-icons-react |
| 状态管理 | React Context + useReducer |
| 后端 | Python 3.11+ + FastAPI + WebSockets |
| 数据库 | SQLite（aiosqlite 异步） |
| LLM | 腾讯混元大模型 API（OpenAI 兼容） |
| 外部 API | 腾讯会议 API（AK/SK HMAC-SHA256 鉴权） |

## 架构

```
用户活动 → [感知层]上下文采集 → [预判层]意图预测+机会检测
        → [过滤层]奖励模型过滤 → [服务层]工具调度+服务生成
        → WebSocket 推送 → TDesign 气泡展示
```

后端采用**工具驱动型 Agent** 架构（参考 claude-code-tudou）：

- `agent/`：编排器 / 上下文管理 / 意图预测 / 机会检测 / 奖励过滤
- `tools/`：每个场景一个 Tool，继承 `BaseTool`，统一接口
- `services/`：混元 API、腾讯会议 API、WebSocket Hub
- `scenarios/scenario_type.py`：`ScenarioType` 枚举

### 扩展新场景（三步）

1. 在 `scenarios/scenario_type.py` 的 `ScenarioType` 新增枚举值
2. 在 `tools/` 继承 `BaseTool` 实现新 Tool 类
3. 在 `agent/orchestrator.py` 的 `_build_tool_map()` 注册映射

## 快速开始

### 后端

```bash
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env      # 按需填入混元/腾讯会议密钥
./venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

> 未配置真实密钥时，`MOCK_MODE=true` 会返回模拟数据，保证 Demo 可离线演示。

### 前端

```bash
cd frontend
npm install
npm run dev               # 默认 http://localhost:5173，已配置 /api 与 /ws 代理
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
├── agent/                  # 编排层
├── tools/                  # 工具层（BaseTool + 6 场景 Tool）
├── services/               # 混元 / 腾讯会议 / WebSocketHub
├── database/               # SQLite 连接、建表、仓储
├── models/schemas.py       # Pydantic 模型
├── prompts/templates.py    # LLM 提示词（含禁令式设计）
└── scenarios/scenario_type.py  # 枚举
frontend/
└── src/
    ├── components/         # chat / proactive / scenario / common
    ├── hooks/              # useWebSocket
    ├── services/           # api / websocket
    ├── store/              # AppContext（Context + useReducer）
    └── types/              # 全局类型
```

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `HUNYUAN_API_KEY` / `HUNYUAN_BASE_URL` / `HUNYUAN_MODEL` | 混元大模型 |
| `TENCENT_MEETING_SECRET_ID` / `SECRET_KEY` / `APP_ID` / `SDK_ID` / `OPERATOR_ID` | 腾讯会议 |
| `MOCK_MODE` | 为 `true` 时返回模拟数据 |
