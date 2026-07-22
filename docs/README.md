# 文档索引

本目录只保留 EdgeOne Makers 当前事实、执行计划和验收材料。历史 FastAPI 文档不再作为开发依据。

## 当前事实源

- [`ARCHITECTURE.md`](ARCHITECTURE.md)：唯一目标架构与状态所有权。
- [`BASELINE.md`](BASELINE.md)：当前功能、条件能力、缺口和零缩水门槛。
- [`CONTEST_SOLUTION.md`](CONTEST_SOLUTION.md)：比赛命题解释、主动机会闭环、当前覆盖和验收门槛。
- [`DEPLOYMENT.md`](DEPLOYMENT.md)：环境变量、构建、Preview、终验与回滚。
- [`DATA_MIGRATION.md`](DATA_MIGRATION.md)：SQLite 只读导出和 Makers Store/Blob 导入。
- [`LEGACY_FASTAPI_CAPABILITIES.md`](LEGACY_FASTAPI_CAPABILITIES.md)：旧用户结果的迁移对照，不是目标技术方案。
- [`EDGEONE_PLATFORM_REUSE_AUDIT.md`](EDGEONE_PLATFORM_REUSE_AUDIT.md)：平台能力复用与禁止重复建设清单。
- [`CURRENT_RELEASE.md`](CURRENT_RELEASE.md)：最近已知发布和待复验项。
- [`TESTING.md`](TESTING.md)：自动化测试、本地测试站启动、Preview 验收和测试数据边界。
- [`ACCEPTANCE_SITE.md`](ACCEPTANCE_SITE.md)：跨主机验收站、证据上传、编辑审计与安全测试说明。
- [`SEARCH_CONFIGURATION.md`](SEARCH_CONFIGURATION.md)：搜索并行策略、上限、缓存与性能结论。
- [`VISUAL_PROVIDER_FALLBACK.md`](VISUAL_PROVIDER_FALLBACK.md)：免费视觉 API 结论、降级顺序、配置和安全验收。
- [`MOTION_AND_VISUAL_FALLBACK.md`](MOTION_AND_VISUAL_FALLBACK.md)：Apple 风格微交互动效基线、混元当前接口与 Cloudflare 最小降级配置。
- [`PROVIDER_HEALTH_2026-07-22.md`](PROVIDER_HEALTH_2026-07-22.md)：环境变量对应外部 API 的脱敏真实存活性快照。
- [`TENCENT_MEETING_SETUP.md`](TENCENT_MEETING_SETUP.md)：腾讯会议个人账号边界和环境变量来源。

## 文档维护规则

1. 架构变化更新 `ARCHITECTURE.md`。
2. 功能状态变化更新 `BASELINE.md`。
3. 比赛能力变化更新 `CONTEST_SOLUTION.md`，不再新增按日期命名的计划或复测日志。
4. 每次 Preview/生产发布更新 `CURRENT_RELEASE.md`。
5. 测试命令、测试站入口或持久化方式变化更新 `TESTING.md` 和 `ACCEPTANCE_SITE.md`。
6. 不再新增以 FastAPI 路由或 SQLite 表为目标的计划文档。
7. Provider 存活性只写脱敏状态、耗时和错误码，不写密钥、签名 URL 或完整响应。
