# Chat、SearchPro 与媒体绑定重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将聊天请求拆成 `ChatTurnController → SearchUseCase → Answer Graph → StreamPresenter`，让一次能力规划只触发一次 SearchPro，并让审核后的图片只通过 `source_id + source_url + 精确引用` 插入，彻底停止新旧占位符和模型自选图片。

**Architecture:** 路由只做 EdgeOne 请求/响应适配；应用层编排一次规划和确定性搜索；领域层保存不可变证据与媒体绑定；基础设施层封装 SearchPro、Maker 证据仓库和后台视觉审核；Presenter 独占 SSE schema。回答模型只消费预取的证据文本，不再拥有 `rich_search` 工具。前端用 Markdown AST 识别精确来源链接并插入已经审核、已经绑定的媒体。

**Tech Stack:** Python 3.11、asyncio、Pydantic、LangGraph/LangChain、EdgeOne Pages Functions、React 18、TypeScript、react-markdown/remark、Vitest、unittest。

## 全局约束

- `main` 必须始终指向 `72be68b2615e7dc23abfbeadca9ce204e3a3c84c`。
- 只在 `dev` 开发；实现前使用 `superpowers:using-git-worktrees` 检查隔离。
- SearchPro 单轮最多调用一次；网页抓取和视觉审核不在首字关键路径。
- 图片必须同时满足 `vision_reviewed=true`、非空 `source_id`、`source_url` 等于该来源 URL，且回答存在该 URL 的精确 Markdown 链接。
- `[[YUANBAO_MEDIA]]`、`[[YUANBAO_MEDIA:n]]` 对新旧消息都不再生效；无法确定绑定的旧图片直接隐藏。
- 模型输出的搜索图片 Markdown 永不直接渲染；生成图片不受此搜索媒体规则影响。
- 缓存只能复用证据包，不能复用最终回答文字。
- 不向用户展示隐藏思维链；只显示结构化阶段、工具、来源数和耗时。

---

## Task 1：建立搜索证据与媒体绑定领域对象

**Files:**

- Create: `agents/_domain/__init__.py`
- Create: `agents/_domain/search/__init__.py`
- Create: `agents/_domain/search/evidence.py`
- Create: `agents/_domain/search/media_binding.py`
- Test: `agents/_tests/search/test_evidence.py`
- Test: `agents/_tests/search/test_media_binding.py`

**Interfaces:**

- Produce: `SearchSource`, `ReviewedMedia`, `SearchEvidence`, `MediaBinding`
- Produce: `bind_reviewed_media(evidence: SearchEvidence) -> tuple[MediaBinding, ...]`
- Invariant: `MediaBinding.source_id` must resolve to exactly one `SearchSource`.

- [ ] Write failing domain tests:

```python
def test_media_requires_review_and_exact_source_url(self):
    evidence = SearchEvidence(
        query="深圳天气",
        sources=(SearchSource(id="source-1", title="气象局", url="https://a.test/1", snippet="晴"),),
        media=(
            ReviewedMedia(
                id="media-1",
                url="https://img.test/1.jpg",
                source_id="source-1",
                source_url="https://a.test/other",
                vision_reviewed=True,
            ),
        ),
    )
    self.assertEqual(bind_reviewed_media(evidence), ())
```

- [ ] Run `python -m unittest agents._tests.search.test_evidence agents._tests.search.test_media_binding -v`; expect import failure for `agents._domain.search`.
- [ ] Implement frozen dataclasses and deterministic binding:

```python
@dataclass(frozen=True, slots=True)
class SearchSource:
    id: str
    title: str
    url: str
    snippet: str
    published_at: str = ""


@dataclass(frozen=True, slots=True)
class ReviewedMedia:
    id: str
    url: str
    source_id: str
    source_url: str
    vision_reviewed: bool
    caption: str = ""


def bind_reviewed_media(evidence: SearchEvidence) -> tuple[MediaBinding, ...]:
    sources = {source.id: source for source in evidence.sources}
    return tuple(
        MediaBinding(media=item, source=sources[item.source_id])
        for item in evidence.media
        if item.vision_reviewed
        and item.source_id in sources
        and item.source_url == sources[item.source_id].url
    )
```

- [ ] Add tests for duplicate source IDs, missing IDs, unreviewed media, exact success, deterministic ordering, and serialization round-trip.
- [ ] Run the two test modules; expect all tests to pass.
- [ ] Commit:

```bash
git add agents/_domain agents/_tests/search
git commit -m "refactor: add deterministic search evidence domain"
```

## Task 2：把 SearchPro 和证据缓存封装成端口

**Files:**

