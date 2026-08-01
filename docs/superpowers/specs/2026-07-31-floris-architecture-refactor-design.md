# Floris 渐进式架构重构设计

## 1. 背景与目标

当前 `dev` 已完成 Makers 多租户、微信优先登录、标准 Skill 清单、证据缓存、
结构化进度、搜索媒体后台化和 `source_id` 来源绑定。新模块已经采用部分
MVC，但核心链路仍处在迁移状态：

- `agents/chat/index.py` 同时承担协议适配、用例编排、SSE、状态读取、Graph
  执行、媒体持久化和后台任务；
- `agents/chat/_ui_tools.py` 集中实现所有内置 Skill 工具，系统 Skill 虽有
  `SKILL.md + floris.json`，运行时仍主要依赖中央工具工厂；
- `agents/_shared` 混合领域策略、Makers Repository、Provider 客户端与副作用；
- Node 与 Python 分别维护会员等级、Guest 权限和限额；
- React 只有 Skills 初步形成 feature MVC，聊天、日程、地图、论文和设置仍
  有大型组件、统一 API 文件和全局 CSS；
- 新回答已使用 `source_id` 绑定媒体，但前端仍有旧
  `[[YUANBAO_MEDIA]]` 插槽兼容代码。

本设计采用渐进式替换，不推倒重写。每一阶段都必须保持可部署、可回滚，
并以自动化测试证明行为没有退化。

## 2. 全局不可回退约束

1. `main` 与 `origin/main` 始终保持
   `72be68b2615e7dc23abfbeadca9ce204e3a3c84c`；所有改动只进入 `dev`。
2. Maker 部署只允许目标项目 `floris-dev`
  （项目 ID `makers-0kgcojx0gjiy`），不得读取、改配或部署
   `ai-active-agent-floris`。
3. 继续复用 Makers 的签名会话、Store、Checkpointer、Blob、定时任务和
   Trace 能力；不自建通用会话、对象存储、队列或定时调度服务。
4. 多用户是唯一身份模式。Guest 只能使用 `core` 与 `proactive-agent`；
   浏览器不能自报租户、用户、角色或会员等级。
5. 缓存只保存结构化证据和业务中间结果，禁止保存最终回答、模型推理或
   人格化措辞。
6. 不展示模型隐藏思维。用户只看到 Controller 产生的固定枚举进度。
7. 搜索媒体必须经过视觉审核，并同时满足 `source_id`、`source_url` 和
   正文精确来源引用匹配；任一条件不满足即不插入。
8. 新旧消息都不得使用媒体占位符决定图片位置。无法确定性绑定的历史图片
   不再显示。
9. 用户 Skill 在审核后台完成前只能上传为 `pending_review`，不能安装、
   导入或执行任意代码。
10. 支付仍只保留 Provider 与权益接口，不实现真实扣款。

## 3. 方案选择

### 3.1 方案 A：大爆炸重写

一次性替换 Chat、Skills、共享层和前端。最终目录整齐，但无法把搜索、
路线、日程、论文、生图和主动式 Agent 的回归定位到单一变更，线上风险
不可接受，因此不采用。

### 3.2 方案 B：渐进式绞杀迁移

保留现有路由和外部协议，先为旧实现建立端口和契约测试，再逐个把职责移到
新的 Application、Domain、Infrastructure 和 Presenter 单元。每迁移一个
用例就删除对应旧分支，确保系统始终只有一个生效实现。这是采用方案。

### 3.3 方案 C：只拆文件

把大文件机械切小，但继续共享闭包状态、中央工具表和双份权益常量。文件会
变短，依赖和运行时耦合不变，不能实现真正 Skill，也不能消除重复模型决策，
因此不采用。

## 4. 目标架构

