# Domain、Maker Infrastructure 与统一权益 Contract 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清空职责混杂的 `agents/_shared`，建立 MVC/Application 分层和 Maker 基础设施适配器，并用唯一的 `contracts/entitlements.v1.json` 同时驱动 Node 与 Python 权益逻辑。

**Architecture:** 纯业务规则进入 `_domain`；用例进入 `_application`；Maker/Provider/HTTP 进入 `_infrastructure`；SSE/HTTP 输出进入 `_presenters`；各 `agents/*/index.py` 只做路由 Controller 适配。Maker 的签名身份、state、checkpointer、blob 和 trace 继续承担多租户底座，业务层只传递可信 `TenantIdentity`。权益 JSON 是唯一人工维护来源，Node/Python 模块由生成器产生并由 CI 校验。支付只定义 Provider 端口和不可用实现。

**Tech Stack:** Python 3.11、Node.js ESM、EdgeOne Pages Functions/Makers、JSON Schema、unittest、Node test runner。

## 全局约束

- 认证为纯多用户架构；Guest 是匿名租户身份，不保留旧单用户兼容路径。
- `tenant_id`、`user_id` 必须来自签名 session/Maker context，禁止从请求 JSON 或模型输出采信。
- Maker 已有隔离、state、checkpointer、blob、model、trace 能力必须复用。
- 数据库/存储适配器使用 Maker 友好的 key/prefix；不得引入独立数据库。
- Node 与 Python 不再各自硬编码会员等级、上限或 Guest Skill 策略。
- 支付接口留出，但 `payment_available=false`，不创建订单、不收款。
- 迁移期间可使用短期 re-export shim；本计划结束时 `agents/_shared` 必须删除。

---

## Task 1：建立唯一权益 Contract 和跨运行时生成器

**Files:**

- Create: `contracts/entitlements.v1.json`
- Create: `contracts/entitlements.v1.schema.json`
- Create: `tools/generate-entitlement-contract.mjs`
- Create: `auth/generated/entitlements.js`
- Create: `agents/_domain/entitlements/generated_contract.py`
- Create: `tools/tests/entitlement-contract.test.mjs`
- Create: `agents/_tests/domain/test_entitlement_contract.py`

**Contract shape:**

```json
{
  "version": 1,
  "plans": ["guest", "free", "plus", "pro"],
  "guest_skill_ids": ["core", "proactive-agent"],
  "limits": {
    "guest": {"search_depth": "basic", "concurrent_runs": 1, "daily_tokens": 20000, "user_skill_uploads": 0},
    "free": {"search_depth": "standard", "concurrent_runs": 1, "daily_tokens": 80000, "user_skill_uploads": 2},
    "plus": {"search_depth": "deep", "concurrent_runs": 2, "daily_tokens": 300000, "user_skill_uploads": 10},
    "pro": {"search_depth": "deep", "concurrent_runs": 4, "daily_tokens": 1000000, "user_skill_uploads": 50}
  },
  "payment_available": false
}
```

- [ ] Write failing Node and Python tests asserting the generated modules equal the JSON contract and preserve plan order.
- [ ] Run `node --test tools/tests/entitlement-contract.test.mjs` and `python -m unittest agents._tests.domain.test_entitlement_contract -v`; expect missing files.
- [ ] Implement the schema with `additionalProperties: false`, exact four plans, non-negative integer limits and `payment_available` boolean.
- [ ] Implement the generator to canonicalize JSON, render frozen ESM/Python literals, and support `node tools/generate-entitlement-contract.mjs --check` without writing.
- [ ] Generate both modules with `node tools/generate-entitlement-contract.mjs`.
- [ ] Run both tests and `node tools/generate-entitlement-contract.mjs --check`; expect pass.
- [ ] Commit:

```bash
git add contracts tools/generate-entitlement-contract.mjs tools/tests auth/generated agents/_domain/entitlements agents/_tests/domain
git commit -m "refactor: define one cross-runtime entitlement contract"
```

## Task 2：让 Node 与 Python 权益服务只消费生成 Contract

**Files:**

- Modify: `auth/entitlements.js`
- Modify: `auth/session.test.js`
- Create: `agents/_domain/entitlements/policy.py`
- Modify: `agents/_shared/entitlements.py`
- Create: `agents/_tests/domain/test_entitlement_policy.py`
- Modify: `package.json`

