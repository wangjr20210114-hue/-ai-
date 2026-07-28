# FLORIS 功能文档

> 产品名：**FLORIS：一只有温度的大橘**
>
> 生产地址：<https://floris.jlutx.com>
>
> 在线验收站：<https://floris.jlutx.com/test-cases/>
>
> 运行平台：腾讯云 EdgeOne Makers
>
> 产品边界：网页端保持个人单所有者演示；微信小程序只使用 `wx.login` 隔离体验数据，不提供账号注册、组织租户或自建用户数据库
>
> 文档原则：根目录 `README.md` 是仓库唯一的功能、环境、部署和测试事实源

本文先说明运行环境，再按“一项功能说明 + 一张建议截图”的方式描述产品。所有“截图位”均是留给维护者的拍摄提示；截图完成后可将图片放进 `docs/images/` 并替换对应提示。

## 1. 环境与运行前提

### 1.1 平台结构

FLORIS 不运行 FastAPI、Uvicorn、WebSocket 服务、SQLite、外置用户数据库、自建对象存储、自建 Cron 或自建模型服务。React/Vite 负责网页界面，Taro/React 负责微信小程序平台适配；13 个 Python Agent 路由承担 LangGraph 对话和业务工具；Node Cloud Functions 承担文件、阅读库、论文、会话索引、微信登录、验收站、健康页、文件重置和定时桥接；EdgeOne Makers 提供 AI Gateway、Agent Runtime、Conversation Store、LangGraph Checkpointer/Store、Pages Blob、Schedule、Trace 和 GitHub Provider 部署。

| 数据或能力 | 事实源 |
| --- | --- |
| 会话列表、标题、消息 | Makers Conversation Store |
| 单会话执行状态 | Makers LangGraph Checkpointer |
| 日程、地图快照、Action、记忆、主动提醒、工作流、偏好 | Makers LangGraph Store |
| PDF、论文、生成图片、阅读库索引、测试证据 | Makers Pages Blob |
| 每日离线检查 | `edgeone.json` 的 Makers Schedule |
| 在线 10 分钟记忆检查 | 页面可见时的前端定时触发 |
| 构建与生产发布 | Makers GitHub Provider |

> 🖼️ 截图位 01：EdgeOne Makers 项目总览，同时露出 Functions、Agents、Schedules 三个页签。

### 1.2 本地环境

建议使用 Node.js 22、Python 3.11+、EdgeOne CLI 1.6.7+。首次拉取后在仓库根目录执行：

```bash
npm ci
npm --prefix frontend ci
npm --prefix miniapp ci
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
edgeone whoami
edgeone makers link
edgeone makers env pull
edgeone makers dev
```

`edgeone makers dev` 的地址同时代理静态前端、Cloud Functions 和 Python Agents，通常是 `http://127.0.0.1:8088/`。不要单独启动旧后端。

> 🖼️ 截图位 02：终端中 `edgeone makers dev` 启动成功并显示本地访问地址。

### 1.3 环境变量

真实值只保存在 Makers 环境变量中，不提交 `.env`。最小可用配置和可选 Provider 如下：

| 级别 | 变量 | 用途 |
| --- | --- | --- |
| 必需 | `AI_GATEWAY_API_KEY`、`AI_GATEWAY_BASE_URL` | Makers AI Gateway |
| 默认即可 | `AI_GATEWAY_MODEL` | 主模型，默认 `@makers/deepseek-v4-flash` |
| 推荐 | `WSA_API_KEY` | 实时网页与新闻富搜索 |
| 推荐 | `TENCENT_MAP_SERVER_KEY`、`VITE_TENCENT_MAP_KEY` | 服务端地点/路线与浏览器地图 |
| 推荐 | `HUNYUAN_IMAGE_API_KEY` | 混元文生图、图生图 |
| 推荐 | `HUNYUAN_VISION_API_KEY` | 搜索图片与参考图的轻量审核；缺省可复用生图 Key |
| 可选降级 | `DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL`、`DEEPSEEK_FAST_MODEL` | AI Gateway 配额或瞬时故障时的文本模型降级；只有语义计划认定为开放式多步推理的正文才使用 `deepseek-v4-pro`，能力路由、固定工具 JSON、地点候选复核、Action 摘要和可选后台判断均使用关闭深度思考的 `deepseek-v4-flash` |
| 可选降级 | `CLOUDFLARE_ACCOUNT_ID`、`CLOUDFLARE_WORKERS_AI_TOKEN` | Workers AI 视觉理解、文生图、图生图降级 |
| 可选降级 | `DASHSCOPE_API_KEY`、`GEMINI_API_KEY` | 视觉理解后备 |
| 可选 Skill | `TENCENT_MEETING_TOKEN` | 腾讯会议个人 AI Skill；未配置时不向模型暴露会议工具 |
| 数据管理 | `DATA_CLEAR_PASSWORD` | 设置页“清空数据库”的服务端校验密码；真实值只保存在 Makers |
| 小程序后端（仅启用小程序时） | `WECHAT_MINIAPP_APP_ID`、`WECHAT_MINIAPP_APP_SECRET` | Preview 的 `/wechat-auth` 用它们交换 `wx.login` 临时 code；网页客户端不读取，AppSecret 只保存在 Makers |
| 小程序后端（仅启用小程序时） | `MINIAPP_SESSION_SECRET` | Preview 后端签发小程序短期会话令牌；网页客户端不需要，应使用独立高熵随机值且只保存在 Makers |
| 性能调节 | `CAPABILITY_PLAN_TIMEOUT_SECONDS` | 搜索/工具语义规划时限 |
| 性能调节 | `RICH_SEARCH_PROVIDER_TIMEOUT_SECONDS` | SearchPro 调用时限 |
| 性能调节 | `RICH_SEARCH_MEDIA_TIMEOUT_SECONDS` | 网页媒体提取时限 |
| 性能调节 | `RICH_SEARCH_VISION_TIMEOUT_SECONDS` | 搜索图片审核时限 |
| 性能调节 | `REFERENCE_VISION_TIMEOUT_SECONDS` | 用户参考图理解时限 |
| 主动服务 | `PROACTIVE_MEMORY_TIMEOUT_SECONDS` | 记忆主动提醒语义判断时限 |

