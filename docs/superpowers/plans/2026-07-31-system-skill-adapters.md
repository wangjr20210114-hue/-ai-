# 系统 Skill Adapter 与组件 API 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让九个内置 Skill 从“清单声明中央函数”升级为真正可独立发现、校验和装载的系统 Skill；每个 Skill 只能通过受权限约束的 Adapter、Maker 句柄和版本化网站组件 API 访问能力。

**Architecture:** `floris.json + SKILL.md` 是 Skill 包边界，`agents/_skill_adapters/<skill_id>/adapter.py` 是唯一可信系统执行入口。注册表校验 manifest、依赖、权限、Adapter 路径和返回工具名；`SkillRuntimeContext` 只暴露 manifest 声明的 Maker/业务端口。用户上传 Skill 只进入 `pending_review`，不会导入 Python 或执行。中央 `_ui_tools.build_production_tools` 按迁移批次缩小，最终删除。

**Tech Stack:** Python 3.11、LangChain StructuredTool、JSON manifest、EdgeOne Makers state/checkpointer/blob/model/trace、unittest。

## 全局约束

- 系统 Skill Adapter 只允许 `agents._skill_adapters.*:build_tools`。
- Guest 只可启用 `core` 与 `proactive-agent`；其它 Skill 即使 manifest 默认开启也必须被权益层屏蔽。
- 依赖是有向无环图；依赖未安装/未启用时，依赖项不可执行且返回结构化原因。
- manifest 的 `tools`、`component_actions`、`permissions` 是运行时白名单，不是说明文字。
- 系统 Skill 可以调用网站组件；第三方 Skill 只能调用审核后授予的组件动作。
- 用户 Skill 上传保持 `pending_review`，本计划不实现自动审核或后台管理。
- 不在 Adapter 中自行实现 Maker 已提供的数据隔离、模型、Blob、checkpointer 或 trace。

---

## Task 1：收紧注册表和 Adapter 信任边界

**Files:**

- Modify: `agents/_shared/skill_registry.py`
- Create: `agents/_tests/skills/test_adapter_security.py`
- Modify: `agents/_tests/test_workspace.py`

**Interfaces:**

- Produce: `validate_adapter_entrypoint(manifest: SkillManifest) -> None`
- Produce: `build_adapter_tools(runtime, enabled_skills) -> list[BaseTool]`
- Enforce returned tool set equals required declared tools and is a subset of all declared tools.

- [ ] Write failing tests:

```python
def test_system_adapter_must_live_under_trusted_package(self):
    raw = manifest_dict(
        id="maps",
        kind="system",
        adapter="agents.chat._ui_tools:build_tools",
    )
    with self.assertRaisesRegex(ValueError, "trusted system adapter"):
        parse_manifest_for_test(raw)

def test_user_skill_adapter_is_never_imported(self):
    manifest = user_manifest(status="pending_review", adapter="evil.module:run")
    tools = build_adapter_tools(self.runtime, [manifest.id])
    self.assertEqual(tools, [])
```

- [ ] Run `python -m unittest agents._tests.skills.test_adapter_security -v`; expect missing module or current permissive behavior.
- [ ] Add path validation:

```python
SYSTEM_ADAPTER_PREFIX = "agents._skill_adapters."

def validate_adapter_entrypoint(manifest: SkillManifest) -> None:
    if manifest.kind == "system" and manifest.adapter:
        module, separator, function = manifest.adapter.partition(":")
        if not separator or not module.startswith(SYSTEM_ADAPTER_PREFIX) or function != "build_tools":
            raise ValueError(f"Skill {manifest.id} must use a trusted system adapter")
    if manifest.kind != "system" and manifest.adapter:
        raise ValueError(f"Unreviewed Skill {manifest.id} cannot declare an executable adapter")
```

