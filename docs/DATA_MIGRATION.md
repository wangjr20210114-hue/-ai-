# SQLite 到 EdgeOne Makers 数据迁移

目标不是把 SQLite 表整体搬到另一个自建数据库，而是按 Makers 官方状态所有权拆分：

| 旧数据 | 目标能力 |
| --- | --- |
| conversations / messages | Makers Conversation Store |
| 日程、旅行计划、Action | Makers LangGraph Store 的 Workspace namespace |
| Event、Run、Notification、Checkpoint | Makers LangGraph Store 的 Proactive namespace |
| Memory、Feedback、Usage | Makers LangGraph Store 的 Intelligence namespace |
| PDF、论文和上传文件 | Makers Blob `yuanbao-files` namespace |
| 多用户账号 | Neon `users` 表；不迁移旧本地访问令牌或明文密码 |

生产代码不安装 SQLite 驱动。`tools/export_sqlite.py` 是一次性本地只读工具，`agents/migration` 只接收标准迁移包并调用 Makers 内置 Store。

## 1. 选择身份模式

个人部署建议先使用 `AUTH_MODE=single_user`。该模式不需要 Neon、`DATABASE_URL` 或 `JWT_SECRET`，Conversation Store、LangGraph Store、Blob 和 Cron 仍由 Makers 提供。

需要开放给多名用户时，再创建 Neon、执行 `db/001_users.sql`，并切换 `AUTH_MODE=multi_user`。旧 SQLite 的 `local-user` 数据导入到登录后的目标账号；不复制旧本地 Token。

## 2. 只读导出

先停止旧 FastAPI 写入，或对其备份快照执行：

```bash
python tools/export_sqlite.py /path/to/yuanbao.db /path/to/makers-bundle --include-files
```

导出器使用 SQLite `mode=ro` 和 `PRAGMA query_only=ON`，不执行旧 migration，不启动 FastAPI。它生成稳定 `export_id`、源库和文件 SHA-256、数量清单；未完成副作用不会导入，旧 scheduled job 只保存为 `migration_review_required`，且拒绝覆盖非空输出目录。

## 3. 部署一次性导入入口

生成至少 32 字符的随机迁移密钥，只配置到 Preview：

```bash
edgeone makers env set LEGACY_IMPORT_SECRET '<one-time-secret>'
git push -u origin <迁移验收分支>
```

随后从 EdgeOne 控制台 → Makers → `ai-active-agent` → 构建部署 → 新建部署，选择迁移验收分支并创建 Preview。当前项目是 GitHub Provider，不能使用 `edgeone makers deploy` 直传本地目录。

`/migration` 同时要求迁移密钥；多用户模式还要求目标用户的有效 HttpOnly 登录 Cookie。消息每批最多 50 条，状态采用非破坏合并；相同 ID 内容不同会返回冲突，不覆盖线上数据。

## 4. 导入 Makers Store 与 Blob

单用户核心数据：

```bash
node tools/import-makers.mjs \
  --bundle /path/to/makers-bundle \
  --base-url https://preview.example \
  --secret '<one-time-secret>'
```

同时迁移文件时，传入 Makers Project ID 和 EdgeOne API Token；工具只通过官方 `@edgeone/pages-blob` SDK 写 Blob：

```bash
node tools/import-makers.mjs \
  --bundle /path/to/makers-bundle \
  --base-url https://preview.example \
  --secret '<one-time-secret>' \
  --project-id '<makers-project-id>' \
  --api-token '<edgeone-api-token>'
```

多用户模式额外传 `--multi-user --user-id '<uuid>' --cookie 'jwt_token=...'`。Token、Cookie 和迁移密钥不得写入仓库或普通日志。

## 5. 验收与关闭入口

1. 对比 manifest 数量和导入结果。
2. 抽样打开历史会话并继续对话；首轮会把 Conversation Store 历史种入 LangGraph Checkpointer。
3. 抽样检查日程、通知、记忆、用量和 PDF 文件 SHA-256。
4. 人工处理所有 `conflict`、`unknown` 和 `migration_review_required`。
5. 验收后立即执行 `edgeone makers env rm LEGACY_IMPORT_SECRET`，再从控制台为同一已审核提交重新创建 Preview；确认新 Deployment 不再接受迁移密钥。
6. Preview 最终验收前不删除旧 SQLite、上传目录或备份。
