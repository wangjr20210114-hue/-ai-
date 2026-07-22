# 当前发布记录

> 本文件只记录有证据的部署事实。变量真实值、Preview 签名、Cookie 和 Provider Key 不得写入仓库。

## 当前生产

- Makers 项目：`ai-active-agent`
- Project ID：`makers-0oeuhire655w`
- GitHub：`wangjr20210114-hue/-ai-`
- 生产分支：`codex/edgeone-makers-refactor`
- 生产提交：`4125c37858a361e3e20d760600621ab1af81313e`
- 生产 Deployment：`dp8p5j6dewo0`
- 发布时间：2026-07-18 13:54（Asia/Shanghai）
- 结论：EdgeOne 控制台状态为“成功”。当前生产仍是发布前稳定版本，不包含 `agent/makers-native-persistence-fixes` 的最新修复。

生产只允许非破坏性冒烟。未绑定自定义域名时，默认 `edgeone.cool` 地址启用访问保护，测试者需在 Deployment 点击“预览”获取 3 小时签名链接；直接访问未携带签名的域名返回 401 不表示应用鉴权失败。

## 当前 Preview

- Preview 分支：`agent/makers-native-persistence-fixes`
- Preview 提交：`55b50f253e58876a4622618fa135f41b1162aa8c`
- Preview Deployment：`dpkx07zwm3mr`
- 创建时间：2026-07-22 18:16（Asia/Shanghai）
- 构建结果：成功，72 秒。
- 构建内容：前端静态资源、Node Cloud Functions、13 条 Python Agent 路由和 1 条 `Asia/Shanghai` 每日 Schedule。
- 本代修复新闻回答渲染稳定性：普通网页证据保持为 Markdown 内联链接，不再升级为卡片；AI 流式消息和富媒体不再反复播放入场动画；聊天区取消重叠的平滑自动滚动，用户向上滚轮、触摸、拖动滚动条、选择或复制文本时立即停止自动跟随；远程图片立即加载并始终以不透明状态显示。
- 流式阶段始终使用 Markdown 渲染器：标题、粗体、列表、链接和完整图片语法随内容到达即时格式化；未闭合的图片、媒体槽、粗体、下划线强调和删除线尾部暂时隐藏，闭合后再显示，避免向用户泄漏半截源码。流式期间关闭基于段落结构的图片兜底移动，仍保留显式媒体槽、复制选区保护和稳定滚动。
- `dpkx07zwm3mr` 线上无干扰格式样例：12.4 秒出现首个可见片段时已经存在 1 个 `<h2>`；随后 `<strong>` 节点按 `1→2→3→4` 增加，可见正文从 5 字流式增长到 668 字，全部采样中 Markdown 源标记泄漏均为 `false`，25.3 秒结束时只移除流式状态，不再进行纯文本到 Markdown 的整块替换。
- `dpuvibbfa7mr` 线上无缓存长回答采样：13.2 秒出现首段，随后可见文本长度按 `51→93→204→…→1691` 单调增长，流式阶段始终使用 `.streaming-answer-text` 且没有一次回退；28.9 秒结束后才切换为 `.markdown-body`。新闻问答返回 1 条回答和 1 张真实图片，图片自然尺寸 700×525、渲染宽度 425.75px，AI 气泡宽度 429.75px，图片容器左右边框均为 1px，说明文字与图片同宽且未裁切。
- `dpujm5tkw9fs` 线上实测“最近 AI 有什么进展？”只产生 1 条 AI 回答。新闻图片真实解码为 1000×555，`opacity=1`，图片和 AI 行动画均为 `none`；普通正文来源是无子卡片的内联链接。间隔 2.2 秒重复采样时，AI 行、图片和 `scrollTop` 的位置完全一致，未再出现持续抖动。
- 本代新增：9 个默认开启且可联动提示依赖的 Skills、日程就地下拉编辑/删除、全局可点击元素微交互、AI 媒体槽排版与基于 AI 段落结构的异步图片兜底、文章主图透传、与 AI 气泡同宽的全幅图片，以及 `v5_20260722_clean` 干净业务数据命名空间。旧 Store/Blob 数据保留用于回滚，但不会出现在本代界面。
- `dpmo5r7e9b69` 控制台构建成功后曾短暂出现 EdgeOne TLS 节点错误，随后恢复。最终签名 Preview 已连接：真实询问“最近 AI 有什么进展”只产生 1 条 AI 回答，返回 2 张 1080×452 / 1280×853 的真实新闻图片，分别位于开场说明后和第二个主题后，无媒体占位符泄漏；图片在动画起始缩放帧仍达到气泡宽度的 98.5%，播放完成为全幅。Skills 广场显示 9/9 默认开启，页面当前 63 个可点击元素均具有 transition 或 animation。
- 线上回归：应用已连接，设置、Skills 广场、历史会话、日历和 Makers 持久化数据可读取；专项 `TEST-CRON-1510` 日程已从 7 月 22 日清理。无缓存新闻搜索保留独立 LLM 规划，工具阶段 17.8 秒、正文 27.3 秒；单轮只有 1 次 SearchPro，请求完成后不再产生冗余工具绑定模型轮次。SearchPro 曾返回并成功加载 919×376 的真实新闻现场图；图片审核改为与文本综合并行，任意 SSE 到达顺序都不会丢图。新对话在有未读风险时由模型自然主动开场；设置、Skills 广场和腾讯会议个人授权引导已上线。CAL-06、PRO-06 和 PRO-08 已在真实 Preview 完成：重叠日程、路线风险、自然语言修改和清理均通过；工作流补偿、重试、依赖恢复、同标题去重及结束后通知清理均通过。地图专项 `TEST-MAP-PARTIAL-HEAD` 在线验证 3 个候选中 2 个核实成功：地图只显示悠航 SLOWBOAT 与潇湘阁，未核实的 BOTTEGA 未进入地图，也未被“三里屯”商圈冒充；正文准确显示成功 `2/3`、失败 `1/3`。当前代码同时覆盖“全部候选均未核实则拒绝生成地图”的边界，禁止空地图和虚假点位。最终 `dpmnthmfw7fx` 用 `TEST-MAP-DEDUPE-8486779` 验证：先切到 7 月 22 日日历详情，再点击“查看故宫博物院位置”，右栏立即恢复为“北京故宫博物院”，腾讯地图和唯一核实地点均出现；加载失败时仍保留核实地点列表和重试入口。`TEST-MEETING-FINAL-32ccf95` 验证缺失时间集中在同一可编辑卡片，填写 10:00–11:00 后得到 3 个独立冲突勾选项，以及“接受全部 3 项冲突提醒”“修改时间”“取消”和接受后创建入口；测试提案已取消，未调用会议 Provider。Cloudflare img2img 真实命中 `@cf/runwayml/stable-diffusion-v1-5-img2img`、`reference_count=1`、`fallback=False`，图片进入第 5 个版本且仍只有一张图片工坊卡；中文翻译预处理失败后使用原提示词继续执行，因此可用性通过但编辑跟随质量有限。空模型终稿、checkpoint 先于流结束以及 Action 重复到达三种竞态均有自动回归。

