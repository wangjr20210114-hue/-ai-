# 文档索引

文档按“当前事实源”和“历史参考”分组。判断生产能力时不要仅依据 `backend/` 是否存在代码；EdgeOne Makers 构建只部署 `agents/`、`cloud-functions/` 和前端静态产物。

## 当前事实源

- [`CURRENT_ARCHITECTURE_AND_REFACTOR_PLAN.md`](CURRENT_ARCHITECTURE_AND_REFACTOR_PLAN.md)：当前底层架构、线上/本地能力分级、架构评价和下一阶段统一改造计划。
- [`CURRENT_ARCHITECTURE_CAPABILITIES_AND_PROACTIVE_GAP.md`](CURRENT_ARCHITECTURE_CAPABILITIES_AND_PROACTIVE_GAP.md)：当前能力边界和主动式 Agent 差距。
- [`EDGEONE_PLATFORM_REUSE_AUDIT.md`](EDGEONE_PLATFORM_REUSE_AUDIT.md)：底层能力复用矩阵与禁止重复建设清单。
- [`FASTAPI_RETIREMENT_MIGRATION.md`](FASTAPI_RETIREMENT_MIGRATION.md)：旧 FastAPI 最终迁移、淘汰项和新的发布门槛。
- [`CURRENT_RELEASE.md`](CURRENT_RELEASE.md)：最近一次线上发布记录和已知边界。
- [`EDGEONE_MAKERS_MIGRATION.md`](EDGEONE_MAKERS_MIGRATION.md)：Makers 平台映射、运行契约和部署检查。
- [`RICH_ANSWER_ARCHITECTURE.md`](RICH_ANSWER_ARCHITECTURE.md)：旧本地图文协议的设计经验；生产富搜索的当前实现以统一计划和 `agents/shared/rich_search.py` 为准。

## 历史/本地兼容参考

- `IMPLEMENTATION_STATUS.md`、`PROACTIVE_AGENT_REFACTOR_PLAN.md`、`BASELINE.md`：FastAPI + SQLite 主动 Runtime 的实现和历史计划。
- `implementation_handoff/`：旧本地链的阶段性交接材料。
- `最新分支能力差距审查与测试CASE.md`、`v4测试用例表.md`、`开发日志.md`：v4 本地版审计、测试和开发记录。
- `TRAVEL_MAP_SEARCH_AGENT_REFACTOR_PLAN.md`：地图/日程迁移前的计划；其中多数 Phase 0–3 已实现，剩余事项已并入当前统一计划。

历史文档仍可用于复用领域模型、测试场景和失败经验，但不得把其中“已完成”直接解释为 Makers 线上已可用。