完整变量名、默认模型与默认 URL 以仓库根目录 `.env.example` 为准。`VISION_PROVIDER_ORDER` 与 `IMAGE_PROVIDER_ORDER` 只应用于专用 Preview 的降级取证，生产通常使用代码默认的混元优先顺序。

> 🖼️ 截图位 03：Makers 环境变量列表，只显示变量名和作用域，所有值必须打码。

### 1.4 部署

项目使用 GitHub Provider。推送 `main` 后，EdgeOne 会从 GitHub 构建；不要对该项目执行本地目录直传。

```bash
git push origin main
```

Preview 流程：EdgeOne 控制台 → Makers → 项目 → 构建部署 → 新建部署 → 选择 `main` 和目标提交 → 选择预览环境 → 等待成功 → 从“预览”按钮获取签名链接。Production 只有在自动化和 Preview 人工验收通过后才发布。自定义域名 `floris.jlutx.com` 指向生产 Deployment。

> 🖼️ 截图位 04：成功的 Production Deployment，显示提交 SHA、main 分支和 floris.jlutx.com 域名状态。

### 1.5 微信小程序开发与预览

小程序位于 `miniapp/`，当前开发分支为 `feature/wechat-miniapp`。它不是网页套壳，也不复制 Agent 业务：聊天、搜索、记忆、Skills、日程、地图数据、图片、论文和主动提醒继续请求 `TARO_APP_API_BASE_URL` 所指向的现有 Makers 环境（开发时为该分支 Preview，上线时为小程序自己的稳定 HTTPS 入口）；小程序只负责微信平台适配。跨端共用的会话 ID、SSE、请求载荷、结构化卡和事件协议位于 `packages/floris-contracts/`。

平台复用规则：

| 场景 | 直接复用 |
| --- | --- |
| 登录 | `wx.login`；code 只传 `/wechat-auth`，AppSecret 不进入小程序 |
| HTTPS 与流式输出 | `Taro.request` / `wx.request` 的 `enableChunked` 与 `onChunkReceived` |
| 停止生成 | `RequestTask.abort()` + Makers `/stop`；绝不自动重试模型 |
| 定位与地图 | `wx.getLocation`、原生 `<map>`、marker/polyline；地点与道路仍由现有 Maps Skill 核实 |
| 日期与时间 | 微信原生 `picker`，不自建日历选择器 |
| 图片 | `wx.chooseMedia`、`wx.compressImage`、原生 `swiper` 展示 Makers 图片版本链、`wx.saveImageToPhotosAlbum` |
| PDF | `wx.chooseMessageFile`、Makers Blob、`wx.openDocument` |
| 本地会话缓存 | `wx.setStorageSync`；Makers Conversation/Checkpointer 仍是服务端事实源 |
| Markdown | 成熟 `marked` 解析器 + 小程序原生 `rich-text` |
| 主动提醒 | 页面打开立即刷新、前台每 10 分钟复用 Proactive Agent 检查；处理/稍后/忽略、多步骤工作流与持久偏好继续写入 Makers |

首次配置：

