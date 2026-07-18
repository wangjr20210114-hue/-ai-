# 验收测试站（Makers 持久化版）

## 目标

测试站入口为 `/test-cases/`。前端仍是无框架静态页面，测试结果、备注、编辑审计和图片/视频证据由 EdgeOne Makers 托管，不再只依赖单台浏览器的 `localStorage`。

## 平台复用

| 能力 | Makers 轮子 | 本项目只负责的业务逻辑 |
| --- | --- | --- |
| 共享测试状态 | Cloud Function `/acceptance` + Makers Blob `yuanbao-acceptance` | 校验用例 ID、合并结果/备注、冲突提示 |
| 媒体证据 | Blob `createUploadUrl` 预签名 PUT | 类型/大小限制和证据元数据 |
| 多主机识别 | 浏览器生成 UUID + 可编辑主机名称 | 把主机、测试人、时间写入审计事件 |
| 强一致读取 | Blob `consistency: strong` | 页面“同步最新”、版本号和最后更新时间 |
| Preview 访问保护 | EdgeOne 受保护预览链接 | 自动把 `eo_token`、`eo_time` 带到 Function/证据请求 |

结构化状态位于 `v2/state.json`，证据位于 `v2/evidence/<CASE-ID>/...`。图片上限 20MB，视频上限 100MB。Blob 内容不经过 Cloud Function 转发上传，避免大文件占用函数请求时间。

## 数据模型

- 每条用例：`result`、`notes`、`evidence[]`、`updatedAt`、`updatedByHostId`、`updatedByHostName`、`updatedByTester`。
- 审计：字段、修改前/后值、用例 ID、主机 ID/名称、测试人、编辑时间；最多保留最近 1500 条。
- 编辑冲突：客户端提交上次看到的 `baseUpdatedAt`。另一台主机已经更新同一用例时返回 HTTP 409，页面载入服务端版本并要求重新填写，避免静默覆盖。
- 本地兜底：Function 暂时不可用时，结果和备注仍保存在当前浏览器；媒体证据必须在线才能上传。

## 使用

1. 从 Makers 控制台打开受保护的 Preview 链接，进入 `/test-cases/`。
2. 填写测试环境、Deployment ID、测试人和当前主机名称。
3. 等待顶部状态显示“已同步”。多台电脑使用同一站点时各自填写不同主机名称。
4. 旧版 JSON 点击“导入 JSON”；导入会生成审计记录并写入共享 Blob。
5. 备注只记录文本；截图/录屏从证据入口上传。刷新后确认附件仍可打开。
6. 每条用例按安全说明执行。无法获得隔离 Preview 或本地 Mock 条件时标记“阻塞”，不得改 Production 配置制造故障。

## 可选写保护

受保护 Preview 可直接使用。若以后绑定公开自定义域名，必须在 Makers 项目设置 Secret 环境变量 `ACCEPTANCE_WRITE_SECRET`，重新部署后在每台测试电脑的“同步密钥”输入同一个值。密钥只保存在该浏览器，禁止写入源码、JSON 导出、截图或备注。

## 本地验证

```bash
npm test
cd frontend && npm run build -- --mode edgeone
edgeone makers dev
```

访问 `http://127.0.0.1:8088/test-cases/index.html`。至少验证：

- 66 条用例、7 列表格和 66 个证据入口完整出现。
- 表头 `position: static`，表头底部与 CORE-01 顶部相接但不重叠。
- 修改结果和备注后版本号递增，刷新后仍存在，编辑记录包含主机和时间。
- 上传测试图片后出现证据链接，刷新后仍可打开。
- 浏览器 Console 没有新增 error。

## 部署与生产边界

当前独立测试项目为 `yuanbao-acceptance-cases`（`makers-fe2uwebn6fx3`）。只发布 Preview：

```bash
edgeone makers deploy --env preview --json
```

测试站 Preview 与正式应用项目、正式业务 Blob 相互隔离。本轮不得执行测试站 Production 发布，也不得把应用业务分支发布到 Production。
