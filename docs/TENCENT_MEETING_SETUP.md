# 腾讯会议 Skill（个人账号可用）

腾讯会议是个人演示的可选 Skill，不是生产阻断项。当前版本优先使用腾讯会议官方远程 MCP，不需要企业自建应用的 `SecretId`、`SecretKey`、`AppId` 或 `SdkId`。

## 安装与授权

1. 在应用左栏点击“Skills 广场” → “腾讯会议” → “开始安装”。
2. 登录腾讯会议官方 [AI Skill 页面](https://meeting.tencent.com/ai-skill)，按页面提示获取个人 Token。
3. 在 EdgeOne Makers 项目的 Preview 环境变量中新增 `TENCENT_MEETING_TOKEN`，值为刚取得的 Token。
4. 重新部署 Preview，回到“Skills 广场”点击“刷新状态”；显示“已连接”后才会向模型开放腾讯会议工具。

Token 等同当前腾讯会议账号身份。不要把它粘贴到聊天、网页表单、验收备注、截图、JSON 导出、日志或 GitHub；只保存在 Makers 的加密环境变量中。生产环境应使用独立 Token，并在测试完成后轮换测试 Token。

## 技术边界

- 官方远程 MCP 地址：`https://mcp.meeting.tencent.com/mcp/wemeet-open/v1`。
- 代码通过 JSON-RPC `tools/call` 调用 `schedule_meeting`；用户仍需在网页 Action 卡中确认，确认前不创建会议。
- 浏览器不能运行用户本机的 Python/CLI 代理。因此“安装”不是在网页中启动本机 CLI，而是引导用户取得官方个人 Token，再由 Makers Agent 从服务端连接官方 MCP。
- “不需要开发者 API”表示不需要申请企业开放平台应用凭据；不表示完全不需要授权凭据。
- 未配置 Token 时，普通日程、主动服务和其他核心能力不受影响；模型不会假装已经创建会议。

旧企业服务端 API 变量只保留兼容已有部署，新个人部署不再需要配置它们。