```text
agents/
  chat/index.py                         # 薄 EdgeOne Route Adapter
  workspace/index.py                    # 薄 EdgeOne Route Adapter
  proactive/index.py                    # 薄 EdgeOne Route Adapter
  <other-route>/index.py                # 薄 EdgeOne Route Adapter

  _application/
    chat/turn_controller.py             # ChatTurnController
    chat/turn_context.py                # 本轮上下文装配
    search/search_use_case.py           # SearchUseCase
    workspace/workspace_controller.py
    proactive/proactive_controller.py

  _domain/
    identity/
    entitlements/
    search/
      evidence.py
      media_binding.py
      policy.py
    skills/
      manifest.py
      dependency_graph.py
      runtime_policy.py
    workspace/
    proactive/

  _infrastructure/
    makers/
      conversation_repository.py
      evidence_repository.py
      identity_adapter.py
    providers/
      searchpro.py
      tencent_location.py
      vision.py
      image_generation.py
      academic_search.py

  _presenters/
    chat_stream.py                      # StreamPresenter
    json_views.py

  _skill_adapters/
    core/
    web_search/
    maps/
    calendar/
    image_studio/
    vision/
    paper_reading/
    proactive_agent/
    tencent_meeting/

  skill_packages/                       # 只存标准包和静态资源
    <skill-id>/SKILL.md
    <skill-id>/floris.json

contracts/
  entitlements.v1.json                  # Node/Python 唯一权益数据源

frontend/src/
  app/                                  # Shell、Provider、组合 reducer
  features/
    chat/
    search/
    calendar/
    maps/
    papers/
    settings/
    skills/
  shared/                               # 无业务语义的 UI/transport 基础件
  styles/tokens.css
```

MVC 只描述接口呈现边界：

- Model：领域实体、值对象、策略和状态转换，不依赖 HTTP、React 或 Provider；
- Controller：鉴权后的用例编排，不直接拼 JSON、SSE 或 JSX；
- View/Presenter：把 Controller 结果投影为 JSON、SSE 或 React；
- Infrastructure：实现 Controller 使用的 Makers/Provider Ports。

后端内部同时采用 Ports and Adapters，避免把 Provider 或 Makers 细节塞进
Model。

## 5. 搜索与 Chat 数据流

### 5.1 当前重复决策

当前结构化规划先判断 `needs_web_search`，随后 LangGraph 中的工具绑定模型
仍可能再次决定是否调用 `rich_search`。即使 Graph 有强制与去重保护，这仍
增加一次模型工具决策、控制分支和首字等待。

### 5.2 目标数据流

```text
HTTP request
  -> Chat route adapter
  -> ChatTurnController
      -> authenticate and assemble turn context in parallel
      -> CapabilityPlan (one structured model decision)
      -> deterministic policy validation
      -> SearchUseCase.execute() when plan requires web evidence
          -> evidence cache
          -> SearchPro once on miss
          -> return SearchEvidence immediately
          -> schedule media extraction/review in background
      -> Answer Graph receives evidence as input
          -> rich_search is not present in its tool set for this turn
      -> StreamPresenter emits fixed progress, answer tokens and actions
      -> reviewed media arrives later through search_media
```

`CapabilityPlan` 仍由模型生成，但必须经过固定 schema、Skill 权限、会员权益、
日期约束和最大预算校验。模型只表达意图，Controller 决定是否允许执行。

### 5.3 SearchUseCase 接口

```python
@dataclass(frozen=True)
class SearchRequest:
    tenant_id: str
    user_id: str
    conversation_id: str
    query: str
    image_query: str
    depth: str
    result_limit: int
    image_limit: int
    target_date: str
    strict_date: bool
    force_refresh: bool
    media_mode: Literal["disabled", "progressive", "blocking"]

@dataclass(frozen=True)
class SearchExecution:
    evidence: SearchEvidence
    media_tasks: tuple[Awaitable[ReviewedMediaBatch], ...]
    cache_hit: bool
    coalesced: bool

class SearchUseCase:
    async def execute(self, request: SearchRequest) -> SearchExecution: ...
```

`blocking` 只用于审核图片是后续 Provider 输入的场景，例如现实对象参考图
生图。普通问答必须使用 `progressive`。

### 5.4 网络和请求合并

- SearchPro、视觉和网页读取统一经 Provider Port；
- 使用共享异步 HTTP Client、连接池和统一总 deadline；
- 进程内 single-flight 保留为快速路径；
- 跨实例请求合并优先使用 Makers 提供的条件写入、幂等键或短租约；
- 如果平台不提供满足语义的原子操作，允许重复 Provider 读取，但禁止为此
  自建分布式锁服务；
