# 文档索引

本目录只保留 EdgeOne Makers 当前事实、执行计划和验收材料。历史 FastAPI 文档不再作为开发依据。

## 当前事实源

- [`ARCHITECTURE.md`](ARCHITECTURE.md)：唯一目标架构与状态所有权。
- [`BASELINE.md`](BASELINE.md)：当前功能、条件能力、缺口和零缩水门槛。
- [`MIGRATION_PLAN.md`](MIGRATION_PLAN.md)：按 P0–P3 执行的改造计划。
- [`DEPLOYMENT.md`](DEPLOYMENT.md)：环境变量、构建、Preview、终验与回滚。
- [`DATA_MIGRATION.md`](DATA_MIGRATION.md)：SQLite 只读导出和 Makers Store/Blob 导入。
- [`LEGACY_FASTAPI_CAPABILITIES.md`](LEGACY_FASTAPI_CAPABILITIES.md)：旧用户结果的迁移对照，不是目标技术方案。
- [`EDGEONE_PLATFORM_REUSE_AUDIT.md`](EDGEONE_PLATFORM_REUSE_AUDIT.md)：平台能力复用与禁止重复建设清单。
- [`CURRENT_RELEASE.md`](CURRENT_RELEASE.md)：最近已知发布和待复验项。
- [`TESTING.md`](TESTING.md)：自动化测试、本地测试站启动、Preview 验收和测试数据边界。
- [`ACCEPTANCE_SITE.md`](ACCEPTANCE_SITE.md)：跨主机验收站、证据上传、编辑审计与安全测试说明。
- [`MAKERS_PROACTIVE_IMPLEMENTATION_STATUS.md`](MAKERS_PROACTIVE_IMPLEMENTATION_STATUS.md)：主动运行时实现状态。
- [`SEARCH_CONFIGURATION.md`](SEARCH_CONFIGURATION.md)：搜索并行策略、上限、缓存与性能结论。
- [`VISUAL_PROVIDER_FALLBACK.md`](VISUAL_PROVIDER_FALLBACK.md)：免费视觉 API 结论、降级顺序、配置和安全验收。
- [`ACCEPTANCE_RETEST_2026-07-20.md`](ACCEPTANCE_RETEST_2026-07-20.md)：原 34 条阻塞/未测用例的真实复测、外部阻塞分类和代码缺陷修复证据。
- [`TENCENT_MEETING_SETUP.md`](TENCENT_MEETING_SETUP.md)：腾讯会议个人账号边界和环境变量来源。

## 文档维护规则

1. 架构变化更新 `ARCHITECTURE.md`。
2. 功能状态变化更新 `BASELINE.md`。
3. 阶段进度更新 `MIGRATION_PLAN.md`。
4. 每次 Preview/生产发布更新 `CURRENT_RELEASE.md`。
5. 测试命令、测试站入口或持久化方式变化更新 `TESTING.md` 和 `ACCEPTANCE_SITE.md`。
6. 不再新增以 FastAPI 路由或 SQLite 表为目标的计划文档。