主动后台触发最终结构为 EdgeOne Schedule 每日 08:00 POST `/api/proactive-tick`，Node Cloud Function 使用 Makers Blob `onlyIfNew` 原子锁后转发 `/proactive` Agent，失败时释放锁。当前 Preview 的云端 Function 与 Agent 清单均已核对；受保护 Preview 的 Schedule 请求仍在进入 Function 运行时前被平台路由以 404 拦截，因此 PRO-07 保持外部阻塞，未发布生产。

本 Preview 是个人演示版：运行时固定单用户，已移除 JWT、Neon、登录注册和租户隔离；持久化使用 Makers Conversation Store、LangGraph Store/Checkpointer、Blob 与 Schedule。搜索保留独立 LLM 规划、单轮一次 `rich_search`、并发事实/视觉查询和持久缓存，并提供 4/8/12/18 个网页结果、0/2/4 张图片与并发开关。

本轮把已弃用的 `backend/` FastAPI/SQLite 运行时（166 个跟踪文件）、旧迁移方向文档、默认 Vite/React 图标以及企业版腾讯会议签名路径从仓库删除；当前业务只保留 Makers 原生 Agent、Cloud Function、Store、Blob、Schedule 与个人腾讯会议 MCP。`dp05mtwv0hfa` 线上复测“2026 世界人工智能大会现场有哪些重要 AI 新产品”：`/chat` 约 25.6 秒完成，返回 3 个可靠来源和 1 张相关搜索配图；页面和刷新后均只有 1 条 AI 回答，旧地图在模型思考与新对话间保持不刷新。规划超时时若主模型稍后选择 `rich_search`，媒体链也不再被空规划错误关闭。

## 部署证据