- 用户明确“重新搜索/刷新”时绕过证据缓存，但仍执行同一来源校验。

## 6. 媒体绑定：完全取消占位符

### 6.1 后端来源身份

SearchPro 结果规范化时由程序生成稳定来源 ID：

```text
source-1 -> canonical source URL
source-2 -> canonical source URL
```

网页图片候选始终携带抓取页面的 `source_url`。审核完成后，后端只允许用
规范化 URL 在本轮来源表中查找 `source_id`，不能让模型提供或修改
`source_id`。

### 6.2 前端插入规则

前端解析 Markdown AST，并为每个正文段落提取真实链接。只有段落包含
`source_id` 对应来源的精确 URL 时，才在该段落后渲染对应
`SourceBoundMedia` React 节点。

实现不得：

- 查找或替换 `[[YUANBAO_MEDIA]]`；
- 使用媒体数组下标决定位置；
- 使用标题、关键词、段落语义相似度或模型解释猜位置；
- 接受媒体 `source_url` 与来源表 URL 不一致；
- 把未审核 `preview_media` 插入正文；
- 信任回答模型直接生成的搜索图片 Markdown。

历史消息读取时先删除所有旧媒体插槽文本，再执行相同的 AST 来源绑定。
历史媒体缺少有效 `source_id` 时不显示。生成图片和用户上传图片继续通过
结构化 Workspace Action/专用组件呈现，不经过搜索媒体绑定。

### 6.3 SSE 合并

`search_media` 事件包含 `run_id`、`conversation_id`、完整来源身份和审核
结果。前端只把它合并到同一运行中的 assistant message。迟到事件不能修改
其他会话、其他 run 或已被新一轮覆盖的消息。

## 7. 真正的系统 Skill Runtime

### 7.1 标准包是唯一清单

每个系统 Skill 继续使用 `SKILL.md + floris.json`。`floris.json` 声明：

- 工具名与 capability；
- `requires`、`recommends` 和会员门槛；
- Makers/Provider 权限；
- Component Actions；
- 可信 Adapter 入口。

中央 `build_production_tools()` 不再实现或枚举业务工具。所有内置工具必须
由其所属系统 Skill Adapter 构建。

### 7.2 Adapter 结构

```python
def build_tools(context: SkillRuntimeContext) -> list[StructuredTool]:
    ...
```

`SkillRuntimeContext` 只暴露清单声明且 Controller 授权的 Ports。Adapter
不能读取原始 HTTP context、任意环境变量或未声明 Makers handle。

迁移顺序：

1. `web-search`，用于证明 SearchUseCase 与媒体契约；
2. `maps` 与 `calendar`，用于证明跨 Skill 依赖和 Workspace Action；
3. `image-studio` 与 `vision`；
4. `paper-reading` 与 `core` 的论文检索；
5. `proactive-agent`；
6. `tencent-meeting` 外部连接器。

每迁移一个 Skill：

- manifest 增加可信 Adapter；
- 中央工具表删除对应定义；
- Registry 测试证明工具只能从 Adapter 出现一次；
- 未安装、未授权或依赖不满足时 Adapter 不加载；
- 工具描述、参数 schema 和现有行为保持一致。

### 7.3 用户 Skill

本轮只完善标准、下载、依赖图、Component API 和审核前隔离。不得实现未经
审核的用户代码加载器。未来审核后台必须产出签名、校验和、运行时版本和
撤回状态，才允许进入受限 Adapter Runtime。

## 8. Domain 与 Infrastructure 拆分

`_shared` 按职责逐步清空：

- 纯规则移入 `_domain`；
- 用例编排移入 `_application`；
- Makers Store/Checkpointer/Blob 操作移入 `_infrastructure/makers`；
- SearchPro、腾讯地图、视觉、生图和论文 API 移入
  `_infrastructure/providers`；
- JSON/SSE 格式化移入 `_presenters`。

