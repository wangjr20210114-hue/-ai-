# CSS、测试拆分与独立 Maker 发布门禁实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 拆分 4336 行全局 CSS 和 6485 行单体 Python 测试，建立架构/路由/浏览器/性能门禁，并确保最终只从干净的 `dev` 提交部署到独立 Maker 项目 `floris-mvc-dev-5925b93`。

**Architecture:** 设计 token 和 reset 保持全局；布局与六个 Feature 样式由各 Feature 拥有；响应式和 reduced-motion 跟随对应样式。Python 测试按领域拆成独立套件并共享明确的 fake/factory。CI 先运行生成 Contract 和静态架构门禁，再运行单元、前端、EdgeOne build route 和浏览器冒烟。部署脚本同时校验 Git branch/commit、`.edgeone/project.json` 和 Maker 项目 ID。

**Tech Stack:** CSS、React/Vite、Python unittest、Node test runner、Vitest、Playwright、EdgeOne Makers CLI、GitHub Actions。

## 全局约束

- `main` 与 `origin/main` 必须保持 `712fe07a1b41dc1ce2ba316838bba0e2d111d32a`。
- 只部署 `Name=floris-mvc-dev-5925b93`、`ProjectId=makers-x91pbqwetj8l`。
- 任何脚本都不能接受或推导 `ai-active-agent-floris` 为部署目标。
- 部署源必须是已推送、无未提交变更的 `dev` HEAD；`.edgeone` 必须由该 HEAD 构建。
- UI 可访问性、浅/深主题、移动端、reduced-motion 和中文/英文不因 CSS 拆分退化。
- 单元测试迁移不能靠减少断言或跳过；旧的公开手工用例命令必须同步更新。

---

## Task 1：建立样式入口、token 和拆分前视觉基线

**Files:**

- Create: `frontend/src/styles/index.css`
- Create: `frontend/src/styles/tokens.css`
- Create: `frontend/src/styles/reset.css`
- Create: `frontend/src/styles/layout.css`
- Create: `frontend/src/styles/motion.css`
- Create: `frontend/e2e/visual-baseline.spec.ts`
- Create: `frontend/playwright.config.ts`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

- [ ] Install Playwright test dependency with `cd frontend && npm install --save-dev @playwright/test`; commit the lockfile change only after tests run.
- [ ] Write failing visual smoke tests for desktop light, desktop dark, 390px mobile, reduced motion, Skills page and a restored rich answer.
- [ ] Run `cd frontend && npx playwright test e2e/visual-baseline.spec.ts`; expect missing config/fixtures.
- [ ] Configure Playwright `webServer` to run Vite on a fixed local port and use deterministic mocked API/SSE fixtures—never production user data.
- [ ] Copy only global tokens/theme/root reset/layout sections from `index.css` into the new files without selector changes. Import them from `styles/index.css`.
- [ ] Point `main.tsx` to `styles/index.css`, while `styles/index.css` temporarily imports legacy `../index.css` last so screenshots remain unchanged.
- [ ] Capture and review baselines for the six required viewports/states.
- [ ] Run frontend tests, lint, build and visual tests.
- [ ] Commit:

```bash
git add frontend/src/styles frontend/src/main.tsx frontend/e2e frontend/playwright.config.ts frontend/package.json frontend/package-lock.json
git commit -m "test: establish visual baselines before CSS split"
```

## Task 2：按 Feature 拆分全局 CSS

**Files:**

- Create: `frontend/src/features/chat/styles.css`
- Create: `frontend/src/features/search/styles.css`
- Create: `frontend/src/features/calendar/styles.css`
- Create: `frontend/src/features/maps/styles.css`
- Create: `frontend/src/features/papers/styles.css`
- Create: `frontend/src/features/settings/styles.css`
- Create: `frontend/src/features/skills/styles.css`
- Create: `frontend/src/features/image-studio/styles.css`
- Create: `frontend/src/shared/ui/styles.css`
- Modify: `frontend/src/styles/index.css`
- Delete: `frontend/src/index.css`
- Create: `frontend/scripts/check-css-ownership.mjs`

**Ownership map:**