**Interfaces:**

- Node: `normalizeMembership`, `planAllows`, `skillAccess`, `publicEntitlements`
- Python: `normalize_membership`, `plan_allows`, `allowed_skill_ids`, `public_entitlements`
- Both consume generated values; no literal plan limit remains outside generated files.

- [ ] Add failing parity tests that execute Node public entitlements and compare them with Python results for guest/free/plus/pro and invalid membership.
- [ ] Run Node/Python entitlement tests; expect key naming or hard-coded-source failures.
- [ ] Refactor `auth/entitlements.js` to import `MEMBERSHIP_PLANS`, `PLAN_LIMITS`, `GUEST_SKILL_IDS`, and `PAYMENT_AVAILABLE` from `auth/generated/entitlements.js`.
- [ ] Implement `agents/_domain/entitlements/policy.py` using `generated_contract.py`; keep public Python snake_case response keys.
- [ ] Turn `_shared/entitlements.py` into a re-export shim with no rules or literals.
- [ ] Add root script:

```json
"check:entitlements": "node tools/generate-entitlement-contract.mjs --check && node --test tools/tests/entitlement-contract.test.mjs"
```

- [ ] Run all auth and Python entitlement tests plus `rg -n "1_000_000|300_000|80_000|20_000|GUEST_SKILL_IDS|PLAN_LIMITS" auth agents --glob '!**/generated_*'`; expect no duplicate plan data.
- [ ] Commit:

```bash
git add auth agents/_domain/entitlements agents/_shared/entitlements.py agents/_tests/domain package.json
git commit -m "refactor: consume generated entitlement policy"
```

## Task 3：建立可信多租户身份和 Maker Repository 基类

**Files:**

- Create: `agents/_domain/identity.py`
- Create: `agents/_application/identity.py`
- Create: `agents/_infrastructure/makers/identity.py`
- Create: `agents/_infrastructure/makers/repository.py`
- Modify: `agents/_shared/auth.py`
- Test: `agents/_tests/infrastructure/test_maker_identity.py`
- Test: `agents/_tests/infrastructure/test_maker_repository.py`

**Interfaces:**

- Produce: `TenantIdentity(tenant_id, user_id, auth_type, membership, session_id)`
- Produce: `MakerIdentityResolver.resolve(ctx) -> TenantIdentity`
- Produce: `MakerRepository.scoped_key(identity, aggregate, key) -> str`

- [ ] Write failing spoofing and isolation tests:

```python
def test_request_body_cannot_override_signed_identity(self):
    identity = MakerIdentityResolver().resolve(
        signed_context("tenant-a", "user-1"),
        request_body={"tenant_id": "tenant-b", "user_id": "attacker"},
    )
    self.assertEqual((identity.tenant_id, identity.user_id), ("tenant-a", "user-1"))

def test_repository_prefixes_tenant_and_user(self):
    key = repository.scoped_key(identity, "workspace", "current")
    self.assertEqual(key, "tenants/tenant-a/users/user-1/workspace/current")
```

- [ ] Run the two test modules; expect missing infrastructure modules.
- [ ] Implement frozen validated identity; Guest receives a signed/derived anonymous user ID from session, never a constant shared ID.
- [ ] Implement Maker repository prefixing and reject empty, `..`, slash-prefixed or cross-tenant keys.
- [ ] Make `_shared/auth.py` a compatibility re-export; migrate direct auth parsing to the resolver.
- [ ] Add tests for two tenants with identical user IDs, two users in one tenant, Guest sessions, invalid signature, and key traversal.
- [ ] Run identity/repository tests and existing auth tests.
- [ ] Commit:

```bash
git add agents/_domain/identity.py agents/_application/identity.py agents/_infrastructure/makers agents/_shared/auth.py agents/_tests/infrastructure
git commit -m "refactor: centralize Maker tenant identity and scoping"
```

## Task 4：拆分 `_shared` 的纯领域与应用服务

**Files:**