迁移期间旧 import 可通过短期 re-export 保持兼容，但每个 re-export 必须
标明删除阶段；最终验收时不保留 `_shared` 业务实现。`_shared` 只允许保留
真正跨领域、无平台语义的基础类型或被完全删除。

依赖方向固定为：

```text
route -> application -> domain
application -> ports <- infrastructure
application -> presenter
skill adapter -> declared ports/component API
```

Domain 禁止 import `ctx`、HTTP Response、LangGraph Store、Blob、urllib 或
React 概念。

## 9. 统一权益 Contract

新增 `contracts/entitlements.v1.json`，作为以下数据的唯一来源：

- `guest/free/plus/pro` 顺序；
- 每级 token、并发、搜索深度、用户 Skill 上传限额；
- Guest 固定 Skill；
- 支付是否可用；
- 可安装社区 Skill、可上传 Skill 等公开 capability。

Node 与 Python 分别实现小型 loader 和语言内校验函数，但不得再硬编码两份
限额表。Contract 含显式 `schema_version`，未知版本部署时失败关闭。

契约测试必须对同一组身份样例同时执行 Node 与 Python，比较：

- 规范化会员等级；
- `planAllows`；
- Guest Skill 访问；
- 每级公开 limits；
- 登录与会员不足错误码。

会员账本和 OAuth 身份继续放在 Neon/Makers 友好数据库边界，浏览器只读取
服务端投影。

## 10. 前端 Feature MVC

保留 React、现有 reducer 和 TDesign，不引入新的全局状态框架。按业务垂直
切分：

```text
features/<domain>/
  model.ts
  controller.ts or use<Domain>Controller.ts
  client.ts
  components/
  styles.css
  *.test.ts(x)
```

迁移规则：

- View 不直接调用 `services/api.ts`；
- feature client 只负责 transport 和数据解码；
- controller 负责异步状态、命令和错误映射；
- model 负责纯状态转换；
- App 只组合 feature，不保存领域细节；
- `services/api.ts` 最终拆为各 feature client；
- `types/index.ts` 的领域类型移到对应 feature，仅共享协议类型留在
  `shared/contracts`；
- `MessageBubble` 拆为文本、搜索、路线、日程、会议、生图和澄清渲染器；
- `useSSEChat` 拆为 transport、run reducer、conversation cache 和
  workspace event bridge；
- 设置、日历/地图、论文阅读器分别拥有 Controller。

## 11. CSS 与测试拆分

### 11.1 CSS

`index.css` 最终只保留 tokens、reset、应用 Shell 和全局可访问性规则。
聊天、Markdown、搜索媒体、Skills、地图、日历、论文、设置和 onboarding
样式随 feature 存放并由 feature 入口导入。

拆分不得改变现有 className、响应式断点或视觉行为；每个阶段使用线上关键
页面截图和 DOM 验收。

### 11.2 测试

`agents/_tests/test_workspace.py` 按现有测试所属领域迁移到：

```text
agents/_tests/chat/
agents/_tests/search/
agents/_tests/maps/
agents/_tests/calendar/
agents/_tests/papers/
agents/_tests/images/
agents/_tests/skills/
agents/_tests/proactive/
```

测试拆分先做纯移动并验证总测试数不减少，再随生产代码迁移调整 import。
跨领域流程保留在少量 acceptance/regression 文件中，不能把所有用例重新
集中到另一个大文件。

## 12. 错误处理与可观测性

- Controller 把错误分类为认证、权限、校验、Provider、配额、超时、取消和
  内部错误；
- Presenter 只输出稳定错误码和安全文案，Provider 原始错误不进入用户界面；
- 每轮记录 `planning/search/answer/media/persist` 阶段耗时；
- 搜索记录 cache hit、single-flight、Provider 调用次数、来源数量、
  `source_id` 绑定成功率和放弃原因；
- 媒体失败不影响文字回答；
- SearchPro 失败不允许回答当前事实为已核验事实；
- 取消信号传递到搜索、Graph 和后台媒体任务；
- 结构化副作用继续要求显式确认和幂等键。

## 13. 测试与验收

### 13.1 媒体协议