| Legacy section | Owner |
|---|---|
| chat shell, message, input, follow-up, clarification | `features/chat/styles.css` |
| source cards, citations, reviewed media, search progress | `features/search/styles.css` |
| calendar grid/day/timeline/proposal | `features/calendar/styles.css` |
| Makers itinerary, places, routes, map | `features/maps/styles.css` |
| paper discovery/reader/library | `features/papers/styles.css` |
| settings/profile/provider usage/onboarding | `features/settings/styles.css` |
| marketplace/catalog/dependency graph | `features/skills/styles.css` |
| generation cards/studio | `features/image-studio/styles.css` |
| generic panel/button/skeleton/scrollbar | `shared/ui/styles.css` |

- [ ] Write a failing CSS ownership test that rejects duplicate selectors across Feature files, legacy “媒体槽” comments, and any file over 900 lines.
- [ ] Run `cd frontend && node scripts/check-css-ownership.mjs`; expect missing script/current monolith.
- [ ] Move selectors in ownership order, including adjacent responsive/reduced-motion rules in the same file; do not duplicate a base selector to make the move easier.
- [ ] Import files once in `styles/index.css` in stable cascade order: tokens, reset, shared UI, layout, Features, motion overrides.
- [ ] Remove the obsolete comment “由模型通过媒体槽决定所在段落” and describe exact source-bound media instead.
- [ ] After each Feature move, run its component tests and the visual suite; accept screenshot updates only after inspecting the rendered diff.
- [ ] Delete `index.css` after `rg -n "index\\.css" frontend/src` shows only the new styles entry.
- [ ] Run CSS guard, all Vitest, lint, build and Playwright.
- [ ] Commit:

```bash
git add -A frontend/src/index.css frontend/src/styles frontend/src/features frontend/src/shared/ui frontend/scripts/check-css-ownership.mjs
git commit -m "refactor: split global CSS by feature ownership"
```

## Task 3：为 Python 测试建立共享支持层

**Files:**

- Create: `agents/_tests/support/__init__.py`
- Create: `agents/_tests/support/fakes.py`
- Create: `agents/_tests/support/factories.py`
- Create: `agents/_tests/support/assertions.py`
- Create: `agents/_tests/test_support_contract.py`
- Modify: `agents/_tests/test_workspace.py`

**Interfaces:**

- `signed_identity(tenant_id="tenant-a", user_id="user-1", membership="free")`
- `FakeModel`, `FakeSearchPort`, `FakeMakerStore`, `FakeComponentPublisher`
- `assert_no_side_effect(testcase, provider)`

- [ ] Write failing support tests for deterministic clock/IDs, tenant-scoped stores, recorded provider calls and async model output.
- [ ] Run `python -m unittest agents._tests.test_support_contract -v`; expect missing support modules.
- [ ] Move duplicated fake/helper definitions from the top of `test_workspace.py` without changing values or timing semantics.
- [ ] Give factories explicit defaults; tests requiring another tenant/date/model result override those arguments visibly.
- [ ] Re-run the complete legacy test module; test count and pass count must match the pre-migration count.
- [ ] Record the baseline count in `agents/_tests/support/test_inventory.json` with file hashes and test names.
- [ ] Commit:

```bash
git add agents/_tests/support agents/_tests/test_support_contract.py agents/_tests/test_workspace.py
git commit -m "test: extract deterministic workspace test support"
```

## Task 4：按领域拆分 `test_workspace.py`

**Files:**

- Create: `agents/_tests/chat/test_planning.py`
- Create: `agents/_tests/chat/test_streaming.py`
- Create: `agents/_tests/search/test_search_pipeline.py`
- Create: `agents/_tests/search/test_media_review.py`
- Create: `agents/_tests/workspace/test_calendar.py`
- Create: `agents/_tests/workspace/test_workflows.py`
- Create: `agents/_tests/maps/test_places.py`
- Create: `agents/_tests/maps/test_routes.py`
- Create: `agents/_tests/proactive/test_opportunities.py`
- Create: `agents/_tests/proactive/test_memory.py`
- Create: `agents/_tests/papers/test_discovery.py`
- Create: `agents/_tests/providers/test_provider_contracts.py`
- Create: `tools/split-workspace-tests.py`
- Delete: `agents/_tests/test_workspace.py`
- Modify: `frontend/public/test-cases/cases.json`
- Modify: `frontend/public/test-cases/procedures.js`

**Deterministic routing rules:**

