# 前端 Feature MVC 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将聊天、搜索、日程、地图、论文和设置从跨目录耦合的大组件/大 Hook 拆成独立 Feature MVC，同时保持现有用户行为、SSE 协议和 Skill 广场路由。

**Architecture:** `app/` 只组合页面、全局 Provider 和路由；每个 `features/<name>/` 包含 model（类型/纯 reducer）、controller（Hook/用例）、view（组件）；`shared/` 只包含通用 transport、UI 和无业务类型。Feature 不跨层导入另一个 Feature 的 view/controller；跨 Feature 通过 app composition 或显式公共 model 事件协作。网络请求按业务拆成 client，`services/api.ts` 最终删除。

**Tech Stack:** React 18、TypeScript 5.6、Vite、Vitest、Testing Library、SSE。

## 全局约束

- 本计划不重做 UI 视觉设计；组件 DOM 语义、i18n key 和主要 class 名在 CSS 迁移前保持稳定。
- 搜索媒体继续遵守 `source_id` 精确绑定；前端 MVC 不能绕过媒体安全转换器。
- 所有请求继续使用 EdgeOne 签名 session；Feature 不自行拼接 tenant/user。
- Chat Controller 只显示结构化进度，不显示原始 reasoning/chain-of-thought。
- Skill 广场是独立大页面，必须能返回聊天主界面；现有 `/skill_marketplace` Maker 安全路由保持不变。
- 每次只迁移一个 Feature，并保留行为测试后再删除旧导出。

## 目标目录

```text
frontend/src/
  app/
    App.tsx
    AppProviders.tsx
    routes.ts
    store/
  features/
    chat/{model,controller,view}/
    search/{model,controller,view}/
    calendar/{model,controller,view}/
    maps/{model,controller,view}/
    papers/{model,controller,view}/
    settings/{model,controller,view}/
    skills/{model,controller,view}/
  shared/
    auth/
    transport/
    ui/
    types/
```

---

## Task 1：建立前端依赖边界和共享 transport

**Files:**

- Create: `frontend/src/shared/transport/httpClient.ts`
- Create: `frontend/src/shared/transport/sseClient.ts`
- Create: `frontend/src/shared/auth/session.ts`
- Create: `frontend/src/shared/types/common.ts`
- Create: `frontend/scripts/check-feature-boundaries.mjs`
- Create: `frontend/src/shared/transport/transport.test.ts`
- Modify: `frontend/package.json`

**Interfaces:**

- Produce: `requestJson<T>(path, init) -> Promise<T>`
- Produce: `streamEvents(path, init, handlers, signal) -> Promise<void>`
- Produce: `withSession(path) -> string`
- Boundary rule: shared imports no Feature; Feature model imports shared only; controller imports own model/shared/other Feature model contracts; view imports own model/controller/shared UI.

- [ ] Write failing transport tests for credentials, auth URL decoration, non-2xx typed errors, split SSE chunks, UTF-8 and abort.
- [ ] Run `cd frontend && npm test -- --run src/shared/transport/transport.test.ts`; expect missing modules.
- [ ] Move the generic fetch/SSE mechanics from `services/auth.ts` and `services/sse.ts` into the three shared modules while preserving compatibility re-exports.
- [ ] Implement `check-feature-boundaries.mjs` by parsing import specifiers and rejecting:

```js
assertImportAllowed('features/chat/model/x.ts', 'features/maps/view/Map.tsx') === false;
assertImportAllowed('features/chat/controller/x.ts', 'features/search/model/events.ts') === true;
assertImportAllowed('shared/ui/Button.tsx', 'features/chat/model/x.ts') === false;
```

- [ ] Add `check:boundaries` to frontend scripts and a unit fixture for allowed/forbidden imports.
- [ ] Run transport tests, current SSE tests and boundary script.
- [ ] Commit:

```bash
git add frontend/src/shared frontend/scripts/check-feature-boundaries.mjs frontend/package.json
git commit -m "refactor: establish frontend feature boundaries"
```