| 环境 | Deployment ID | 提交 | 结论 |
| --- | --- | --- | --- |
| Preview | `dpdbu4eyrid8` | `8a25bc0` | 首次完整 Makers 动态路由 Preview；历史会话、日程、路线、阅读库和 `/system` 读取通过。 |
| Production | `dpk92buifgid` | `c7edf79` | 成功；修正 Makers 日程状态。 |
| Production | `dp8p5j6dewo0` | `4125c37` | 当前生产；成功；修复腾讯地图清理竞态。 |
| Preview | `dpzcwuz2sjg4` | `3d42b8f` | 成功；修复聊天与 Workspace 验收回归。 |
| Preview | `dph2wvagts0x` | `9ed04b1` | 成功；包含当时全部带描述验收问题修复。 |
| Preview | `dpre2ruu98hn` | `4262a26` | 成功；个人演示、搜索设置与多用户删除后的首个干净构建。 |
| Preview | `dpxl03mjkz33` | `438093f` | 历史 Preview；成功；补充 SearchPro 内嵌新闻主图解析。 |
| Preview | `dpl61xo277ys` | `7c6a9c5` | 历史 Preview；成功；视觉降级、搜索预算、图片版本、大 PDF 分片/中文文件名与 arXiv 120 秒平台时限均已上线复测。 |
| Preview | `dppucqhthhnt` | `eb1bc19` | 历史 Preview；成功；新对话主动服务、搜索真实图片画廊、Skills 广场、腾讯会议个人 MCP 引导与 30 秒搜索性能改造。 |
| Preview | `dpke66jsaxpb` | `826be01` | 历史 Preview；成功；主动工作流同标题幂等、工作流结束后旧通知清理、PRO-08 精确步骤和 Skills 设置稳定性修复。 |
| Preview | `dp68sdom9rm5` | `76dde27` | 专项短周期 Cron；页面关闭时 Schedule 确实请求根级 Function，但平台路由返回 404、运行时间 0ms。 |
| Preview | `dpfbbacza7ac` | `5ae60ee` | 专项直接 Agent Cron；云端存在 `/proactive`，但 Schedule 没有发出 Agent 调度请求。 |
| Preview | `dpjffjsmaokh` | `9f1e79e` | 专项嵌套 Function Cron；云端存在 `/api/proactive-tick`，但平台请求仍在进入运行时前 404。 |
| Preview | `dptjeltndw8y` | `58ac263` | 历史 Preview；成功，71 秒；包含永久 08:00 Schedule、官方 Workers AI 请求格式、主动式 Schedule 桥接测试与完整阻塞证据。 |
| Preview | `dpy9p2uloo7d` | `4e7cc46` | 历史专项 Preview；成功；地点并行核实、部分成功地图、泛化商圈拒绝与正文数量一致性在线通过。 |
| Preview | `dpnfctdj8ld1` | `b520a74` | 历史 Preview；成功，137 秒；包含部分成功地图规则、全失败拒绝边界测试与 Cloudflare 中文图片提示词翻译修复。 |
| Preview | `dpu2leh922y2` | `f0e0165` | 历史 Preview；成功；地图 Action 显式/重复展开与腾讯会议可编辑条件卡、逐条冲突确认在线通过。 |
| Preview | `dpjo3fvc3aqe` | `3cb7f7d` | 历史诊断 Preview；成功；验证 Action 去重后暴露 checkpoint 先结束时的 Action 回挂竞态。 |
| Preview | `dp2ohxgfckff` | `8486779` | 历史 Preview；成功，70 秒；单一地图 Action、点击后显示、旧地图持久和切换日历后重复打开在线通过。 |
| Preview | `dp062qb6xrjm` | `040908d` | 历史 Preview；地图乐观展开与 SDK 超时回退、腾讯会议条件编辑和多冲突独立确认在线通过。 |
| Preview | `dpj3l8pjbwl6` | `1899df4` | 历史诊断 Preview；确认 Cloudflare 翻译预处理失败后混元安全兜底。 |
| Preview | `dpmnthmfw7fx` | `32ccf95` | 历史 Preview；成功；地点显示、会议多选条件卡和 Cloudflare img2img 真实调用在线通过。 |
| Preview | `dpm39mg7jlk0` | `966ab80` | 成功，193 秒；删除 FastAPI/SQLite 旧运行时，加入消息去重、Provider 脱敏探测和文档收口。 |
| Preview | `dp05mtwv0hfa` | `3f8f167` | 历史 Preview；成功，71 秒；规划超时仍保留搜索媒体，新闻单回答、刷新去重、25.6 秒正文和真实搜索配图在线通过。 |
| Preview | `dpmo5r7e9b69` | `5ea04c5` | 历史 Preview；成功，68 秒；干净数据代、Skills、全局动效、日程就地编辑/删除和 AI 段落图片排版；新闻单回答与 2 张段落内真实图片在线通过。 |
| Preview | `dpujm5tkw9fs` | `8c747c8` | 历史 Preview；成功，66 秒；新闻来源简化为 Markdown 链接，修复流式回答抖动、滚动争抢和图片透明白框。 |
| Preview | `dpld91zuafir` | `12516b9` | 中间 Preview；成功，69 秒；加入复制选区保护、停止强制贴底与图片/说明同宽边框修复。 |
| Preview | `dpuvibbfa7mr` | `df3cd82` | 历史 Preview；成功，70 秒；流式纯文本单调增长、结束后一次性 Markdown 格式化，真实流式、新闻图片尺寸与边框复验通过。 |
| Preview | `dpxfue2pren8` | `e3e7b77` | 中间 Preview；成功，69 秒；首次启用流式 Markdown，线上确认标题和粗体随片段即时渲染。 |
| Preview | `dpkx07zwm3mr` | `55b50f2` | 当前 Preview；成功，72 秒；隐藏未闭合 Markdown 标记，真实流式格式样例全程无源码泄漏。 |