- planning/capability/prompt/clarification/history → `chat/test_planning.py`
- stream/delta/checkpoint/public_content/fallback → `chat/test_streaming.py`
- rich_search/SearchPro/evidence/cache → `search/test_search_pipeline.py`
- media/image_limit/vision → `search/test_media_review.py`
- calendar/schedule/meeting → `workspace/test_calendar.py`
- workflow/action/provider_ledger/reconciliation → `workspace/test_workflows.py`
- place/location/nearby → `maps/test_places.py`
- route/map → `maps/test_routes.py`
- proactive/opportunity/notification → `proactive/test_opportunities.py`
- memory/feedback/budget → `proactive/test_memory.py`
- paper/arxiv/author/OpenAlex/DBLP/Crossref → `papers/test_discovery.py`
- remaining provider/identity/version contracts → `providers/test_provider_contracts.py`

- [ ] Write a failing splitter test that parses the baseline inventory and requires every original test name to map exactly once.
- [ ] Implement `tools/split-workspace-tests.py --check` using Python AST; it reports duplicates/unmapped tests and never rewrites production files.
- [ ] Create domain test classes inheriting only the necessary support mixins; move tests according to the routing table in small batches.
- [ ] After every batch, run both the new module and remaining legacy module; total discovered test names must equal inventory with no duplicates.
- [ ] Update the two public commands currently referencing `WorkspaceUnitTests` to the new workflow modules, and update all other string references found by:

```bash
rg -n "test_workspace|WorkspaceUnitTests" . --glob '!docs/superpowers/**'
```

- [ ] Delete `test_workspace.py` only after `python tools/split-workspace-tests.py --check` reports full one-to-one coverage.
- [ ] Run `python -m unittest discover -s agents/_tests -v`; require equal or higher test count and all pass.
- [ ] Commit:

```bash
git add -A agents/_tests/test_workspace.py agents/_tests tools/split-workspace-tests.py frontend/public/test-cases
git commit -m "test: split workspace regression suite by domain"
```

## Task 5：扩展架构、路由和构建门禁

**Files:**

- Modify: `tools/assert-edgeone-build-routes.mjs`
- Create: `tools/assert-source-architecture.mjs`
- Create: `tools/assert-deployment-target.mjs`
- Modify: `middleware.js`
- Modify: `package.json`
- Modify: `.github/workflows/ci.yml`
- Test: `tools/tests/source-architecture.test.mjs`
- Test: `tools/tests/deployment-target.test.mjs`

**Required Agent routes:**

```text
/chat /conversation /image /intelligence /messages /places /proactive
/provider_usage /reader /reset /routes /skill_marketplace /stop
/system_internal /workspace
```

- [ ] Write failing tests that use temporary fixture configs to detect one missing route, one exposed `_skill_adapters` route, one middleware mismatch, wrong project name, wrong project ID, wrong branch and dirty worktree.
- [ ] Run `node --test tools/tests/source-architecture.test.mjs tools/tests/deployment-target.test.mjs`; expect missing guards.
- [ ] Expand the EdgeOne route assertion from one Skill route to the full exact allowlist; no unexpected Agent route is accepted.
- [ ] Compare protected API routes with `middleware.config.matcher`; public auth and static routes remain explicitly separate.
- [ ] Implement deployment-target assertion:

```js
assert.equal(project.Name, 'floris-mvc-dev-5925b93');
assert.equal(project.ProjectId, 'makers-x91pbqwetj8l');
assert.equal(branch, 'dev');
assert.equal(head, remoteDevHead);
assert.equal(status, '');
```

- [ ] Add source architecture checks for deleted legacy files, `_shared`, `_ui_tools`, placeholder markers, direct Feature fetch, adapter paths and generated entitlement drift.
- [ ] Add root scripts `check:source`, `check:deploy-target`, `check:all`; order CI as generation/architecture → Python/Node → frontend → EdgeOne build/routes.
- [ ] Run all guards and CI-equivalent commands locally.
- [ ] Commit:

```bash
git add tools middleware.js package.json .github/workflows/ci.yml
git commit -m "ci: enforce architecture routes and Maker target"
```

## Task 6：端到端产品与性能验收

**Files:**

- Create: `frontend/e2e/chat-search.spec.ts`
- Create: `frontend/e2e/skills-marketplace.spec.ts`
- Create: `frontend/e2e/multi-tenant.spec.ts`
- Create: `frontend/e2e/calendar-maps-papers.spec.ts`
- Create: `docs/acceptance/2026-07-31-dev-acceptance.md`
- Modify: `.github/workflows/ci.yml`