1. 在微信公众平台注册个人小程序，复制 AppID，并在“开发管理 → 开发设置”取得 AppSecret。
2. 在 EdgeOne Makers 的 Preview 环境添加 `WECHAT_MINIAPP_APP_ID`、`WECHAT_MINIAPP_APP_SECRET`、`MINIAPP_SESSION_SECRET`；三者均设为 Secret。
3. 微信公众平台 → 开发管理 → 开发设置 → 服务器域名，把当前 `TARO_APP_API_BASE_URL` 的 HTTPS 主机加入 `request`、`downloadFile` 合法域名；Makers Blob 预签名上传所返回的实际 HTTPS 域名还需加入 `request` 合法域名。开发 Preview 与正式入口域名不同，两者都要分别登记。
4. 复制 `miniapp/project.private.config.example.json` 为 `miniapp/project.private.config.json`，只把其中 AppID 换成真实值。该文件已被 Git 忽略。
5. 执行：

```bash
npm --prefix miniapp ci
npm --prefix miniapp run typecheck
npm --prefix miniapp test
npm --prefix miniapp run build:weapp
npm --prefix miniapp run preflight -- --api <当前 feature/wechat-miniapp Preview 地址>
```

`preflight` 不读取或打印 AppSecret：它只校验本地真实 AppID、构建产物、HTTPS，以及 Preview `/wechat-auth` 是否已经走到微信官方 `jscode2session`。返回“微信登录尚未配置”时，不要继续真机测试，先补齐三项 Makers Secret 并从 `feature/wechat-miniapp` 重新部署 Preview。

6. 微信开发者工具 → 导入项目，选择仓库的 `miniapp/` 目录；`miniprogramRoot` 已指向 `dist/`。先在 Preview 后端验证登录、流式问答、停止生成、位置授权、日程确认和图片保存，再上传体验版。

若开发者工具提示“当前地址不在 request 合法域名列表中”，本地联调可在“详情 → 本地设置”勾选“不校验合法域名、web-view（业务域名）、TLS 版本以及 HTTPS 证书”，它只影响本机模拟器；体验版与正式版仍必须按第 3 步登记服务器域名。Preview 地址会随部署变化，不适合作为长期入口；准备真机验收时应给小程序后端绑定稳定 HTTPS 域名，再同时登记为 `request` 与 `downloadFile` 合法域名。

未配置真实 AppID 与上述三个 Makers Secret 时，代码仍可自动测试和构建，但 `touristappid` 不能完成真实 `wx.login` 闭环。小程序不使用 `web-view`，因此个人主体不受网页套壳能力限制。

微信原生 `openDocument` 负责可靠的 PDF 查看，但它不提供正文抽取 API。小程序论文助读因此复用系统阅读器的复制能力与现有 Reader Agent：用户在原生预览中复制段落，回到助读页粘贴后即可流式翻译、总结、解释、公式分析、术语提取或问答，结果仍持久保存到 Makers 阅读库。这里没有为了“自动抽取”再内置一套 PDF 解析器；网页端已有的完整 PDF.js 助读保持不变。

结构化副作用也不在小程序重写：日程确认卡展开现有 Agent 返回的新增、修改、删除与冲突提醒；腾讯会议卡复用 `update_meeting_action`，通过微信原生日期/时间 `picker` 补齐信息、由 Makers 再校验冲突，最后才允许确认。主动服务页直接呈现现有 Proactive Agent 的待确认/进行中工作流，完成、跳过、失败、重试、补救与取消都调用同一组持久化操作。

## 2. 对话、流式输出与会话恢复

用户可以直接进行问答、写作、翻译、总结和代码生成。回答按 SSE 流式输出，Markdown、表格、代码、公式、行内来源和图片会在对应位置逐步渲染；“猜你想继续问”与正文并行生成。每个对话独立保存，切换对话后后台生成仍可继续；刷新或连接丢失不会偷偷重启旧请求。用户点击“停止生成”后立即结束本轮并恢复输入，只能由用户点击“重试”或发送新消息重新生成。

回答右上角提供纯文字复制和回答图片保存；富文本来源、图片不进入纯文字复制。需要关键条件时，模型可在任何问答场景生成结构化选择、判断、多选、日期或必要填空卡；点击选项后直接把结果交给模型继续思考，不要求用户再次手工发送。非阻断偏好不会强迫必填，而是给出多套方案。

能力规划使用 LangChain 原生 `with_structured_output` 和 Pydantic schema。第一阶段 Flash 只做必要信息预检、完整能力依赖和提示词主题检索；第二阶段 Flash 只接收本轮命中的能力细则并冻结查询、地点、路线顺序及副作用意图。业务执行继续使用 LangGraph `ToolNode` 与 Makers Checkpointer。路线计划会在规划层冻结用户给出的完整有序站点，工具决策层可以改善地点别名和消歧，但不得缩短站点链。工具决策流与最终回答流通过 LangChain tags 区分，只有最终回答进入用户可见的 SSE，因此不会先冒出半句回答又退回“正在处理”。

