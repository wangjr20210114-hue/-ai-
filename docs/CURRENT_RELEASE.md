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
- 结论：EdgeOne 控制台状态为“成功”。当前生产仍是发布前稳定版本，不包含 `codex/acceptance-test-site` 上尚待人工复验的最新修复。

生产只允许非破坏性冒烟。未绑定自定义域名时，默认 `edgeone.cool` 地址启用访问保护，测试者需在 Deployment 点击“预览”获取 3 小时签名链接；直接访问未携带签名的域名返回 401 不表示应用鉴权失败。

## 当前 Preview

- Preview 分支：`agent/makers-native-persistence-fixes`
- Preview 提交：`438093f6f46647471fd56bbf71e23091a71dcad6`
- Preview Deployment：`dpxl03mjkz33`
- 创建时间：2026-07-20 17:54（Asia/Shanghai）
- 构建结果：成功，70 秒。
- 构建内容：前端静态资源、Node Cloud Functions、13 条 Python Agent 路由和 1 条 `Asia/Shanghai` 每日 Schedule。
- 线上回归：搜索设置跨刷新持久化通过；自动记忆跨新对话召回通过；主动扫描约 3.6 秒完成并更新最近检查时间，运行记录可读；搜索生成期间地图路线和日程保持不变；测试站显示 64 条有效用例并已移除废弃多用户/连接器用例。

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
| Preview | `dpxl03mjkz33` | `438093f` | 当前 Preview；成功；补充 SearchPro 内嵌新闻主图解析。 |

GitHub Provider 项目不支持 `edgeone makers deploy` 本地目录直传。当前发布方式是先推送目标分支，再从 EdgeOne 控制台“构建部署 → 新建部署”选择该分支。详细步骤见 [`DEPLOYMENT.md`](DEPLOYMENT.md)。

## 自动化证据

当前 `438093f` 已验证：

- Cloud Functions、验收持久化与平台约束：14 项通过。
- 前端 Vitest：37 项通过。
- Python Agent：82 项通过。
- 旧数据迁移工具：2 项通过。
- ESLint、TypeScript/Vite EdgeOne 构建和 `git diff --check`：通过。
- EdgeOne 云端构建：成功。

这些自动化和只读冒烟不替代真实模型、外部 Provider、图片生成和跨日 Cron 的人工验收。

## 当前边界

- `dpxl03mjkz33` 尚未发布生产；测试站仍有 3 条失败、34 条阻塞/未测，生产门禁明确为“禁止生产发布”。
- “最近AI有什么新进展”四次真实 Preview 回归均完成并附来源，耗时约 50–76 秒；最后一次约 67 秒。SearchPro 主图可通过 HTTPS 打开，但回答图片仍为 0。控制台已配置 `HUNYUAN_IMAGE_API_KEY`，未配置独立 `HUNYUAN_VISION_API_KEY`；需为 `hy-vision-2.0-instruct` 配置有权限的专用密钥并复验，不能把图片用例记为通过。
- 真实旧 SQLite 备份尚未执行数量、哈希和抽样回读；迁移代码与测试已完成。
- 真实平台跨日定时触发和各 Provider 付费调用仍需专项验收。
- 腾讯会议是最后阶段可选连接器；个人部署不要求先申请企业 API。
- DOC/DOCX、扫描 PDF OCR、页码级引用尚未实现。
- 未绑定自定义域名，Preview 测试链接默认有效 3 小时，签名不得提交仓库。

## 回滚

- 当前生产回滚目标：上一成功 Production Deployment `dpk92buifgid`。
- Preview 失败只废弃对应 Preview，不影响当前生产。
- 回滚只切换 Deployment，不删除 Blob、LangGraph Store、Conversation Store 或旧 SQLite 数据。