## Task 2：按业务拆分 API client 和类型

**Files:**

- Create: `frontend/src/features/chat/model/types.ts`
- Create: `frontend/src/features/chat/model/client.ts`
- Create: `frontend/src/features/search/model/types.ts`
- Create: `frontend/src/features/search/model/client.ts`
- Create: `frontend/src/features/calendar/model/types.ts`
- Create: `frontend/src/features/calendar/model/client.ts`
- Create: `frontend/src/features/maps/model/types.ts`
- Create: `frontend/src/features/maps/model/client.ts`
- Create: `frontend/src/features/papers/model/types.ts`
- Create: `frontend/src/features/papers/model/client.ts`
- Create: `frontend/src/features/settings/model/types.ts`
- Create: `frontend/src/features/settings/model/client.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/features/clients.test.ts`

**Interfaces:**

- Chat client: conversation/messages/stop/reset/chat stream.
- Search client: search metadata/media event decoding only; actual chat transport remains Chat client.
- Calendar client: workspace calendar proposals/confirmations.
- Maps client: place, route and map projections.
- Papers client: search, library, reader.
- Settings client: current user, entitlements, provider usage, reset.

- [ ] Write failing route-ownership tests:

```ts
expect(chatClient.routes).toEqual(['/chat', '/conversation', '/messages', '/stop']);
expect(papersClient.routes.every((route) => ['/papers', '/reader', '/library'].includes(route))).toBe(true);
expect(allOwnedRoutes).toHaveLength(new Set(allOwnedRoutes).size);
```

- [ ] Run `cd frontend && npm test -- --run src/features/clients.test.ts`; expect missing clients.
- [ ] Move types out of `types/index.ts` by aggregate; export only stable public contracts from each feature `model/index.ts`.
- [ ] Move endpoint functions from `services/api.ts` into the six clients. Every client must use `requestJson`/`streamEvents`, not direct `fetch`.
- [ ] Leave named re-exports in old files temporarily and migrate imports feature by feature.
- [ ] Add response parser tests that reject malformed media/source IDs and preserve unknown forward-compatible event fields.
- [ ] Run all service/client/type tests and `npm run build`.
- [ ] Commit:

```bash
git add frontend/src/features frontend/src/services/api.ts frontend/src/types/index.ts
git commit -m "refactor: split frontend clients and domain types"
```

## Task 3：拆分 Chat 与 Search model/controller

**Files:**

- Create: `frontend/src/features/chat/model/state.ts`
- Create: `frontend/src/features/chat/model/events.ts`
- Create: `frontend/src/features/chat/controller/useChatTransport.ts`
- Create: `frontend/src/features/chat/controller/useConversationLifecycle.ts`
- Create: `frontend/src/features/chat/controller/useChatController.ts`
- Create: `frontend/src/features/search/model/progress.ts`
- Create: `frontend/src/features/search/controller/useSearchProgress.ts`
- Move: `frontend/src/features/chat/progressModel.ts` → `frontend/src/features/search/model/progressModel.ts`
- Modify: `frontend/src/hooks/useSSEChat.ts`
- Modify: `frontend/src/hooks/useSSEChat.test.ts`
- Create: `frontend/src/features/chat/controller/useChatController.test.ts`

**Interfaces:**

- `useChatTransport`: one request lifecycle and SSE decoding.
- `useConversationLifecycle`: load/switch/delete/reset conversation.
- `useSearchProgress`: reduce `stage/sources/media` events.
- `useChatController`: compose the three and expose the existing `useSSEChat` public return shape.

- [ ] Write a failing controller test proving search progress, answer tokens and media updates reduce independently:

```ts
controller.receive(stageEvent('searching'));
controller.receive(tokenEvent('答'));
controller.receive(mediaEvent(reviewedMedia));
expect(controller.state.progress.stage).toBe('searching');
expect(controller.state.streamingText).toBe('答');
expect(controller.state.search.media).toEqual([reviewedMedia]);
```

