---
name: 元宝·灵犀 主动式AI服务系统
overview: 为元宝C端用户设计一套"无需用户主动触发，AI实时识别机会点并主动提供服务"的创新演示系统，包含剪贴板感知、日程预判、写作伴侣、知识雷达、情绪关怀五大主动服务模块，采用 Next.js + TypeScript 前端 + Python FastAPI 后端 + LLM API 的技术栈。
design:
  architecture:
    framework: react
    component: shadcn
  styleKeywords:
    - Glassmorphism
    - Dark Mode
    - Glowing Accents
    - Floating Cards
    - Gradient Mesh
  fontSystem:
    fontFamily: PingFang SC
    heading:
      size: 28px
      weight: 700
    subheading:
      size: 18px
      weight: 600
    body:
      size: 15px
      weight: 400
  colorSystem:
    primary:
      - "#1677FF"
      - "#4096FF"
      - "#722ED1"
      - "#9254DE"
    background:
      - "#0A0E27"
      - "#111632"
      - "#1A1F3A"
    text:
      - "#FFFFFF"
      - "#E8ECF4"
      - "#8B95B7"
    functional:
      - "#52C41A"
      - "#FF4D4F"
      - "#FAAD14"
      - "#1677FF"
todos:
  - id: setup-scaffold
    content: 初始化Next.js前端和FastAPI后端项目结构，配置TypeScript、Tailwind、CORS等基础环境
    status: pending
  - id: backend-core
    content: 实现上下文管理器、意图预测器、机会检测器和奖励过滤器四个核心组件
    status: pending
    dependencies:
      - setup-scaffold
  - id: backend-scenarios
    content: 实现5个场景处理器和建议生成器，集成LLM API完成主动服务逻辑
    status: pending
    dependencies:
      - backend-core
  - id: frontend-chat
    content: 构建对话界面、消息列表、输入栏和场景选择器组件
    status: pending
    dependencies:
      - setup-scaffold
  - id: frontend-proactive
    content: 实现灵犀气泡系统、上下文感知面板和Framer Motion动画，使用[skill:多模态内容生成]生成场景演示素材
    status: pending
    dependencies:
      - frontend-chat
  - id: integrate-polish
    content: 前后端WebSocket联调，测试全部5个场景的主动服务流程，使用[skill:pptx]生成比赛演示文稿
    status: pending
    dependencies:
      - backend-scenarios
      - frontend-proactive
---

## 产品概述

**元宝灵犀** —— 面向元宝C端用户的主动式AI服务创新方案。通过"感知-预判-服务"三层架构，让AI从被动响应升级为主动协作者，在搜索问答、写作、翻译、文档总结、生图五大日常场景中，无需用户触发即可实时识别机会点并主动提供服务。

## 核心功能

### 1. 灵犀气泡系统（非侵入式主动服务载体）

- 以悬浮气泡形式展示AI主动服务建议，不打断用户当前操作
- 支持展开/收起/忽略/采纳四种交互
- 气泡带有来源场景标签和置信度指示器

### 2. 五大主动服务场景

- **搜索问答 - 深度追问预判**：AI回答后主动分析追问方向，以灵犀气泡展示2-3个预判问题
- **写作 - 素材先行**：检测写作行为时主动收集素材；停顿超阈值时主动提供续写建议；检测专业术语时主动推送解释卡片
- **翻译 - 无感翻译**：检测到外文输入时主动准备翻译，输入框旁显示翻译预览气泡
- **文档总结 - 上传即总结**：文档上传完成瞬间主动启动总结，结果以卡片滑入，同时生成关键探索问题
- **生图 - 场景感知生图**：用户描述场景时主动生成配图建议，识别情绪/风格关键词主动匹配

### 3. 上下文感知面板

- 实时展示AI对用户当前上下文的理解（活动类型、关注点、情绪倾向）
- 展示用户偏好学习结果，增强透明度和信任感

### 4. 误报过滤机制

- 基于规则的第一层快速过滤 + LLM二次判断的奖励模型简化版
- 降低误报率，避免过度打扰用户

## 视觉效果

整体采用深色玻璃拟态风格，灵犀气泡以柔和发光的半透明卡片形式从侧边滑入，带有微动画呼吸效果。场景切换流畅自然，上下文面板以实时更新的数据流形式展示AI的"思考过程"，营造科技感与温度感并存的体验。

## 技术栈选择

- **前端**：Next.js 14+ (App Router) + TypeScript + Tailwind CSS + Framer Motion
- **后端**：Python 3.11+ + FastAPI + WebSockets
- **LLM调用**：OpenAI兼容API（支持混元/OpenAI），用于意图预测和服务生成
- **状态管理**：Zustand（前端），内存态（后端Demo）

## 技术选型理由

- **Next.js**：SSR支持好、组件生态丰富、TypeScript原生支持，适合快速搭建高质量Demo
- **FastAPI**：异步高性能，与LLM生态无缝对接，自动生成API文档便于调试
- **WebSocket**：实现主动服务的实时推送，是"主动服务"体验的技术基础
- **Framer Motion**：灵犀气泡的滑入、呼吸、展开动画效果，是"非侵入式"体验的关键