GitHub Provider 项目不支持 `edgeone makers deploy` 本地目录直传。当前发布方式是先推送目标分支，再从 EdgeOne 控制台“构建部署 → 新建部署”选择该分支。详细步骤见 [`DEPLOYMENT.md`](DEPLOYMENT.md)。

## 自动化证据

当前分支待发布代码已验证：

- Cloud Functions、Schedule 桥接、验收持久化与平台约束：20 项通过。
- 前端 Vitest：68 项通过。
- Python Agent：131 项通过。
- SQLite 只读迁移工具：2 项通过。
- 旧数据迁移工具：2 项通过。
- ESLint、TypeScript/Vite EdgeOne 构建、`edgeone makers build` 和 `git diff --check`：通过。
- EdgeOne 云端构建：`dpkx07zwm3mr` 成功，72 秒。

本轮新增回归覆盖地图 Action 仅在用户点击后激活、同一地点组重复点击仍可恢复右栏，以及地图 SDK 临时失败时保留地点并提供重试。腾讯会议缺失主题/时间和日程冲突改为同一卡片逐项编辑与确认，确认前不会调用外部 Provider。

这些自动化和只读冒烟不替代真实模型、外部 Provider、图片生成和跨日 Cron 的人工验收。

## 当前边界

- `dpkx07zwm3mr` 尚未发布生产；生产仍保持 `dp8p5j6dewo0` 不变。共享验收站历史门禁仍明确为“禁止生产发布”，CORE-08（需测试人员按 Chrome“请求条件”补真实网络故障证据）和 PRO-07（受保护 Preview 的 EdgeOne Schedule 平台 404）仍未放行。
- PRO-08 清理后的首次整页重载曾出现 1 次 EdgeOne `CLOUD_FUNCTION_INVOCATION_TIMEOUT`；立即使用同一 Preview 链接重试后恢复，应用重新连接，随后新建对话与刷新均正常。当前按不可稳定复现的平台瞬时错误记录，生产发布前仍需继续观察日志和冷启动重载。
- “最近AI有什么新进展”最终无缓存样例在 17.8 秒拿到工具结果、27.3 秒显示正文，达到最慢约 30 秒目标；5–10 秒仍只能在缓存命中或 Provider 较快时达到，不能普遍承诺。
- Cloudflare Workers AI 的测试 Token 与 Account ID 均只配置到 Preview，生产环境不继承。Token、Flux 文生图和历史 img2img 实调可用；当前 Meta 视觉模型因许可返回 403/5016，LLaVA Beta 按官方小图字节数组仍返回 400/3010，混元视觉小图约 23.4 秒后返回 400/`400001`。因此多模态理解当前保持外部阻塞，不把历史成功写成现状。SearchPro 图片链路在 `dp05mtwv0hfa` 再次真实成功；没有可追溯候选或候选不相关时会诚实不展示图片。混元文生图和图生图已真实通过。
- 真实旧 SQLite 备份尚未执行数量、哈希和抽样回读；迁移代码与测试已完成。
- PRO-07 已完成三轮专用 Preview：Schedule 可在页面关闭时请求，但受保护 Preview 的路由/访问保护在进入已部署 Function 前返回 404；该项是当前平台外部阻塞，不用手动 tick 冒充通过。CORE-08 仍需测试人员按 Chrome“请求条件”完成一次真实网络阻断证据。
- 腾讯会议是可选 Skill；个人账号不要求企业 `SecretId/AppId`。个人 MCP Token 已仅保存到 Preview 并完成真实创会、日历单条写入和用户侧核对；生产不继承测试 Token。
- DOC/DOCX、扫描 PDF OCR、页码级引用尚未实现。
- 未绑定自定义域名，Preview 测试链接默认有效 3 小时，签名不得提交仓库。

## 回滚

- 当前生产回滚目标：上一成功 Production Deployment `dpk92buifgid`。
- Preview 失败只废弃对应 Preview，不影响当前生产。
- 回滚只切换 Deployment，不删除 Blob、LangGraph Store、Conversation Store 或旧 SQLite 数据。