> 🖼️ 截图位 05：一条正在流式输出的回答，同时显示进度短句、行内来源、图片和“猜你想继续问”。

### 2.1 公共 LangChain 动态链

完整策略仍保存在一套具名提示词注册表中，没有删除功能规则；运行时按语义计划只组合当前阶段需要的片段。片段通过 `identity`、`maps`、`route`、`calendar`、`paper` 等语义名称关联，并在启动时校验每一段都有唯一名称，不再依赖提示词第几行。用户表达的意图只由结构化语义模型判断，业务入口有自动化检查，禁止新增关键词、正则、同义词表或“当前位置”等固定短语分支。

每轮按需经过以下环节：

1. 只读取所有回合都需要的 Skills、搜索/地图设置、预算和安全记忆摘要；日程 Workspace、路线记录和主动服务状态在规划后按能力并行读取。
2. 非思考 Flash 做语义预检：判断是否真的缺少阻断信息、选中一个或多个提示词主题，并保留完整能力依赖。只有它提出阻断卡时，才增加一次独立 Flash 复核，防止把可选偏好误判为必填。
3. 非思考 Flash 只接收命中的能力细则，输出完整 `CapabilityPlan`。普通聊天不会注入地图、日程、搜索、论文等大段规则；跨能力请求可以同时命中多个片段。
4. LangGraph 只暴露计划选中的工具和全局 `ask_user_clarification`。规划器已给出完整参数的当前位置、附近搜索、路线、纯论文检索和富搜索会直接进入工具，不再让模型复述一次固定 JSON；其余参数生成仍使用非思考 Flash。
5. 腾讯地图、SearchPro、混元、arXiv、Makers Store 或腾讯会议 MCP 返回可核验结果。当前位置、纯路线、纯论文和“路线 + 日程”已有确定展示模板，直接本地收尾；其余回答使用 Flash。只有 `needs_deep_reasoning=true` 的开放式正文才切到推理档。
6. “猜你想继续问”、记忆提取和主动机会判断由计划分别开启，使用非思考 Flash 并与正文或彼此并行；澄清、失败、寒暄及无后续价值的回合不会无条件执行这些模块。

必要信息卡是核心对话能力，不属于地图或日程私有逻辑。它覆盖写作、翻译、搜索、附图、文档、生图、地点、路线、日程、会议、论文和普通问答；有限候选优先单选/多选，权限或定位失败时先由浏览器请求真实权限，仍不可用才发大致位置填空卡。卡片提交会继续原任务，不要求用户再次发送。可安全默认或给多套方案的偏好不得阻断回答。

### 2.2 八个 Skills 的实际调用链