## 实现方案

### 核心架构：感知-预判-服务三层管线

```
用户活动 → [感知层]上下文采集 → [预判层]意图预测+机会检测 → [过滤层]奖励模型过滤 → [服务层]建议生成 → WebSocket推送 → 灵犀气泡展示
```

### 后端核心组件设计

1. **ContextManager**：维护用户当前活动状态、历史交互、偏好画像
2. **IntentPredictor**：调用LLM分析当前上下文，生成候选意图列表
3. **OpportunityDetector**：基于规则引擎+LLM判断是否存在主动服务机会
4. **RewardFilter**：简化版奖励模型，两层过滤降低误报率
5. **SuggestionGenerator**：生成具体的主动服务建议内容
6. **ScenarioHandler**（5个场景各一个）：封装场景特定的感知和预判逻辑

### 前端核心设计

1. **ChatInterface**：模拟元宝对话界面，支持消息收发
2. **LingxiBubble**：灵犀气泡组件，支持滑入动画、展开详情、采纳/忽略
3. **ContextPanel**：侧边栏展示AI实时上下文理解
4. **ScenarioSelector**：场景切换器，支持5大场景演示

### 关键技术决策

- **WebSocket vs HTTP轮询**：选择WebSocket，主动服务需要实时推送，轮询延迟过大且浪费资源
- **规则+LLM双层过滤**：纯LLM误报率高（参考ProActive Agent研究结论），先用规则快速过滤明显无需求场景，再由LLM精判
- **模拟场景 vs 真实集成**：Demo阶段采用模拟用户行为的场景脚本驱动，降低复杂度同时完整展示主动服务体验

### 性能考量

- LLM调用延迟控制：意图预测使用轻量prompt，控制在2-3秒内返回
- 前端动画性能：使用Framer Motion的transform/opacity动画，避免触发重排
- WebSocket连接管理：心跳保活 + 断线重连

## 架构图

```mermaid
graph TB
    subgraph Frontend["前端 (Next.js)"]
        UI[对话界面]
        LB[灵犀气泡系统]
        CP[上下文感知面板]
        SS[场景选择器]
    end

    subgraph Backend["后端 (FastAPI)"]
        WS[WebSocket Hub]
        CM[上下文管理器]
        IP[意图预测器]
        OD[机会检测器]
        RF[奖励过滤器]
        SG[建议生成器]
        SH[场景处理器 x5]
    end

    subgraph External["外部服务"]
        LLM[LLM API<br/>混元/OpenAI]
    end

    UI -->|用户活动事件| WS
    WS --> CM
    CM --> IP
    IP -->|候选意图| OD
    OD -->|机会信号| RF
    RF -->|通过过滤| SG
    SG --> SH
    SH -->|调用| LLM
    LLM -->|返回结果| SG
    SG -->|主动建议| WS
    WS -->|推送| LB
    CM -->|上下文数据| CP
    SS -->|切换场景| SH
```

## 目录结构

