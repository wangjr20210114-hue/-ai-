# 当前发布记录

> 本文件只记录有证据的部署事实。变量真实值不得写入仓库。

## 当前生产

- Makers 项目：`ai-active-agent`
- Project ID：`makers-0oeuhire655w`
- GitHub：`wangjr20210114-hue/-ai-`
- 生产分支：`codex/edgeone-makers-refactor`
- 生产提交：`8a25bc0d9fe98d003baa581edf3e02f3b080d41b`
- 生产 Deployment：`dp2aglwjqj7l`
- 发布时间：2026-07-18
- 结论：平台 Git 构建、静态资源、Cloud Functions、Agents 和生产发布均成功。

未绑定自定义域名时，默认 `edgeone.cool` 地址启用访问保护，直接访问会返回 401。测试者需在该 Deployment 点击“预览”获取 3 小时访问链接；这不是应用鉴权失败。

## 发布证据

| 环境 | Deployment ID | 提交 | 结论 |
| --- | --- | --- | --- |
| Preview | `dpkr22b0au30` | `ee3a355` | Git 构建成功，但小时级 Cron 违反 Makers 最短 1 天间隔，`routes.json` 未生成；仅静态资源可用。 |
| Preview | `dpdbu4eyrid8` | `8a25bc0` | 69 秒成功；控制台登记 11 条 Node Cloud Functions 和 12 条 Python Agents；受保护链接显示“已连接”，历史对话、日程、路线、阅读库和 `/system` 读取通过。 |
| Production | `dp2aglwjqj7l` | `8a25bc0` | 193 秒成功；Functions 发布完成，控制台登记 11 条 Cloud Functions 和 12 条 Agents；受保护生产链接显示“已连接”，历史数据加载成功且无新增前端错误。 |

根因修复：原 `0 * * * *` Cron 被 EdgeOne CLI 1.6.13 的最短 1 天间隔校验拒绝，生成动态路由前退出。现改为 `Asia/Shanghai` 每日 08:00，`edgeone makers generate-routes` 已生成完整 Functions、Agents 和 Schedule 路由。

## 自动化证据

- Makers Agent：53 项通过。
- SQLite 只读导出：2 项通过。
- Cloud Functions/平台约束：9 项通过。
- 前端 Vitest：24 项通过。
- ESLint、TypeScript/Vite EdgeOne 构建和 `git diff --check`：通过。
- 本地路由生成：11 条 Node Functions、12 条 Python Agents、1 条每日 Schedule。

## 当前边界

- 真实旧 SQLite 备份尚未执行数量、哈希和抽样回读；迁移代码与测试已完成。
- 多用户 A/B 隔离、真实平台定时触发和各 Provider 付费调用仍需专项验收。
- 腾讯会议是最后阶段可选连接器；个人部署不要求先申请企业 API。
- DOC/DOCX、扫描 PDF OCR、页码级引用尚未实现。
- 未绑定自定义域名，测试链接默认有效 3 小时。

## 回滚

- 回滚目标：发布前生产 Deployment `dptvxaubmrso`。
- 回滚只切换 Deployment，不删除 Blob、Store、Neon 或旧 SQLite 数据。