- Create: `agents/_application/search/__init__.py`
- Create: `agents/_application/search/ports.py`
- Create: `agents/_application/search/search_use_case.py`
- Create: `agents/_infrastructure/__init__.py`
- Create: `agents/_infrastructure/providers/__init__.py`
- Create: `agents/_infrastructure/providers/searchpro.py`
- Create: `agents/_infrastructure/makers/__init__.py`
- Create: `agents/_infrastructure/makers/evidence_repository.py`
- Modify: `agents/_shared/rich_search.py`
- Modify: `agents/_shared/evidence_cache.py`
- Test: `agents/_tests/search/test_search_use_case.py`
- Test: `agents/_tests/search/test_searchpro_gateway.py`

**Interfaces:**

- Consume: `CapabilityPlan.search_query`, `image_query`, `strict_today_only`
- Produce: `SearchPort.search(request: SearchRequest) -> SearchEvidence`
- Produce: `EvidenceRepository.get(key)`, `put(key, evidence, ttl_seconds)`
- Produce: `SearchUseCase.execute(plan, identity, on_media) -> SearchExecution`
- `SearchExecution.initial` contains sources and `media_pending`; `completion` is an optional background awaitable.

- [ ] Write a failing test proving cache hits reuse evidence but still return a fresh execution object:

```python
async def test_execute_calls_provider_once_and_never_caches_answer(self):
    provider = FakeSearchPort()
    repository = InMemoryEvidenceRepository()
    use_case = SearchUseCase(provider=provider, repository=repository)
    first = await use_case.execute(self.plan, self.identity)
    second = await use_case.execute(self.plan, self.identity)
    self.assertEqual(provider.calls, 1)
    self.assertIsNot(first, second)
    self.assertFalse(hasattr(first, "answer"))
```

- [ ] Run `python -m unittest agents._tests.search.test_search_use_case -v`; expect import failure.
- [ ] Define request/port contracts:

```python
@dataclass(frozen=True, slots=True)
class SearchRequest:
    query: str
    image_query: str
    depth: str
    target_date: str = ""
    strict_date: bool = False


class SearchPort(Protocol):
    async def search(
        self,
        request: SearchRequest,
        *,
        on_media: Callable[[SearchEvidence], Awaitable[None]] | None = None,
    ) -> SearchExecution: ...
```

- [ ] Implement `SearchProGateway` as the only adapter calling `agents._shared.rich_search.rich_search`; translate dictionaries at the boundary and preserve `provider_request_count=1`.
- [ ] Implement `MakerEvidenceRepository` as an adapter over the existing evidence cache; key only normalized query, plan depth, date boundary and provider version—never prompt text or generated answer.
- [ ] Make `SearchUseCase` choose entitlement depth, perform one repository lookup, call one provider on miss, store the initial evidence, and forward reviewed media updates through `on_media`.
- [ ] Add gateway tests that patch `_json_request` and assert URL ends in `/SearchPro`, call count is one when `image_query != query`, and fallback media with `vision_reviewed=false` is filtered from `SearchEvidence.media`.
- [ ] Run `python -m unittest agents._tests.search.test_search_use_case agents._tests.search.test_searchpro_gateway -v`; expect pass.
- [ ] Commit:

```bash
git add agents/_application/search agents/_infrastructure agents/_shared/rich_search.py agents/_shared/evidence_cache.py agents/_tests/search
git commit -m "refactor: isolate SearchPro behind search use case"
```

## Task 3：建立统一的 Chat SSE Presenter

**Files:**

- Create: `agents/_presenters/__init__.py`
- Create: `agents/_presenters/chat_stream.py`
- Test: `agents/_tests/chat/test_chat_stream_presenter.py`
- Modify: `agents/chat/index.py`

**Interfaces:**

- Produce: `ChatStreamPresenter.stage(name, detail, elapsed_ms)`
- Produce: `sources(evidence)`, `token(text)`, `media(evidence)`, `error(code, message)`, `done(turn_id)`
- Every method returns one complete `event: <name>\ndata: <json>\n\n` frame.

- [ ] Write failing tests for UTF-8 JSON, event order and public progress fields:

```python
def test_stage_exposes_progress_without_hidden_reasoning(self):
    frame = ChatStreamPresenter().stage(
        "searching", {"provider": "SearchPro", "source_count": 0}, 132,
    )
    self.assertIn("event: stage\n", frame)
    self.assertNotIn("chain_of_thought", frame)
    self.assertNotIn("reasoning_content", frame)
```

- [ ] Run `python -m unittest agents._tests.chat.test_chat_stream_presenter -v`; expect import failure.
- [ ] Implement a single serializer:

```python
def _frame(event: str, payload: Mapping[str, Any]) -> str:
    body = json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {body}\n\n"
```