| Skill | 语义命中后的 LangChain / Provider 链 | 动态提示词与省略的无用环节 | 主要失败边界 |
| --- | --- | --- | --- |
| 实时搜索 `web-search` | 预检选 `web` → CapabilityPlan 合并一次查询 → LangGraph 直接调用一次 `rich_search` → SearchPro、媒体抽取与可选 HY-Vision 并行 → Flash 综合正文 | 只注入相对时间、来源、媒体和时效证据规则；不注入地图、日程、会议或论文参数规则。同轮重复搜索被执行层去重 | SearchPro 超时会缩小答案；图片失败不阻断文字；需要当天发布时严格按发布日期过滤 |
| 视觉理解 `vision` | 有用户附图时先由配置的多模态 Provider 一次提取视觉事实；搜索图片只在搜索已命中且图片数量大于 0 时并发审核 | 没有附图且没有搜索媒体时不调用视觉模型，也不注入附图上下文；图片审核不使用主推理模型 | Provider 都失败时明确无法识别，不假装看见；精确图像事实只来自本轮结果 |
| 图片工坊 `image-studio` | CapabilityPlan 选生图 → 原创图直接进入 `propose_image`；需外观准确的现实主体才先富搜索参考图 → 混元生成，必要时按配置降级 → Blob 保存版本 | 只注入生图、参考图和正文去重规则；固定工具参数用 Flash，生成本身不经过文本 Pro；已有参考图时不重复搜索 | 无可用生图 Provider 时失败；历史修改必须绑定已有 Action 版本；正文不重复输出图片 URL |
| 地图 `maps` | 预检选当前位置/地点/附近/路线之一 → CapabilityPlan 冻结地点与原顺序 → 当前位置、附近和路线参数可直接进工具 → 地点搜索与各站核实并行 → 腾讯路线 → 结构化地图 Action | 只注入定位、地点、地图 Action 或路线中实际需要的片段。唯一地点直接采用；多候选只在均衡/完整档增加一次非思考 Flash 证据复核；快速档采用 Provider 首选 | 浏览器无定位先请求权限，拒绝或失败后发位置卡；地点无证据发填空卡；道路路线只用腾讯，58 秒硬截止，不用 OSM 路径 |
| 日程 `calendar` | 规划后才读取 Workspace → 查询/汇总直接回答；新增、修改、删除由 Flash 生成 `propose_calendar_changes` → 服务端校验 ID、时间、地点、冲突和通勤 → 用户确认后写入 | 只在日程命中时注入当前日程和变更规则。路线联动先复用腾讯核实站点，再生成一张包含多项变更的日程提案；不会为每个地点生成一张卡，也不会重新搜地点 | 缺少唯一副作用对象时发最小卡；过去日程不可修改；确认前不写入；地图 Action 与日程 Action 相互独立 |
| 主动式 Agent `proactive-agent` | 用户明确要持续工作流时进入 `propose_workflow`；后台日程、天气、路线、文件、图片和记忆信号先确定性收集，再只对待判断候选调用非思考 Flash，最后经过冷却、免打扰、上限与去重 | 普通聊天不会注入工作流规则或运行主动判断；只有 CapabilityPlan 的机会标记、真实上传/生成事件、页面检查或 Schedule 到期才运行对应语义模块 | 浏览器关闭时平台 Schedule 最小粒度为每天；缺少可靠证据或置信度不足时不通知；不会把精确位置或敏感记忆写入提醒 |
| 论文助读 `paper-reading` | 纯论文检索由规划器参数直接调用一次 arXiv 并本地生成固定完成说明；跨来源综述先富搜索，再由 Flash 把准确标题交给 arXiv 补 PDF；进入 Reader 后按当前按钮选择单一动作流式处理 | 纯论文检索不再无条件先跑富搜索。Reader 每次只注入当前动作提示：翻译、总结、解释、公式、全文翻译和术语使用非思考 Flash；全文分析和论文问答才启用推理档 | 找不到论文不拿无关结果凑数；Reader 只依据当前 PDF 文本；长文有输入上限，Provider 失败时保留 SSE 心跳并返回可读错误 |
| 腾讯会议 `tencent-meeting` | 只有 Token 存活且日程也开启时才暴露工具 → Flash 生成可编辑会议 Action → 用户补齐/确认 → 腾讯会议官方 MCP 调用一次 → 成功后关联日程 | 未配置时工具 schema 和会议提示词都不进入模型；缺时间仍先给一张可编辑卡，不做多轮普通文字追问 | Token、日程依赖或 MCP 失败会明确终止；结果未知进入核对状态，不盲目重试创建 |

## 3. 自动记忆

记忆由后台自动提取，不在前端向用户展示，也不要求逐条确认。系统只保存用户明确表达的稳定偏好、长期目标和项目背景，并二次过滤联系方式、凭证、证件、精确地址、财务、医疗等敏感信息；低置信度、一次性事实、过期或长期未使用内容会被清理。安全记忆会进入后续对话的模型上下文、搜索规划和主动提醒判断，从而形成跨会话连续体验。

> 🖼️ 截图位 06：两个不同会话中，第二个会话自然复用了第一个会话明确表达的非敏感偏好。

## 4. 主动式服务

主动服务覆盖搜索问答、写作、翻译、生图、文档和日程场景。回答完成、文件上传、图片生成、日程变化、网页打开以及在线每 10 分钟检查都可能产生业务信号；独立语义模型只在确有价值时选出最多一个机会，再经过隐私、置信度、冷却、过期、免打扰和每日上限规则，写入持久 Event、Run、Notification。每日 Makers Schedule 在浏览器关闭时继续扫描日程、天气、路线与工作流。

真实提醒在 Header 中以自然短句淡入淡出轮播，并同步出现在左侧简洁提醒面板，用户可以采纳、稍后一小时或忽略。提醒不会写入空白新对话，因此不会和用户首条消息竞态。提醒窗口以记忆为主、用户操作为辅，最多显示设置的窗口上限；日程或路线更新后旧提醒会被淘汰。

当没有真实提醒时，Header 才显示用户在“设置 → 主动式服务”中维护的诗意短句。最多 5 条、每条最多 80 字，默认含“鱼儿水中游，永远不会回首～”等三条；这些短句仅是低权重界面兜底，不创建假通知、不进入提醒窗口。短句和真实提醒偏好都保存在 Makers LangGraph Store，刷新和跨主机继续有效；一旦出现真实提醒，短句立即让位。

> 🖼️ 截图位 07：设置中编辑 3–5 条诗意短句，Header 正在轮播其中一条。

> 🖼️ 截图位 08：创建临近日程后，Header 的诗意短句已被真实日程提醒替换，左侧面板显示处理按钮。

## 5. 实时图文搜索