- Create: `agents/_domain/skills/manifest.py`
- Create: `agents/_domain/skills/policy.py`
- Create: `agents/_domain/workspace/models.py`
- Create: `agents/_domain/workspace/policy.py`
- Create: `agents/_domain/proactive/models.py`
- Create: `agents/_domain/proactive/policy.py`
- Create: `agents/_application/workspace/service.py`
- Create: `agents/_application/proactive/service.py`
- Create: `agents/_application/intelligence/service.py`
- Modify: `agents/_shared/skill_registry.py`
- Modify: `agents/_shared/workspace.py`
- Modify: `agents/_shared/proactive.py`
- Modify: `agents/_shared/proactive_memory.py`
- Modify: `agents/_shared/opportunities.py`
- Modify: `agents/_shared/intelligence.py`
- Test: `agents/_tests/domain/test_layer_boundaries.py`

**Move map:**

| Existing module | Target responsibility |
|---|---|
| `_shared/skill_registry.py` | `_domain/skills/{manifest,policy}.py` + `_application/skills/registry.py` |
| `_shared/workspace.py` | `_domain/workspace/*` + `_application/workspace/service.py` |
| `_shared/proactive.py`, `proactive_memory.py`, `opportunities.py` | `_domain/proactive/*` + `_application/proactive/service.py` |
| `_shared/intelligence.py` | `_application/intelligence/service.py` |
| `_shared/component_api.py` | `_application/skills/component_api.py` |

- [ ] Write a failing AST boundary test: `_domain` may import stdlib/Pydantic and other domain modules, but must not import `pages_*`, HTTP, provider, route or infrastructure packages.
- [ ] Run `python -m unittest agents._tests.domain.test_layer_boundaries -v`; expect missing/new-boundary violations.
- [ ] Move pure dataclasses, enums, validation and deterministic policies first; preserve public call signatures through re-export shims.
- [ ] Move orchestration that coordinates repositories/providers into `_application`.
- [ ] Update call sites in small batches; after each module run its focused tests before deleting implementation from the shim.
- [ ] Run `python -m unittest discover -s agents/_tests -v`; expect pass.
- [ ] Commit:

```bash
git add agents/_domain agents/_application agents/_shared agents/_tests/domain
git commit -m "refactor: separate domain policies from application services"
```

## Task 5：迁移 Maker 和 Provider 基础设施

**Files:**

- Create: `agents/_infrastructure/makers/data_version.py`
- Create: `agents/_infrastructure/makers/conversation_repository.py`
- Create: `agents/_infrastructure/makers/workspace_repository.py`
- Create: `agents/_infrastructure/makers/intelligence_repository.py`
- Create: `agents/_infrastructure/makers/place_repository.py`
- Create: `agents/_infrastructure/makers/route_repository.py`
- Create: `agents/_infrastructure/makers/provider_usage_repository.py`
- Create: `agents/_infrastructure/providers/arxiv.py`
- Create: `agents/_infrastructure/providers/tencent_location.py`
- Create: `agents/_infrastructure/providers/vision.py`
- Create: `agents/_infrastructure/providers/web_media.py`
- Create: `agents/_infrastructure/providers/side_effects.py`
- Create: `agents/_infrastructure/http.py`
- Modify: corresponding files under `agents/_shared/`
- Test: `agents/_tests/infrastructure/test_layer_boundaries.py`

**Move map:**

| Existing module | Target |
|---|---|
| `data_version.py`, `makers_conversation.py` | `_infrastructure/makers/` |
| `evidence_cache.py`, `place_cache.py`, `route_cache.py`, `provider_metering.py` | Maker repositories |
| `arxiv.py`, `rich_search.py`, `tencent_location.py`, `vision.py`, `web_media.py`, `side_effects.py` | `_infrastructure/providers/` |
| `http.py` | `_infrastructure/http.py` |

- [ ] Write failing boundary tests: `_infrastructure` may depend on domain/application ports; domain/application cannot import concrete provider classes except in composition roots.
- [ ] Move one adapter at a time, leaving re-export shims so route behavior stays stable.
- [ ] Replace raw cache keys with `MakerRepository.scoped_key`; add cross-tenant tests for evidence, place, route, conversation, workspace and provider usage.
- [ ] Ensure Maker optimistic version/consistency semantics remain in repository adapters and are not reimplemented in controllers.
- [ ] Run all infrastructure and existing workspace/search/provider tests.
- [ ] Commit:

```bash
git add agents/_infrastructure agents/_shared agents/_tests/infrastructure
git commit -m "refactor: isolate Maker and provider infrastructure"
```

## Task 6：让所有 HTTP Agent 成为薄 MVC Controller