- [ ] Reject duplicate tool ownership, duplicate component actions, undeclared returned tools, missing required returned tools, cyclic `requires`, and adapters for `pending_review`.
- [ ] Add a runtime import allowlist translation for EdgeOne’s `pages_agents._skill_adapters` package without weakening source-path validation.
- [ ] Run the adapter security tests and the existing registry tests.
- [ ] Commit:

```bash
git add agents/_shared/skill_registry.py agents/_tests/skills agents/_tests/test_workspace.py
git commit -m "security: enforce trusted system Skill adapters"
```

## Task 2：把运行时上下文改成最小权限端口

**Files:**

- Create: `agents/_application/skills/__init__.py`
- Create: `agents/_application/skills/runtime_ports.py`
- Modify: `agents/_shared/skill_registry.py`
- Modify: `agents/_shared/component_api.py`
- Test: `agents/_tests/skills/test_runtime_context.py`
- Test: `agents/_tests/skills/test_component_api.py`

**Interfaces:**

- Produce: `SkillServices(search, maps, calendar, meeting, image, vision, papers, workspace)`
- Produce: `SkillRuntimeContext.service(name)`, `.component(action)`, existing Maker handles
- Produce component envelope: `{version, action, request_id, tenant_id, user_id, payload}`

- [ ] Write a failing test proving an Adapter cannot obtain undeclared services or components:

```python
def test_context_denies_undeclared_service_and_component(self):
    context = SkillRuntimeContext(self.web_manifest, self.runtime)
    with self.assertRaises(PermissionError):
        context.service("calendar")
    with self.assertRaises(PermissionError):
        context.component("calendar.change.propose")
```

- [ ] Run `python -m unittest agents._tests.skills.test_runtime_context -v`; expect missing `service`.
- [ ] Define typed service protocols in `runtime_ports.py`, including:

```python
class SearchService(Protocol):
    async def search(self, request: SearchRequest, *, on_media=None) -> SearchExecution: ...

class WorkspaceService(Protocol):
    async def propose(self, kind: str, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...
```

- [ ] Map each service to a permission; `SkillRuntimeContext.service()` checks both permission and callable/port availability before returning it.
- [ ] Version component calls with `COMPONENT_API_VERSION`; validate required payload fields before dispatch and always attach signed identity from runtime, never identity supplied by the model.
- [ ] Add tests for environment key filtering, Maker handle permissions, signed identity override prevention, unknown component action, and schema version.
- [ ] Run runtime/component tests and existing workspace tests.
- [ ] Commit:

```bash
git add agents/_application/skills agents/_shared/skill_registry.py agents/_shared/component_api.py agents/_tests/skills
git commit -m "refactor: expose least-privilege Skill runtime ports"
```

## Task 3：迁移 web-search、vision 和 image-studio

**Files:**

- Create: `agents/_skill_adapters/__init__.py`
- Create: `agents/_skill_adapters/web_search/__init__.py`
- Create: `agents/_skill_adapters/web_search/adapter.py`
- Create: `agents/_skill_adapters/vision/__init__.py`
- Create: `agents/_skill_adapters/vision/adapter.py`
- Create: `agents/_skill_adapters/image_studio/__init__.py`
- Create: `agents/_skill_adapters/image_studio/adapter.py`
- Modify: `agents/skill_packages/web-search/floris.json`
- Modify: `agents/skill_packages/vision/floris.json`
- Modify: `agents/skill_packages/image-studio/floris.json`
- Modify: `agents/chat/_ui_tools.py`
- Test: `agents/_tests/skills/test_search_image_adapters.py`

**Interfaces:**

- Each module exports `build_tools(context: SkillRuntimeContext) -> Sequence[BaseTool]`.
- Web search calls `context.service("search")`; it does not call HTTP/provider code.
- Vision and image generation call their own service ports and publish through allowed components.

- [ ] Write failing tests that load all three manifests, build adapters, and compare returned names with declared required names.
- [ ] Run `python -m unittest agents._tests.skills.test_search_image_adapters -v`; expect no adapters.
- [ ] Implement the web-search factory:

```python
def build_tools(context: SkillRuntimeContext) -> Sequence[BaseTool]:
    search = context.service("search")

    async def rich_search(query: str, image_query: str = "", depth: str = "standard") -> str:
        execution = await search.search(
            SearchRequest(query=query, image_query=image_query, depth=depth)
        )
        return execution.initial.for_model()

    return (StructuredTool.from_function(
        coroutine=rich_search,
        name="rich_search",
        description="Search current external evidence once and return citable sources.",
    ),)
```

- [ ] Add manifest `adapter` values:

```json
"adapter": "agents._skill_adapters.web_search.adapter:build_tools"
```

Use corresponding underscored package names for vision and image-studio.
- [ ] Move only tool construction from `_ui_tools.py`; provider logic remains behind application service ports. Remove migrated nested tool definitions and assert names occur only in adapters/tests/manifests.
- [ ] Add tests that disabled Skill returns no tools, missing env degrades cleanly, and web search cannot access image-generation service.
- [ ] Run adapter, graph and chat search tests.
- [ ] Commit:

```bash
git add agents/_skill_adapters agents/skill_packages agents/chat/_ui_tools.py agents/_tests/skills
git commit -m "refactor: migrate search and image Skills to adapters"
```

## Task 4：迁移 maps、calendar 和 tencent-meeting

**Files:**

- Create: `agents/_skill_adapters/maps/__init__.py`
- Create: `agents/_skill_adapters/maps/adapter.py`
- Create: `agents/_skill_adapters/calendar/__init__.py`
- Create: `agents/_skill_adapters/calendar/adapter.py`
- Create: `agents/_skill_adapters/tencent_meeting/__init__.py`
- Create: `agents/_skill_adapters/tencent_meeting/adapter.py`
- Modify: `agents/skill_packages/maps/floris.json`
- Modify: `agents/skill_packages/calendar/floris.json`
- Modify: `agents/skill_packages/tencent-meeting/floris.json`
- Modify: `agents/chat/_ui_tools.py`
- Test: `agents/_tests/skills/test_action_adapters.py`

**Interfaces:**

- Maps service returns provider-verified place/route value objects.
- Calendar and meeting mutations return proposals; confirmation and side effects remain application policies.
- Adapter may publish `maps.place.select` or `calendar.change.propose`, but cannot write Maker state directly unless its manifest grants the exact permission.

- [ ] Write failing tests asserting exact manifest/tool parity for all map/calendar/meeting tools.
- [ ] Add a failing test that calling a calendar mutation produces a proposal and performs zero writes before confirmation.
- [ ] Run `python -m unittest agents._tests.skills.test_action_adapters -v`; expect adapter import failures.
- [ ] Implement factories that are thin closures over `context.service(...)`; keep current argument schemas and result JSON stable.
- [ ] Add manifest adapters and the minimum service/component permissions actually used. Do not add `components.system` when a narrower component permission exists.
- [ ] Delete migrated nested functions from `_ui_tools.py`: location, place search/batch, nearby, route, map preparation/recommendation, calendar and meeting tool construction.
- [ ] Run action adapter tests plus existing route/calendar/workspace confirmation tests.
- [ ] Commit:

```bash
git add agents/_skill_adapters agents/skill_packages agents/chat/_ui_tools.py agents/_tests/skills
git commit -m "refactor: migrate map calendar and meeting Skills"
```

## Task 5：迁移 core、paper-reading 和 proactive-agent

**Files:**

- Create: `agents/_skill_adapters/core/__init__.py`
- Create: `agents/_skill_adapters/core/adapter.py`
- Create: `agents/_skill_adapters/paper_reading/__init__.py`
- Create: `agents/_skill_adapters/paper_reading/adapter.py`
- Create: `agents/_skill_adapters/proactive_agent/__init__.py`
- Create: `agents/_skill_adapters/proactive_agent/adapter.py`
- Modify: `agents/skill_packages/core/floris.json`
- Modify: `agents/skill_packages/paper-reading/floris.json`
- Modify: `agents/skill_packages/proactive-agent/floris.json`
- Modify: `agents/chat/_ui_tools.py`
- Test: `agents/_tests/skills/test_core_paper_proactive_adapters.py`