搜索前保留独立 LLM 语义规划，它结合当前问题和已过滤的非敏感记忆，决定是否联网、合并查询和是否需要图片，不使用关键词硬编码替代规划。一轮对话最多执行一次 `rich_search`；同轮重复调用复用同一任务，跨轮按时效 TTL 使用 LangGraph Store 缓存。默认向答案提供 8 条去重网页结果，并从最多 8 张候选图中完成视觉审核；用户可在设置中选择 4/8/12/18 条网页结果、0/1/2/4/8 张图片以及是否并行查图。图片设置值同时是单轮视觉审核与最终素材数量上限。

SearchPro 事实搜索只调用一次，网页媒体并发抽取，候选图并发做轻量相关性、广告、二维码、Logo、UI 和占位图审核。审核通过的真实 URL 交给主模型直接用标准 Markdown 排版；来源以对应事实旁的可点击标题链接出现，不在回答底部重复堆一份来源目录。Provider 失败或超时只影响图片，不阻断文字回答。

> 🖼️ 截图位 09：询问“最近 AI 有什么新进展”，回答中图片位于相关段落、来源标题可单击打开。

## 6. 视觉理解与图片工坊

用户可以上传图片让模型理解，也可以文生图、参考图生图和基于已有版本继续修改。混元为主 Provider，Cloudflare Workers AI 可作为视觉和生图降级；视觉审核只判断相关性与明显广告等必要条件，并受硬超时约束。生成结果保存到 Makers Blob，图片工坊支持版本轮播、统一切换按钮、单图下载、批量 ZIP 下载和“基于此图修改”。绘制期间使用稳定的全宽画布和阶段提示，避免输入区尺寸跳动。

搜索回答中的图片排版由答案模型通过标准 Markdown 决定；前端只负责安全渲染、加载状态和持久恢复，不使用 `[[YUANBAO_MEDIA...]]` 一类占位符猜位置。

> 🖼️ 截图位 10：一组橘猫图片的生成过程与完成后的版本轮播、下载、继续修改入口。

## 7. 真实地点、定位、地图与路线

地点推荐先查询短期 Makers Store 缓存，再由腾讯位置服务核实真实名称、地址、place_id 和坐标；腾讯搜索不可用或没有可信匹配时，OpenStreetMap 只作为短期 POI 搜索兜底。有部分地点核实成功时只显示成功项，全部失败时才拒绝生成地图。普通地点推荐只展示点位，不把地点强行连线；旅游规划、日程规划或用户明确询问两地路线时才绘制道路路径。所有道路匹配和路线计算都只使用腾讯路线服务，不会静默切换到公共 OSRM；失败时如实提示重试，并返回已经核实到的地点边界。

“显示我的位置”先检查浏览器权限，已授权时可复用 10 分钟内的内存位置；用户只给目的地并表达“我想去/怎么去”时，路线链直接把它作为隐式起点，不再重复询问。WGS84 定位先经腾讯坐标转换后参与道路匹配；精确坐标不进入模型提示词、回答、日程、提醒或长期记忆。地图容器在模型思考时保持持久，不因回答状态反复刷新。地点错字先采用腾讯地点搜索和关键词输入提示的候选证据。地点执行固定三级决策：唯一候选直接继续；多个腾讯建议只在一次按需注入候选证据、使用 Flash 且关闭深度思考的结构化复核判定实际目的地近乎唯一时采用其中一个真实 `place_id`，否则保留腾讯相对顺序，并把请求城市或候选一致城市中的高概率项移到主动式单选卡前面；无候选让用户填写。快速地图模式会跳过这次额外复核并采用 Provider 首选。这里不使用本地距离阈值、关键词、别名或编辑距离，未经用户选择的纠错结果也不会跨对话复用；直接采用仍不会绕过最终日程确认。

多站路线从第一个起点到最后一个终点严格保留原始顺序；“某地点附近的某品牌”由结构化字段分别表达品牌与参照点，不依赖地点名称或中文关键词硬编码。路线支持腾讯驾车、公交、步行和骑行；用户明确方式优先，未明确时采用设置或已学习的稳定习惯。默认路线策略为“省时优先、时间相近选省钱”：腾讯先按实时 ETA 返回候选，项目只在设置的分钟容差内比较可核验费用；费用未知时回退最快，明确最省钱的驾车请求会使用腾讯 `LEAST_FEE`。只有用户实际点击路线 Action 后才按 Action 去重统计其明确选择；至少三次且占比达到 60% 才影响默认，设置中可关闭。聊天路线会生成一个独立的“在地图中查看”动作，只有用户点击才切换右侧地图并按对应方式绘制；路线与日程保持独立，只有用户明确要求或带未来时刻的多站行程才另行生成待确认日程。近期路线按 `route_plan_id` 有界保留，日程工具按来源 ID 和完整站点顺序补齐模型漏传的地点身份；另一个对话的新路线不会立即让当前提案失效，浏览器临时起点也不会把地址或坐标写进持久路线计划。同一组地点、方式、策略与时间容差共享 30 分钟缓存，缓存不会跨条件复用。快速/均衡/完整档可调整候选数、路线站点上限和地点搜索等待时间，默认目标 30 秒，单次完整路线硬截止为 58 秒；调用链与失败边界以本功能文档第 2.2、7、8 节为准。

