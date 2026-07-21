# 当前发布记录

> 本文件只记录有证据的部署事实。变量真实值、Preview 签名、Cookie 和同步密钥不得写入仓库。

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
- Preview 提交：`826be013e4b1c3b961d0caaca8c7ee369efe8520`
- Preview Deployment：`dpke66jsaxpb`
- 创建时间：2026-07-21 14:24（Asia/Shanghai）
- 构建结果：成功，66 秒。
- 构建内容：前端静态资源、Node Cloud Functions、13 条 Python Agent 路由和 1 条 `Asia/Shanghai` 每日 Schedule。
- 线上回归：无缓存新闻搜索保留独立 LLM 规划，工具阶段 17.8 秒、正文 27.3 秒；单轮只有 1 次 SearchPro，请求完成后不再产生冗余工具绑定模型轮次。SearchPro 曾返回并成功加载 919×376 的真实新闻现场图；图片审核改为与文本综合并行，任意 SSE 到达顺序都不会丢图。新对话在有未读风险时由模型自然主动开场；旧左栏主动提醒区已移除，设置、Skills 广场和腾讯会议个人授权引导已上线。CAL-06、PRO-06 和 PRO-08 已在真实 Preview 完成：重叠日程、路线风险、自然语言修改和清理均通过；工作流补偿、重试、依赖恢复、同标题去重及结束后通知清理均通过。最终应用和 64 条验收站均连接成功。

本 Preview 是个人演示版：运行时固定单用户，已移除 JWT、Neon、登录注册和租户隔离；持久化使用 Makers Conversation Store、LangGraph Store/Checkpointer、Blob 与 Schedule。搜索保留独立 LLM 规划、单轮一次 `rich_search`、并发事实/视觉查询和持久缓存，并提供 4/8/12/18 个网页结果、0/2/4 张图片与并发开关。

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
| Preview | `dpke66jsaxpb` | `826be01` | 当前 Preview；成功；主动工作流同标题幂等、工作流结束后旧通知清理、PRO-08 精确步骤和 Skills 设置稳定性修复。 |

GitHub Provider 项目不支持 `edgeone makers deploy` 本地目录直传。当前发布方式是先推送目标分支，再从 EdgeOne 控制台“构建部署 → 新建部署”选择该分支。详细步骤见 [`DEPLOYMENT.md`](DEPLOYMENT.md)。

## 自动化证据

当前运行代码 `826be01` 已验证：

- Cloud Functions、验收持久化与平台约束：17 项通过。
- 前端 Vitest：41 项通过。
- Python Agent：96 项通过。
- 旧数据迁移工具：2 项通过。
- ESLint、TypeScript/Vite EdgeOne 构建、`edgeone makers build` 和 `git diff --check`：通过。
- EdgeOne 云端构建：成功。

这些自动化和只读冒烟不替代真实模型、外部 Provider、图片生成和跨日 Cron 的人工验收。

## 当前边界

- `dpke66jsaxpb` 尚未发布生产；共享验收站当前 53 条通过、0 条失败、11 条阻塞/未测，生产阻断通过 40/42，门禁仍明确为“禁止生产发布”。原 34 条阻塞专项已归类为 23 条通过、11 条不适用/外部阻塞、0 条真实场景待测。
- PRO-08 清理后的首次整页重载曾出现 1 次 EdgeOne `CLOUD_FUNCTION_INVOCATION_TIMEOUT`；立即使用同一 Preview 链接重试后恢复，应用重新连接，随后新建对话与刷新均正常。当前按不可稳定复现的平台瞬时错误记录，生产发布前仍需继续观察日志和冷启动重载。
- “最近AI有什么新进展”最终无缓存样例在 17.8 秒拿到工具结果、27.3 秒显示正文，达到最慢约 30 秒目标；5–10 秒仍只能在缓存命中或 Provider 较快时达到，不能普遍承诺。
- Cloudflare Workers AI 测试 Token 已仅配置到 Preview 且验证为有效，但该 Token 无权列出 Account，当前仍缺 `CLOUDFLARE_ACCOUNT_ID`，因此免费视觉降级尚不能真实调用。SearchPro 图片链路已真实成功过，但视觉 Provider 不可用或候选不相关时会诚实不展示图片，不再声称图片正在生成。混元文生图和图生图已真实通过。
- 真实旧 SQLite 备份尚未执行数量、哈希和抽样回读；迁移代码与测试已完成。
- 真实平台跨日定时触发和各 Provider 付费调用仍需专项验收。
- 腾讯会议是可选 Skill；个人账号不要求企业 `SecretId/AppId`，但仍需从腾讯会议 AI Skill 页面取得个人 MCP Token，并只保存到 Makers 环境变量。
- DOC/DOCX、扫描 PDF OCR、页码级引用尚未实现。
- 未绑定自定义域名，Preview 测试链接默认有效 3 小时，签名不得提交仓库。

## 回滚

- 当前生产回滚目标：上一成功 Production Deployment `dpk92buifgid`。
- Preview 失败只废弃对应 Preview，不影响当前生产。
- 回滚只切换 Deployment，不删除 Blob、LangGraph Store、Conversation Store 或旧 SQLite 数据。