**Interfaces:**

- Core owns clarification and safe workflow proposal tools.
- Paper reading owns arXiv/search/reader preparation tools.
- Proactive agent owns opportunity review and its existing preference hook.

- [ ] Write failing manifest parity, Guest access and dependency tests.
- [ ] Run the new test module; expect adapter import failures.
- [ ] Implement three adapter factories with the same least-privilege service pattern.
- [ ] Add manifest adapter entries; preserve proactive preference hook and its default/locked policy.
- [ ] Remove the remaining migrated nested production tools from `_ui_tools.py`.
- [ ] Verify Guest runtime returns tools only from `core` and `proactive-agent`; authenticated free/plus/pro runtime follows required plan and preferences.
- [ ] Run all Skill, capability-plan, graph and workspace tests.
- [ ] Commit:

```bash
git add agents/_skill_adapters agents/skill_packages agents/chat/_ui_tools.py agents/_tests/skills
git commit -m "refactor: complete system Skill adapter migration"
```

## Task 6：删除中央工具工厂并建立 Skill 完整性门禁

**Files:**

- Delete: `agents/chat/_ui_tools.py`
- Modify: `agents/chat/_graph.py`
- Create: `tools/assert-skill-integrity.py`
- Create: `agents/_tests/skills/test_all_system_skills.py`
- Modify: `package.json`
- Modify: `.github/workflows/deploy.yml`

- [ ] Add a failing repository test that rejects imports of `agents.chat._ui_tools` and rejects any system manifest without Adapter.
- [ ] Add a tool-integrity test:

```python
def test_every_system_skill_builds_exact_declared_tools(self):
    for manifest in skill_manifests():
        if manifest.kind != "system":
            continue
        built = build_adapter_tools(runtime_for(manifest), [manifest.id, *manifest.requires])
        returned = {tool.name for tool in built}
        declared = {tool.name for tool in manifest.tools}
        required = {tool.name for tool in manifest.tools if tool.required}
        self.assertTrue(required.issubset(returned))
        self.assertTrue(returned.issubset(declared))
```

- [ ] Run the integrity test; expect failure while `_graph.py` still imports the central factory.
- [ ] Change `_graph.py` to use only `build_adapter_tools(runtime, enabled_skills)`.
- [ ] Delete `_ui_tools.py` after `rg -n "_ui_tools|build_production_tools" agents frontend tools` shows only the failing guards.
- [ ] Implement `tools/assert-skill-integrity.py` to validate manifests, unique ownership, DAG order, trusted paths, required returns, component permissions, Guest policy and `pending_review` non-execution.
- [ ] Add root script `check:skills` and invoke it in CI before build.
- [ ] Run:

```bash
python tools/assert-skill-integrity.py
python -m unittest agents._tests.skills.test_all_system_skills -v
python -m unittest discover -s agents/_tests -v
```

- [ ] Commit:

```bash
git add -A agents/chat/_ui_tools.py agents/chat/_graph.py agents/_skill_adapters agents/_tests/skills tools/assert-skill-integrity.py package.json .github/workflows/deploy.yml
git commit -m "refactor: make system Skills the only production tool source"
```

## 本计划完成定义

- 九个系统 Skill 都有标准包、manifest、可信 Adapter 和精确权限。
- 工具清单由各 Skill 自己产生，中央 `_ui_tools.py` 不存在。
- 依赖图、权益、开关、环境配置、工具所有权在加载时确定性校验。
- Guest 只能执行两个必开 Skill。
- 用户上传 Skill 始终不可执行，直到未来审核状态和后台管理明确放行。
- 系统/第三方 Skill 都通过版本化组件 API，而不是直接操作前端或绕过确认策略。