> 🖼️ 截图位 11：推荐三里屯附近餐馆，只显示真实点位且没有无意义连线；“我的位置”同时可见。

## 8. 日程管理与冲突闭环

日程可以从右侧日历直接新增、就地编辑、删除，也可以完全通过自然语言新增、改时间、改描述、改地点和删除。模型先生成冻结的 Calendar Action，用户确认后服务端按当前 `schedule_id` 执行并使用幂等键阻止重复写入；删除不会把剩余日程重复复制。今日以前的日程在界面和模型工具层都禁止修改。

现实地点必须来自地点库，Zoom、腾讯会议、Teams 等线上地点可独立保存。系统在确认卡生成前检查日程重叠，并对受影响且带核实地点的相邻日程检查腾讯道路时间与用户设置的换场缓冲；时间不合理、通勤不足或路线暂时无法核实时给出可理解警告。确认修改后再次重算主动提醒，旧提醒不再保留。移动已有日程但未要求改变时长时会保留原时长，也支持明确清空地点。用户先规划路线、后说“写入日程”时，系统复用上一轮已核实地点，并通过日期/时间选择卡收集真正必要的信息；路线生成地图动作并不等于写入日程，日程确认也不会擅自激活其他地图推荐。

> 🖼️ 截图位 12：右侧未来日历的行内编辑框，以及一张含时间冲突与通勤提醒的确认卡。

## 9. 腾讯会议

个人用户从腾讯会议官方 AI Skill 页面取得 `TENCENT_MEETING_TOKEN`，保存到 Makers 环境变量即可，不需要企业 SecretId、SecretKey、AppId、SDK ID 或回调服务。只有 Token 存活且“腾讯会议”与“日程管理”Skill 都开启时，模型才获得会议工具。

会议缺少必要时间时使用同一张可编辑卡收集主题、开始和结束时间；卡片可快捷填充，也能逐条处理日程冲突。用户最终确认后只调用一次官方 MCP，成功返回会议号和入会链接，并自动写入一条关联 `meeting_id` 的日程。未知结果进入人工核对，不会盲目重试创建。

> 🖼️ 截图位 13：腾讯会议确认卡、创建成功的会议号，以及右侧日历中自动新增的同主题日程。

## 10. PDF、论文与“我的阅读”

用户上传 PDF 后，文件直传 Makers Blob；论文会自动加入“我的阅读”并打开兼容模式助读器，普通 PDF 打开阅读器。系统也能检索 arXiv/公开论文并下载 PDF。大文件使用分片读取，避免 Cloud Function 响应大小限制。

论文助读保留全文分析、问答、选词翻译和总结，打开时默认使用完整视口，也可用工具栏恢复窗口布局。翻译、总结、全文分析和问答都由 Reader Agent 以 SSE 流式输出 GitHub Flavored Markdown；本轮最新结果始终位于历史记录上方。翻译与分析历史写回阅读项目，关闭、刷新或换主机后仍可恢复。外文文档上传成功后，即使用户还没提问，主动服务也可在有价值时建议当前界面语言版本；采纳后从原 Makers Blob 重新载入，不搜索同名网页。

> 🖼️ 截图位 14：论文兼容阅读器，顶部“论文助读”、全文分析、全屏按钮和右侧按时间排列的翻译记录。

## 11. Skills 广场与设置

Skills 广场把通用问答、实时搜索、视觉理解、图片工坊、真实地点与地图、日程、主动式 Agent、论文助读和腾讯会议组织为能力开关。现有功能默认开启，核心问答不可关闭；硬依赖会自动补齐，推荐依赖会自然引导。例如只开日程而关地图时，无地点日程仍可使用，涉及真实地点时会建议开启地图而不是编造地址。

设置只展示已启用 Skill 的相关配置，包括五种语言、搜索结果/图片数量、阅读库整理、主动服务开关、关注范围、免打扰、立即检查和最多 5 条诗意短句。固定标签、Toast 和模型回答同时支持简体中文、繁体中文、English、可爱喵喵语、冷酷喵喵语；Toast 不直接展示 Provider、HTTP 或存储层原始错误。

设置底部的“清空数据库”需要输入 `DATA_CLEAR_PASSWORD`，密码只在服务端校验，不进入前端包或 GitHub。确认后会物理删除 Makers Conversation、Checkpointer、LangGraph 业务状态与 Pages Blob 中的文件、验收记录和定时锁，同时清理浏览器缓存；随后只重建 Skills 开关，日程、记忆、提醒、对话、文件、搜索偏好和其他记录都不会保留。浅色主题为橙色暖调，深色主题为紫色夜空风格，主题切换控制在数百毫秒内。