```
yuanbao-lingxi/
├── frontend/                          # 前端项目
│   ├── app/
│   │   ├── layout.tsx                 # [NEW] 根布局，全局样式注入
│   │   ├── page.tsx                   # [NEW] 主页面，组合所有模块
│   │   └── globals.css               # [NEW] 全局样式 + Tailwind指令
│   ├── components/
│   │   ├── chat/
│   │   │   ├── ChatInterface.tsx      # [NEW] 对话界面主容器，管理消息流和WebSocket连接
│   │   │   ├── MessageList.tsx        # [NEW] 消息列表，支持流式渲染
│   │   │   ├── MessageBubble.tsx     # [NEW] 单条消息气泡，区分用户/AI消息样式
│   │   │   └── InputBar.tsx           # [NEW] 输入栏，支持文本输入、文件上传、场景感知
│   │   ├── proactive/
│   │   │   ├── LingxiBubble.tsx       # [NEW] 灵犀气泡核心组件，滑入动画+展开详情+采纳/忽略交互
│   │   │   ├── ProactivePanel.tsx     # [NEW] 主动建议面板，管理多个灵犀气泡的排列和优先级
│   │   │   └── SuggestionCard.tsx     # [NEW] 建议卡片，展示具体服务内容（追问、素材、翻译等）
│   │   ├── scenario/
│   │   │   ├── ScenarioSelector.tsx   # [NEW] 场景切换器，5大场景tab切换
│   │   │   └── ScenarioStage.tsx      # [NEW] 场景舞台，根据选中场景渲染对应演示内容
│   │   └── common/
│   │       ├── Header.tsx             # [NEW] 顶部导航栏，展示产品名称和状态
│   │       └── ContextIndicator.tsx   # [NEW] 上下文指示器，显示AI当前感知状态
│   ├── lib/
│   │   ├── api.ts                     # [NEW] API客户端，封装HTTP和WebSocket调用
│   │   ├── types.ts                   # [NEW] 全局TypeScript类型定义
│   │   ├── scenarios.ts              # [NEW] 场景配置数据，定义5大场景的元信息和脚本
│   │   └── store.ts                   # [NEW] Zustand状态管理，全局状态定义
│   ├── package.json                   # [NEW] 依赖配置
│   ├── tsconfig.json                  # [NEW] TypeScript配置
│   ├── tailwind.config.ts             # [NEW] Tailwind主题配置
│   └── next.config.js                 # [NEW] Next.js配置
├── backend/                           # 后端项目
│   ├── main.py                        # [NEW] FastAPI应用入口，CORS配置，路由注册
│   ├── config.py                      # [NEW] 配置管理，LLM API Key、模型选择等
│   ├── api/
│   │   ├── routes.py                  # [NEW] REST API路由，场景列表、历史记录等
│   │   └── websocket.py               # [NEW] WebSocket端点，实时双向通信核心
│   ├── core/
│   │   ├── context_manager.py         # [NEW] 上下文管理器，维护用户活动状态、历史、偏好画像
│   │   ├── intent_predictor.py       # [NEW] 意图预测器，调用LLM分析上下文生成候选意图
│   │   ├── opportunity_detector.py    # [NEW] 机会检测器，规则引擎+LLM判断主动服务机会
│   │   ├── reward_filter.py           # [NEW] 奖励过滤器，两层过滤降低误报率
│   │   └── suggestion_generator.py    # [NEW] 建议生成器，调用LLM生成具体服务建议内容
│   ├── models/
│   │   └── schemas.py                 # [NEW] Pydantic数据模型，请求/响应/WebSocket消息定义
│   ├── prompts/
│   │   └── templates.py               # [NEW] LLM提示词模板，意图预测、机会判断、建议生成
│   ├── scenarios/
│   │   ├── base_scenario.py           # [NEW] 场景基类，定义统一接口
│   │   ├── search_scenario.py         # [NEW] 搜索问答场景-追问预判逻辑
│   │   ├── writing_scenario.py        # [NEW] 写作场景-素材先行逻辑
│   │   ├── translation_scenario.py    # [NEW] 翻译场景-无感翻译逻辑
│   │   ├── document_scenario.py       # [NEW] 文档总结场景-上传即总结逻辑
│   │   └── image_scenario.py          # [NEW] 生图场景-场景感知生图逻辑
│   └── requirements.txt              # [NEW] Python依赖
└── README.md                          # [NEW] 项目说明文档
```

## 实现要点

- **WebSocket消息协议**：定义统一的消息格式 `{type, scenario, payload, timestamp}`，type区分用户活动事件和主动服务推送
- **场景脚本驱动**：每个场景预置模拟用户行为脚本，按时间线触发事件，让Demo可重复演示
- **LLM调用优化**：意图预测prompt精简化，限制max_tokens=200；建议生成支持流式返回
- **灵犀气泡动画**：使用Framer Motion的`AnimatePresence`管理气泡进出，`spring`物理动画提供自然手感
- **错误处理**：LLM调用失败时降级为规则建议，WebSocket断线时展示重连提示

## 设计风格

采用**深色玻璃拟态（Glassmorphism）**风格，灵感来源于元宝APP的科技感视觉语言，融合柔和发光效果与半透明面板。整体氛围营造"AI正在思考"的沉浸感，灵犀气泡以发光浮动卡片形式从侧边滑入，带有呼吸式微光动画。

## 页面规划（3个核心页面/视图）

### 页面1：主演示页

- **顶部导航栏**：左侧产品Logo"元宝灵犀"+ 右侧连接状态指示器（WebSocket在线/离线）
- **场景选择器区**：5个场景tab卡片横向排列（搜索/写作/翻译/文档/生图），选中态带发光边框
- **对话主体区**：中央对话界面，支持消息流式渲染，用户/AI消息气泡样式区分
- **灵犀气泡层**：对话区右侧浮动的主动建议气泡，可展开查看详情，支持采纳/忽略
- **上下文感知面板**：右侧固定面板，实时展示AI感知的用户活动、关注点、预判意图
- **底部输入栏**：输入框 + 文件上传按钮 + 场景感知状态提示

### 页面2：场景详情浮层

- 点击场景卡片展开的全屏模态视图
- 展示该场景的主动服务流程图和设计理念
- 支持直接从说明切换到实时演示

### 页面3：灵犀面板详情

- 上下文感知面板的展开版
- 展示完整的用户画像、历史主动服务记录、偏好学习结果
- 以时间线形式展示AI的"思考过程"

## 布局设计

- 三栏布局：左侧场景导航(200px) + 中央对话区(flex-1) + 右侧上下文面板(320px)
- 响应式：小屏隐藏右栏，灵犀气泡改为底部抽屉式

## Agent Extensions

### Skill

- **多模态内容生成**
- Purpose: 为Demo界面生成演示用的图片素材（如生图场景的示例输出、写作场景的素材配图、文档总结的场景图）
- Expected outcome: 生成5-8张与各场景匹配的高质量演示图片，用于灵犀气泡中的建议卡片展示

- **pptx**
- Purpose: 在开发完成后，生成比赛路演用的PPT演示文稿，包含方案概述、技术架构、场景演示截图、创新亮点
- Expected outcome: 产出一份15-20页的专业比赛演示PPT