- [ ] Run focused Chat controller tests; expect missing controller.
- [ ] Extract pure event reducer first; unknown events are ignored, terminal error/done is deterministic, and no `reasoning_content` field is accepted into UI state.
- [ ] Extract transport timeout/abort/stop behavior from `useSSEChat.ts` into `useChatTransport`.
- [ ] Extract conversation restore/interruption/manual-stop behavior into `useConversationLifecycle`.
- [ ] Make `useSSEChat.ts` a thin compatibility wrapper:

```ts
export { useChatController as useSSEChat } from '../features/chat/controller/useChatController';
```

- [ ] Keep all current hook tests, re-home them by responsibility, and add a file-size guard requiring each controller file below 350 lines.
- [ ] Run Chat/Search tests, lint and build.
- [ ] Commit:

```bash
git add frontend/src/features/chat frontend/src/features/search frontend/src/hooks
git commit -m "refactor: split chat transport and search progress controllers"
```

## Task 4：把 MessageBubble 拆成可注册的内容 View

**Files:**

- Create: `frontend/src/features/chat/view/MessageBubble.tsx`
- Create: `frontend/src/features/chat/view/renderers/rendererRegistry.ts`
- Create: `frontend/src/features/chat/view/renderers/TextRenderer.tsx`
- Create: `frontend/src/features/search/view/SearchEvidenceRenderer.tsx`
- Create: `frontend/src/features/calendar/view/CalendarRenderer.tsx`
- Create: `frontend/src/features/maps/view/MapRenderer.tsx`
- Create: `frontend/src/features/papers/view/PaperRenderer.tsx`
- Create: `frontend/src/features/chat/view/ActionRenderer.tsx`
- Modify: `frontend/src/components/chat/MessageBubble.tsx`
- Modify: `frontend/src/components/chat/MessageBubble.test.ts`
- Create: `frontend/src/features/chat/view/rendererRegistry.test.tsx`

**Interfaces:**

```ts
export interface MessageContentRenderer {
  id: string;
  canRender(message: ChatMessage): boolean;
  render(message: ChatMessage, context: MessageViewContext): ReactNode;
}
```

- [ ] Write a failing registry test asserting deterministic priority and fallback:

```tsx
expect(selectRenderer(searchMessage).id).toBe('search-evidence');
expect(selectRenderer(paperMessage).id).toBe('paper');
expect(selectRenderer(plainMessage).id).toBe('text');
```

- [ ] Run registry/MessageBubble tests; expect missing registry.
- [ ] Implement an explicit immutable renderer array; never infer renderer by raw HTML or arbitrary model strings.
- [ ] Move existing JSX blocks from the 1194-line component to the six typed renderers without changing data semantics.
- [ ] Ensure `SearchEvidenceRenderer` delegates Markdown/media handling to the source-bound transformer from the search/media plan.
- [ ] Make old `components/chat/MessageBubble.tsx` a re-export, then update call sites.
- [ ] Add tests for mixed content, unknown action, empty response, source cards, reviewed media, map, paper and calendar.
- [ ] Run focused tests, lint and build; require no renderer file above 300 lines.
- [ ] Commit:

```bash
git add frontend/src/features frontend/src/components/chat/MessageBubble.tsx frontend/src/components/chat/MessageBubble.test.ts
git commit -m "refactor: split message content renderers"
```

## Task 5：完成 calendar、maps、papers、settings 和 skills MVC

**Files:**