- [ ] Add mocked deterministic E2E coverage for:
  - Guest can chat and sees only core/proactive Skills.
  - Signed-in user opens Skills page, returns home, sees dependency graph and cannot execute pending upload.
  - Search shows planning/searching/source progress, receives first token before delayed media, inserts reviewed image only at exact citation, and ignores legacy slot text.
  - Two signed identities never see each other’s conversation/workspace/cache.
  - Calendar change requires confirmation; maps use verified coordinates; papers open reader.
- [ ] Add performance assertions with artificial delays and require one SearchPro call per turn.
- [ ] Run `cd frontend && npx playwright test`; inspect traces/screenshots for all failures.
- [ ] Add a production-mode smoke job that builds locally and runs the mocked suite; keep live Maker smoke outside pull-request CI because it requires signed session/environment.
- [ ] Write the acceptance document with command, timestamp, commit hash, expected/actual result and links to non-secret artifacts. Do not paste cookies, tokens, env values or hidden model reasoning.
- [ ] Run the complete local release gate:

```bash
npm run check:all
npm test
python -m compileall -q agents
python -m unittest discover -s agents/_tests -v
cd frontend && npm run check:boundaries && npm test && npm run lint && npm run build -- --mode edgeone && npx playwright test
```

- [ ] Commit:

```bash
git add frontend/e2e .github/workflows/ci.yml docs/acceptance/2026-07-31-dev-acceptance.md
git commit -m "test: add full product acceptance gates"
```

## Task 7：推送 `dev`、构建并只部署独立 Maker 项目

**Files:**

- Build output: `.edgeone/`
- Modify only if generated from source: `.edgeone/agent-python/config.json`, `.edgeone/edge-functions/config.json`, `.edgeone/assets/`
- Update: `docs/acceptance/2026-07-31-dev-acceptance.md`

- [ ] Use `superpowers:verification-before-completion`; run all Task 6 gates from a clean working tree candidate.
- [ ] Verify branch invariants:

```bash
git rev-parse main
git rev-parse origin/main
git rev-parse --abbrev-ref HEAD
git status --short
```

Expected: both main hashes equal `712fe07a1b41dc1ce2ba316838bba0e2d111d32a`, branch is `dev`, status empty.

- [ ] Push exact commits: `git push origin dev`.
- [ ] Verify local and remote dev match: `test "$(git rev-parse HEAD)" = "$(git rev-parse origin/dev)"`.
- [ ] Run `edgeone makers build`, then `npm run test:edgeone-build-routes` and `node tools/assert-deployment-target.mjs`.
- [ ] Confirm `.edgeone/project.json` contains only:

```json
{"Name":"floris-mvc-dev-5925b93","ProjectId":"makers-x91pbqwetj8l"}
```

- [ ] If build changes tracked `.edgeone` source, inspect, test, commit, push and rebuild from that new clean HEAD before deployment.
- [ ] Deploy with the explicit allowed target:

```bash
edgeone makers deploy .edgeone -n floris-mvc-dev-5925b93 -e production
```

- [ ] Inspect deployment status until terminal success. Do not retry against, inspect, reconfigure or deploy `ai-active-agent-floris`.
- [ ] Use the in-app browser signed session to test the deployed `/chatBot/`: ordinary chat, current search with progress, exact reviewed media, Skill page return/dependency, calendar confirmation, map, paper, logout/login boundary and second isolated identity where available.
- [ ] Record deployment ID/URL, deployed commit, route result and product smoke results in the acceptance document; never record secrets.
- [ ] If acceptance document changed, commit/push it and deploy once more only if the document is included in the website build; otherwise leave deployment source unchanged and push the doc commit with a clear record of the deployed source commit.

## 本计划完成定义

- 全局 CSS 和单体测试已按 Feature/领域拆分，视觉和测试覆盖未下降。
- CI 阻止占位符、遗留大模块、错误分层、路由缺失、权益漂移和错误 Maker 目标。
- 搜索、Skill、多租户、日程、地图、论文关键路径都通过浏览器验收。
- `main` 未变化；`dev` 已推送；部署源干净且可追溯。
- 唯一部署项目是 `floris-mvc-dev-5925b93`。