**Files:**

- Create: `agents/_controllers/chat_controller.py`
- Create: `agents/_controllers/conversation_controller.py`
- Create: `agents/_controllers/image_controller.py`
- Create: `agents/_controllers/messages_controller.py`
- Create: `agents/_controllers/places_controller.py`
- Create: `agents/_controllers/proactive_controller.py`
- Create: `agents/_controllers/provider_usage_controller.py`
- Create: `agents/_controllers/reader_controller.py`
- Create: `agents/_controllers/reset_controller.py`
- Create: `agents/_controllers/routes_controller.py`
- Create: `agents/_controllers/stop_controller.py`
- Create: `agents/_controllers/system_controller.py`
- Create: `agents/_controllers/workspace_controller.py`
- Modify: every `agents/*/index.py`
- Create: `agents/_tests/architecture/test_route_controllers.py`

**Interfaces:**

- Each route `handler(ctx)` delegates once to a named controller.
- Controllers parse HTTP input, call one application use case/service, pass results to Presenter/view.
- No route imports `_shared`, provider code or Maker SDK directly.

- [ ] Write a failing AST test that enumerates all `agents/*/index.py`, requires a handler, allows only controller imports, and caps each route at 80 nonblank lines.
- [ ] Run `python -m unittest agents._tests.architecture.test_route_controllers -v`; expect failures for current route files.
- [ ] Extract routes one by one; keep response schemas/status codes unchanged.
- [ ] Use existing `agents/_controllers/intelligence_controller.py` as a shape reference, then bring it under the same boundary rules.
- [ ] Run each route’s focused tests after extraction and then full discovery.
- [ ] Commit:

```bash
git add agents/_controllers agents/*/index.py agents/_tests/architecture
git commit -m "refactor: make Agent routes thin MVC controllers"
```

## Task 7：删除 `_shared` 并保留支付扩展端口

**Files:**

- Create: `agents/_application/billing/ports.py`
- Create: `agents/_infrastructure/providers/unavailable_billing.py`
- Modify: `auth/entitlements.js`
- Delete: `agents/_shared/`
- Create: `tools/assert-python-architecture.py`
- Modify: `package.json`
- Modify: `.github/workflows/deploy.yml`

**Interfaces:**

```python
class BillingProvider(Protocol):
    async def create_checkout(self, identity: TenantIdentity, plan: str) -> CheckoutSession: ...
    async def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> BillingEvent: ...
    async def list_transactions(self, identity: TenantIdentity) -> Sequence[Transaction]: ...
```

- [ ] Add a failing test that the unavailable provider reports `payment_available=False` and raises a typed `BillingUnavailable` without external calls.
- [ ] Add an architecture guard rejecting `agents._shared` imports and `_shared` directory presence.
- [ ] Run the guards; expect failure until all shims/call sites are gone.
- [ ] Implement billing contracts and unavailable adapter; keep existing Node `BillingProvider` API behavior aligned without adding routes or checkout UI.
- [ ] Run `rg -n "agents\\._shared|\\.\\._shared|_shared" agents tools`; migrate every remaining call site.
- [ ] Delete `agents/_shared` only after the grep is clean outside historical docs.
- [ ] Add root script `check:architecture` and invoke entitlement/architecture checks in CI.
- [ ] Run:

```bash
node tools/generate-entitlement-contract.mjs --check
python tools/assert-python-architecture.py
python -m unittest discover -s agents/_tests -v
node --test auth/*.test.js auth/controllers/*.test.js tools/tests/*.test.mjs
```

- [ ] Commit:

```bash
git add -A agents/_shared agents/_application/billing agents/_infrastructure/providers/unavailable_billing.py auth tools package.json .github/workflows/deploy.yml
git commit -m "refactor: complete domain and infrastructure boundaries"
```

## 本计划完成定义

- `agents/_shared` 不存在，所有模块有明确的 domain/application/infrastructure/presenter/controller 归属。
- 所有 Maker 数据 key 都包含可信 tenant/user 前缀，跨租户测试通过。
- 所有 HTTP Agent 都是薄 Controller，业务规则不在路由层。
- Node/Python 权益数据来自同一 JSON Contract，生成差异会阻断 CI。
- Guest 与会员 Skill 策略一致；支付只有接口且明确不可用。