- Move/Modify: `frontend/src/components/travel/RouteMap.tsx`
- Move/Modify: `frontend/src/components/travel/TravelPlanCard.tsx`
- Move/Modify: `frontend/src/components/paper/*`
- Move/Modify: `frontend/src/components/profile/ReadingLibraryPanel.tsx`
- Move/Modify: `frontend/src/components/profile/EdgeOnePlatformPanel.tsx`
- Move/Modify: `frontend/src/components/profile/ProactiveBriefPanel.tsx`
- Move/Modify: `frontend/src/components/profile/SkillsMarketplaceButton.tsx`
- Modify: `frontend/src/features/skills/useSkillMarketplaceController.ts`
- Create: `frontend/src/features/calendar/controller/useCalendarController.ts`
- Create: `frontend/src/features/maps/controller/useMapsController.ts`
- Create: `frontend/src/features/papers/controller/usePapersController.ts`
- Create: `frontend/src/features/settings/controller/useSettingsController.ts`
- Create: `frontend/src/features/skills/view/SkillsMarketplacePage.tsx`
- Create: per-feature controller tests.

- [ ] For each Feature, write a failing controller test before moving its component: model transition, client call, error state and retry.
- [ ] Migrate maps: verified places/routes are model types; map view never fetches provider data.
- [ ] Migrate calendar: proposals and confirmations stay separate states; view cannot directly apply a mutation.
- [ ] Migrate papers: search, history/library and reader loading become controller actions; PDF utility stays shared only if business-neutral.
- [ ] Migrate settings: session, entitlement, provider usage and reset actions have one controller; membership checkout remains disabled.
- [ ] Expand Skills marketplace into a full page with catalog, installed/download/install states, dependency graph, docs link, upload status and a visible “返回主界面” action. Upload produces only `pending_review`.
- [ ] Add Skill dependency graph tests: missing prerequisite disables install, install order is topological, cycle is shown as invalid data.
- [ ] Run all five Feature suites, lint and build.
- [ ] Commit:

```bash
git add frontend/src/features frontend/src/components/travel frontend/src/components/paper frontend/src/components/profile
git commit -m "refactor: complete frontend feature MVC"
```

## Task 6：收敛 App composition、状态切片和旧目录

**Files:**

- Create: `frontend/src/app/App.tsx`
- Create: `frontend/src/app/AppProviders.tsx`
- Create: `frontend/src/app/routes.ts`
- Create: `frontend/src/app/store/rootReducer.ts`
- Create: `frontend/src/app/store/types.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/store/AppContext.tsx`
- Modify: `frontend/src/store/appState.ts`
- Modify: `frontend/src/main.tsx`
- Delete: `frontend/src/services/api.ts`
- Delete: `frontend/src/types/index.ts`
- Delete: `frontend/src/hooks/useSSEChat.ts`
- Delete obsolete component re-export files after imports are migrated.
- Create: `frontend/scripts/check-legacy-front-end.mjs`

- [ ] Write failing app integration tests for `/chatBot/` main view, Skills page entry/return, conversation selection and right-panel routing.
- [ ] Split global state into `session`, `navigation` and feature-owned states; root reducer only delegates actions.
- [ ] Make root `App.tsx` a compatibility re-export during migration, then update `main.tsx` to import `app/App`.
- [ ] Run `rg -n "src/(services/api|types/index|hooks/useSSEChat)|components/(travel|paper|profile)" frontend/src`; update every import.
- [ ] Delete legacy files only when the grep is empty.
- [ ] Implement a guard that rejects new imports from deleted paths and rejects direct `fetch(` outside `shared/transport`.
- [ ] Run:

```bash
cd frontend
npm run check:boundaries
npm test
npm run lint
npm run build
```

- [ ] Commit:

```bash
git add -A frontend/src frontend/scripts frontend/package.json
git commit -m "refactor: finish frontend feature MVC composition"
```

## 本计划完成定义

- 六个核心 Feature 均有 model/controller/view；Skills 页面也遵循相同结构。
- `useSSEChat.ts`、1194 行 `MessageBubble.tsx`、聚合 `services/api.ts` 和 `types/index.ts` 均已退出。
- 网络、身份和 SSE 只有 shared transport 一处实现。
- Feature 边界脚本、全部 Vitest、lint 和 build 通过。
- 用户行为、精确媒体绑定、确认式副作用和 Skill 权益没有被重构绕过。