- [ ] Add contract tests for `stage → sources → token* → media? → done`, error terminality, no raw exception, and no hidden-reasoning keys.
- [ ] Replace only the duplicated frame-formatting helpers in `agents/chat/index.py`; keep request orchestration unchanged in this task.
- [ ] Run presenter tests and existing chat tests.
- [ ] Commit:

```bash
git add agents/_presenters agents/chat/index.py agents/_tests/chat
git commit -m "refactor: centralize chat stream presentation"
```

## Task 4：前端移除占位符并使用 Markdown AST 精确绑定

**Files:**

- Create: `frontend/src/features/search/sourceBoundMedia.ts`
- Create: `frontend/src/features/search/sourceBoundMedia.test.ts`
- Modify: `frontend/src/components/common/MarkdownRenderer.tsx`
- Modify: `frontend/src/components/common/MarkdownRenderer.test.tsx`
- Modify: `frontend/src/components/chat/streamingAnswer.ts`
- Modify: `frontend/src/components/chat/streamingAnswer.test.ts`

**Interfaces:**

- Produce: `remarkSourceBoundMedia(options: { sources; media }): Plugin`
- Produce: AST node property `data-source-bound-media="media-id"` only after a paragraph containing the exact source URL.
- Consume only `vision_reviewed === true` media with exact `(source_id, source_url)`.

- [ ] Replace old positive placeholder tests with failing safety tests:

```tsx
it('strips legacy media markers and does not place an image', () => {
  render(<MarkdownRenderer content={'结论[[YUANBAO_MEDIA:1]]'} media={[reviewed]} sources={[source]} />);
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
  expect(screen.queryByText(/YUANBAO_MEDIA/)).not.toBeInTheDocument();
});

it('places reviewed media only after the exact source citation', () => {
  render(<MarkdownRenderer content={'结论 [来源](https://a.test/1)'} media={[reviewed]} sources={[source]} />);
  expect(screen.getByRole('img')).toHaveAttribute('data-source-id', 'source-1');
});
```

- [ ] Run `cd frontend && npm test -- --run src/components/common/MarkdownRenderer.test.tsx src/features/search/sourceBoundMedia.test.ts`; expect failures from current slot behavior/missing module.
- [ ] Implement an AST transformer that:

```ts
const eligible = media.filter((item) =>
  item.vision_reviewed === true &&
  item.source_id &&
  sources.some((source) => source.id === item.source_id && source.url === item.source_url)
);
```

Then traverse paragraph link nodes, match `link.url === source.url`, insert each bound image once immediately after the first exact citation, and mark the image node with trusted `data.hProperties`.

- [ ] Remove `MEDIA_SLOT`, `replaceLegacyMediaSlots`, and all numeric slot selection from `MarkdownRenderer.tsx`; strip legacy marker text before Markdown parsing without turning it into media.
- [ ] Remove `MEDIA_SLOT_PREFIX` buffering from `streamingAnswer.ts`; incomplete legacy markers are treated as ordinary untrusted model text until final sanitization removes them.
- [ ] Make the renderer reject model-authored Markdown image nodes whose URL equals search media unless the AST plugin attached the trusted property; preserve generated-image components.
- [ ] Add tests for wrong URL, wrong source ID, unreviewed media, duplicate citations, redirect-like URLs, model-authored `![](...)`, missing old bindings, and one successful exact binding.
- [ ] Run `cd frontend && npm test -- --run src/components/common/MarkdownRenderer.test.tsx src/components/chat/streamingAnswer.test.ts src/features/search/sourceBoundMedia.test.ts`; expect pass.
- [ ] Commit:

```bash
git add frontend/src/components/common frontend/src/components/chat/streamingAnswer.ts frontend/src/components/chat/streamingAnswer.test.ts frontend/src/features/search
git commit -m "fix: bind reviewed media only to exact source citations"
```

## Task 5：建立 ChatTurnController 并从回答图移除重复搜索决策

**Files:**

- Create: `agents/_application/chat/__init__.py`
- Create: `agents/_application/chat/turn_context.py`
- Create: `agents/_application/chat/turn_controller.py`
- Modify: `agents/chat/index.py`
- Modify: `agents/chat/_graph.py`
- Modify: `agents/chat/_ui_tools.py`
- Test: `agents/_tests/chat/test_turn_controller.py`
- Test: `agents/_tests/chat/test_route_boundary.py`
- Modify: `agents/_tests/test_graph.py`

**Interfaces:**