右上角 GitHub 图标单击打开本功能文档，鼠标悬浮提示“功能文档”。

> 🖼️ 截图位 15：Skills 广场与设置并排展示，包含语言、搜索、诗意短句和受密码保护的数据清空入口；右上角 GitHub 图标可见。

## 12. 视觉风格与交互

浅色对话背景是与 Floris Logo 同风格的橘猫在草地与人撒娇，深色背景是橘猫在房顶看星空；背景覆盖完整中间栏，包括消息和发送区，但不覆盖左右工作区。按钮、卡片、弹窗、抽屉、消息气泡、主题切换、图片切换和论文助读操作都使用短促的 Apple 风格缓动，并遵循 `prefers-reduced-motion`。图形按钮均提供悬浮说明。

回答列表采用稳定滚动锚点：用户主动向上浏览或选择文字时不会被自动滚动抢走位置；回答正文目前通过右上角复制按钮复制纯文字，不依赖不稳定的气泡内划词复制。

> 🖼️ 截图位 16：同一对话的浅色与深色主题对比，显示完整中间栏背景和 Floris 头像。

## 13. 安全副作用与故障处理

地图展示、日程变更、腾讯会议和生图使用服务端冻结 Action：包含版本、SHA-256 快照、幂等键、执行租约和 Provider 账本。用户确认前不发生高风险副作用；确认时只提交 Action ID 与版本，不由浏览器重传整份参数。超时导致结果未知时标为 `reconciliation_required`，避免重复创建。

网络断开时，本轮在 20 秒无进展后进入明确恢复/失败状态；用户主动停止拥有最高优先级，网络恢复只允许补发取消指令，绝不自动重新生成。模型主链可在 Makers Gateway 配额或瞬时故障时使用配置的 DeepSeek 降级；搜索图片、视觉、生图和地图的降级互相隔离，不把单个 Provider 故障扩大为整轮失败。

> 🖼️ 截图位 17：断网或生成失败后的终止卡片，显示“重试”按钮且输入框已经恢复可用。

## 14. 验收测试站

`/test-cases/` 是随主应用部署的静态测试站。每个 Case 包含真实入口、逐步点击位置、输入数据、每一步预期、最终结果、安全边界和清理步骤；测试人员可以记录通过、失败、阻塞、不适用、备注和编辑主机。图片/视频证据上传到 Makers Blob，状态、备注、最后编辑主机和时间跨刷新、跨主机共享。产品按个人单编辑者设计，最后一次保存生效，不实现多人同时编辑锁。

完整 Makers 本地环境访问 `http://127.0.0.1:8088/test-cases/`。只检查静态布局时执行 `npm --prefix frontend run dev`，再访问 `http://127.0.0.1:5173/test-cases/index.html`；此模式仅使用当前浏览器 localStorage，不能验证跨主机持久化和证据上传。

> 🖼️ 截图位 18：测试站表格的一条完整 Case，展开操作步骤、预期结果、备注、证据与最后编辑记录。

## 15. 质量检查与发布门槛

提交前在仓库根目录执行：

```bash
. .venv/bin/activate
python -m compileall -q agents
python -m unittest discover -s agents/_tests -v
npm test
npm --prefix frontend test -- --run
npm --prefix frontend run lint
npm --prefix frontend run build -- --mode edgeone
git diff --check
```

还应执行严格 TypeScript 未使用检查：

```bash
cd frontend
npx tsc -p tsconfig.app.json --noEmit --noUnusedLocals --noUnusedParameters
```

Preview 必须确认首页、`/system`、`/test-cases/`、`/messages`、`/chat`、`/workspace`、文件上传和至少一轮真实对话均可用。生产环境只做非破坏冒烟，不进行无效 Key、网络阻断、付费批量调用或真实会议故障注入。

> 🖼️ 截图位 19：终端中 Python、Node、前端测试和生产构建全部通过。

## 16. 当前明确不提供的能力

- 注册、登录、JWT、多用户、租户隔离和团队协同。
- FastAPI、Uvicorn、WebSocket、SQLite、Neon 或外部业务数据库。
- 一次性旧 SQLite 数据导入入口；当前版本从干净的 Makers 数据代际运行。
- 本地 `tmeet` CLI、腾讯会议企业五项凭据或自建会议桥。
- 用户可见的记忆列表和逐条记忆确认。
- 浏览器关闭状态下每 10 分钟运行；Makers Schedule 的平台最小间隔为每天，在线页面负责 10 分钟补充检查。

这些边界是当前个人比赛演示的有意取舍，不是隐藏在旧代码中的待恢复功能。