- 生产代码不存在可放置 `YUANBAO_MEDIA` 的解析路径；
- 测试可保留该文本作为恶意/历史输入，断言它被删除且不产生图片；
- 模型直接生成的搜索图片 Markdown 不显示；
- 审核媒体只有在 `source_id`、规范化 `source_url` 和正文链接全部一致时
  显示一次；
- 无引用、错 URL、错 run、未审核和迟到到其他会话的媒体全部失败关闭。

### 13.2 搜索

- `needs_web_search=true` 时 SearchUseCase 最多调用 SearchPro 一次；
- Answer Graph 的本轮工具集合不含 `rich_search`；
- 普通搜索首字不等待 page scraping 或 vision；
- 生图参考模式仍等待审核媒体；
- 缓存命中仍重新生成最终回答；
- 显式刷新绕过证据缓存。

### 13.3 MVC 与 Skills

- 所有 Agent `index.py` 只做协议适配和 Controller 委托；
- route 文件不直接 import Provider 或领域 Repository；
- 每个声明工具的系统 Skill 都有可信 Adapter；
- 中央 `_ui_tools.py` 在迁移完成后删除；
- 关闭 Skill、依赖缺失、Provider 未连接和会员不足时工具不会注册；
- 未审核用户 ZIP 永不进入 Python import 路径。

### 13.4 多租户与权益

- Node/Python 权益结果来自同一 Contract 并完全一致；
- Guest 不能使用其余七个系统 Skill；
- Store、Checkpointer、Blob 和数据库 key 均由签名身份派生；
- 跨租户 conversation/file/skill-upload 访问失败。

### 13.5 前端与工程门禁

- Python、Node、frontend 测试全绿且测试总数不减少；
- lint 无 error；
- frontend production build 成功；
- 9 个标准 Skill 校验通过；
- EdgeOne 实际构建路由通过 allowlist 检查；
- 关键端到端流程覆盖 Guest、新对话、搜索首字、媒体迟到、取消、断线恢复、
  Skill 广场、Action 确认和错误重试；
- `main` hash 与独立 Maker 项目边界检查通过。

## 14. 分阶段交付与回滚

1. **P0：媒体与 Chat Search**
   删除占位符放置；新增 SearchUseCase；让已规划搜索绕过 Graph 的重复工具
   决策；提取 StreamPresenter。
2. **P0：ChatTurnController**
   把上下文装配、状态读取、Graph 执行和后台任务移出 route。
3. **P0/P1：系统 Skill Adapter**
   依照第 7.2 节顺序逐个迁移，最后删除中央工具工厂。
4. **P1：Domain/Infrastructure 与权益 Contract**
   拆空 `_shared`，统一 Node/Python 权益数据。
5. **P1/P2：前端 Feature MVC**
   先拆 Chat/Search，再拆 Calendar/Maps/Papers/Settings。
6. **P2：CSS、测试和性能门禁**
   完成样式、测试目录迁移和端到端/性能验收。
7. **发布**
   每一阶段独立提交并推送 `dev`；最终从干净已推送提交构建 `.edgeone`，
   验证路由后只通过 `dev` 推送部署 `floris-dev`。

每阶段回滚只反向提交该阶段或在独立 Maker 项目选择上一部署。禁止改写
`main` 历史，禁止把 `dev` 绑定到现有正式项目。

## 15. 完成定义

只有以下条件同时成立才算完成：

1. 本文全部验收项有自动化或线上证据；
2. `source_id` 是搜索图片进入正文的唯一定位机制，项目不存在媒体占位符
   放置行为；
3. Chat route、SearchUseCase 和 StreamPresenter 边界真实落地；
4. 搜索规划后不存在第二次 `rich_search` 工具决策；
5. 所有内置工具通过所属 Skill Adapter 注册；
6. `_shared` 不再承载业务实现；
7. Node/Python 权益使用同一 Contract；
8. 六个前端业务域完成 feature MVC；
9. 全局 CSS 和超长测试文件完成领域拆分；
10. `dev` 已推送、独立 Maker 部署验收成功、`main` 与正式 Maker 项目完全
    未变化。
