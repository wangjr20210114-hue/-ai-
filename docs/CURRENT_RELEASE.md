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

- Preview 分支：`codex/acceptance-test-site`
- Preview 提交：`9ed04b19150843b9a3a4efed091bbf39c2d22138`
- Preview Deployment：`dph2wvagts0x`
- 创建时间：2026-07-18 20:02（Asia/Shanghai）
- 构建结果：成功，192 秒。
- 构建内容：前端静态资源、Node Cloud Functions、13 条 Python Agent 路由和 1 条 `Asia/Shanghai` 每日 Schedule。
- 只读冒烟：受保护链接可打开，应用由“连接中”切换为“已连接”；历史会话、用户级日程、腾讯路线缓存、阅读库和代码块高亮/复制均正常读取。

本 Preview 包含验收记录中所有带描述问题的修复：网络错误中文化、代码高亮复制、日程跨对话匹配与即时主动扫描、地点回退、图片粘贴/参考图、图片版本加载状态、PDF 内置助读、阅读库移动/删除反馈、Reader 会话头和论文去重补足。

## 部署证据

| 环境 | Deployment ID | 提交 | 结论 |
| --- | --- | --- | --- |
| Preview | `dpdbu4eyrid8` | `8a25bc0` | 首次完整 Makers 动态路由 Preview；历史会话、日程、路线、阅读库和 `/system` 读取通过。 |
| Production | `dpk92buifgid` | `c7edf79` | 成功；修正 Makers 日程状态。 |
| Production | `dp8p5j6dewo0` | `4125c37` | 当前生产；成功；修复腾讯地图清理竞态。 |
| Preview | `dpzcwuz2sjg4` | `3d42b8f` | 成功；修复聊天与 Workspace 验收回归。 |
| Preview | `dph2wvagts0x` | `9ed04b1` | 当前 Preview；成功；包含全部带描述验收问题修复。 |

GitHub Provider 项目不支持 `edgeone makers deploy` 本地目录直传。当前发布方式是先推送目标分支，再从 EdgeOne 控制台“构建部署 → 新建部署”选择该分支。详细步骤见 [`DEPLOYMENT.md`](DEPLOYMENT.md)。

## 自动化证据

当前 `9ed04b1` 已验证：

- Cloud Functions、验收持久化与平台约束：16 项通过。
- 前端 Vitest：34 项通过。
- Python Agent：63 项通过。
- ESLint、TypeScript/Vite EdgeOne 构建和 `git diff --check`：通过。
- EdgeOne 云端构建：成功；依赖审计为 0 个漏洞。

这些自动化和只读冒烟不替代真实模型、外部 Provider、图片生成和跨日 Cron 的人工验收。

## 当前边界

- `dph2wvagts0x` 尚未发布生产；必须先在 `/test-cases/` 完成相关用例复验。
- 真实旧 SQLite 备份尚未执行数量、哈希和抽样回读；迁移代码与测试已完成。
- 真实平台跨日定时触发和各 Provider 付费调用仍需专项验收。
- 腾讯会议是最后阶段可选连接器；个人部署不要求先申请企业 API。
- DOC/DOCX、扫描 PDF OCR、页码级引用尚未实现。
- 未绑定自定义域名，Preview 测试链接默认有效 3 小时，签名不得提交仓库。

## 回滚

- 当前生产回滚目标：上一成功 Production Deployment `dpk92buifgid`。
- Preview 失败只废弃对应 Preview，不影响当前生产。
- 回滚只切换 Deployment，不删除 Blob、LangGraph Store、Conversation Store 或旧 SQLite 数据。