- Produce: `ChatTurnController.run(request: ChatTurnRequest) -> AsyncIterator[str]`
- Consume: `CapabilityPlanner`, `SearchUseCase`, `AnswerGraph`, `ChatStreamPresenter`
- Produce: `AnswerContext.search_evidence_text`; graph receives it as context and has no `rich_search` tool when evidence was planned.

- [ ] Write a failing orchestration test:

```python
async def test_planned_search_executes_once_before_answer_graph(self):
    controller = build_controller(needs_web_search=True)
    frames = [frame async for frame in controller.run(self.request)]
    self.assertEqual(controller.planner.calls, 1)
    self.assertEqual(controller.search.calls, 1)
    self.assertEqual(controller.graph.calls, 1)
    self.assertNotIn("rich_search", controller.graph.last_tool_names)
    self.assertLess(event_index(frames, "sources"), event_index(frames, "token"))
```

- [ ] Run `python -m unittest agents._tests.chat.test_turn_controller -v`; expect import failure.
- [ ] Implement the controller state machine:

```python
plan = await self._planner.plan(request)
yield self._presenter.stage("planned", public_plan_summary(plan), elapsed())
execution = None
if plan.needs_web_search:
    execution = await self._search.execute(plan, request.identity, on_media=publish_media)
    yield self._presenter.sources(execution.initial)
answer_context = AnswerContext(search_evidence_text=execution.initial.for_model() if execution else "")
async for token in self._graph.answer(request, plan, answer_context, excluded_tools={"rich_search"}):
    yield self._presenter.token(token)
yield self._presenter.done(request.turn_id)
```

- [ ] Add controller tests for clarification, disabled Skill, no-search request, provider error, disconnect cancellation, and background media arriving before or after `done`.
- [ ] Update `_graph.py` so preloaded evidence is placed in the system context and `rich_search` cannot be selected after `needs_web_search` was resolved.
- [ ] Remove the nested `rich_search` tool construction from `_ui_tools.py`; retain a temporary import-compatible wrapper only for tests that have not yet moved, with a deprecation assertion that production tool names exclude it.
- [ ] Reduce `agents/chat/index.py` to request parsing, dependency construction, controller iteration and EdgeOne response creation; add an AST/static test requiring the route handler body to remain below 120 logical lines and forbidding SearchPro/provider imports.
- [ ] Run:

```bash
python -m unittest agents._tests.chat.test_turn_controller agents._tests.chat.test_route_boundary agents._tests.test_graph -v
```

Expected: all pass and the provider fake records exactly one SearchPro call.

- [ ] Commit:

```bash
git add agents/_application/chat agents/chat agents/_tests/chat agents/_tests/test_graph.py
git commit -m "refactor: orchestrate chat search through one controller"
```

## Task 6：关键路径、回归与验收

**Files:**

- Create: `tools/benchmark-search-critical-path.py`
- Create: `agents/_tests/search/test_search_performance_contract.py`
- Modify: `frontend/public/test-cases/cases.json`
- Modify: `frontend/public/test-cases/procedures.js`

- [ ] Add a deterministic latency contract using fake delays: SearchPro 250 ms, answer first token 100 ms, media review 1500 ms; assert first token is emitted below 500 ms and media completion does not block it.
- [ ] Add a 20-query benchmark script that prints p50/p95 for plan, SearchPro, sources event and first token, plus provider request count. The script must redact queries and credentials from persisted output.
- [ ] Run `python tools/benchmark-search-critical-path.py --fake`; expect `provider_requests_per_turn=1` and `first_token_p95_ms<500`.
- [ ] Update manual cases to state: no placeholders, source-bound reviewed media only, visible progress excludes hidden thought, and media may arrive incrementally.
- [ ] Run all relevant suites:

```bash
python -m unittest discover -s agents/_tests -v
cd frontend && npm test
cd frontend && npm run lint
cd frontend && npm run build
```

- [ ] Inspect `git diff --check`, `git status --short`, and `git diff main...dev -- agents/chat agents/_application agents/_domain frontend/src`; confirm no secret, placeholder strategy or direct searched-image rendering remains.
- [ ] Commit:

```bash
git add tools/benchmark-search-critical-path.py agents/_tests/search frontend/public/test-cases
git commit -m "test: enforce search critical path and media safety"
```

## 本计划完成定义

- 一轮能力规划、一轮 SearchPro、一轮回答模型；回答模型没有重复搜索工具。
- 首字等待 SearchPro 文本证据，但不等待网页抓取或视觉审核。
- 旧新消息都不使用媒体占位符；不确定的旧媒体不可见。
- 所有搜索图片均由代码验证 `vision_reviewed + source_id + source_url + 精确引用`。
- SSE 只公开结构化进度，不公开隐藏思维链。
- Python、Vitest、lint、TypeScript build 全部通过。
