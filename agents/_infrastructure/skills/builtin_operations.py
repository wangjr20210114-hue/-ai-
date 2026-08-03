"""Turn-local business operations supplied to trusted system Skill adapters."""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, Awaitable, Callable

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from .calendar_operations import build_calendar_operation
from .contracts import ClarificationFieldInput

from ..._infrastructure.providers.tencent_location import (
    plan_verified_route as provider_plan_route,
    reverse_geocode as provider_reverse_geocode,
    search_verified_places_bounded as provider_search_places,
    search_verified_places_nearby as provider_search_places_nearby,
)
from ..._infrastructure.providers.web_media import collect_page_images as provider_collect_page_images
from ..._infrastructure.providers.rich_search import evidence_for_model, rich_search as provider_rich_search
from ..._infrastructure.providers.side_effects import generate_image as provider_generate_image, resolve_image_reference
from ..._infrastructure.providers.arxiv import search_arxiv as provider_search_arxiv
from ..._application.proactive.service import load_proactive_state, propose_workflow as create_workflow_proposal, save_proactive_state
from ..._infrastructure.makers.provider_usage_repository import record_provider_usage, record_vision_diagnostics
from ..._infrastructure.makers.identity import required_user_id
from ..._application.skills.registry import (
    capability_skill_map,
    default_skill_preferences,
    locked_skill_ids,
    resolve_enabled_skills,
    tool_skill_map,
)
from ..._application.skills.runtime import build_adapter_tools
from ..._application.skills.component_api import ComponentPublicationJournal
from ..._application.skills.runtime_ports import (
    SKILL_SERVICE_NAMES,
    ToolOperationService,
)
from ..._application.workspace.service import (
    load_user_workspace,
    meeting_action_payload,
    new_action,
    put_action,
    save_user_workspace,
)

from .route_resolution import _clarification_action
from .image_operations import build_image_operations
from .map_runtime import MapProviderRuntime
from .nearby_operations import build_nearby_operation
from .paper_operations import build_paper_search_operation
from .place_operations import PlaceOperations
from .route_operations import build_route_operation
from .search_operations import build_rich_search_operation
from .visual_context import TurnVisualContext

def build_system_skill_tools(
    model, *, store=None, conversation_id: str = "", env: dict | None = None,
    place_disambiguation_model=None,
    paper_discovery_model=None,
    paper_constraints: dict | None = None,
    temporal_context: dict[str, Any] | None = None,
    progressive_media: bool = False,
    media_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    background_tasks: list[asyncio.Task] | None = None,
    user_id: str = "",
    initial_visual_references: list[str] | None = None,
    media_enabled: bool = True,
    planned_media_preferred: bool = False,
    planned_search_query: str = "",
    planned_image_query: str = "",
    force_search_refresh: bool = False,
    rich_search_operation: Callable[[str, str, str], Awaitable[str]] | None = None,
    search_result_limit: int = 8,
    search_image_limit: int = 8,
    parallel_image_search: bool = True,
    enabled_skills: set[str] | None = None,
    identity: dict[str, Any] | None = None,
    planned_route_stops: list[dict[str, str]] | None = None,
    route_user_message: str = "",
    planned_route_city: str = "全国",
    planned_route_mode: str = "default",
    planned_route_strategy: str = "default",
    planned_route_uses_current_location: bool = False,
    planned_route_calendar_hint: str = "",
    planned_reuse_latest_route: bool = False,
    requested_route_plan_id: str = "",
    planned_calendar_place_resolution: bool = False,
    browser_current_location: dict[str, Any] | None = None,
    map_preferences: dict[str, Any] | None = None,
    proactive_preferences: dict[str, Any] | None = None,
    tracer: Any = None,
    makers_checkpointer: Any = None,
    request_id: str = "",
    component_journal: ComponentPublicationJournal | None = None,
) -> list[StructuredTool]:
    user_id = required_user_id(user_id)
    runtime_env = env or {}
    place_skill_id = capability_skill_map().get("places", "")
    calendar_skill_id = capability_skill_map().get("calendar_action", "")
    paper_scope = paper_constraints or {}
    time_scope = temporal_context or {}
    map_scope = map_preferences or {}
    map_service_mode = str(map_scope.get("service_mode") or "balanced")
    map_place_result_limit = max(3, min(12, int(map_scope.get("place_result_limit") or 6)))
    map_route_stop_limit = max(2, min(12, int(map_scope.get("route_stop_limit") or 8)))
    map_search_timeout = max(10.0, min(55.0, float(map_scope.get("search_timeout_seconds") or 30)))
    provider_place_review_enabled = bool(
        place_disambiguation_model is not None
        and map_service_mode != "fast"
    )
    map_preferred_route_mode = str(map_scope.get("preferred_route_mode") or "driving")
    if map_preferred_route_mode not in {"driving", "transit", "walking", "bicycling"}:
        map_preferred_route_mode = "driving"
    map_route_strategy = str(map_scope.get("route_strategy") or "time_then_cost")
    if map_route_strategy not in {"time_then_cost", "least_time", "least_cost"}:
        map_route_strategy = "time_then_cost"
    map_near_time_tolerance = max(
        0, min(30, int(map_scope.get("near_time_tolerance_minutes", 10) or 0)),
    )
    map_learn_route_preferences = bool(
        map_scope.get("learn_route_preferences", True)
    )
    map_parallelism = {"fast": 4, "balanced": 3, "complete": 2}.get(map_service_mode, 3)
    proactive_scope = proactive_preferences or {}
    travel_buffer_minutes = max(0, min(120, int(
        proactive_scope.get("travel_buffer_minutes")
        if proactive_scope.get("travel_buffer_minutes") is not None
        else 15
    )))
    route_gap_hours = max(1, min(8, int(proactive_scope.get("route_gap_hours") or 3)))
    provider_schedule_limit = max(2, min(12, int(
        proactive_scope.get("provider_schedule_limit") or 6
    )))
    # Explicit turn-local handoff: reviewed search media can become image
    # references without asking the model to copy fragile URLs between tools.
    turn_visual_context = TurnVisualContext.from_initial(initial_visual_references)

    async def _load_state() -> dict[str, Any]:
        return await load_user_workspace(store, user_id=user_id)

    async def _save_state(state: dict[str, Any]) -> dict[str, Any]:
        return await save_user_workspace(store, state, user_id=user_id)

    map_runtime = MapProviderRuntime(
        store=store,
        user_id=user_id,
        service_mode=map_service_mode,
        search_timeout=map_search_timeout,
        place_result_limit=map_place_result_limit,
        tracer=tracer,
        # Resolve providers at operation time so the Adapter remains swappable
        # without capturing a stale provider during tool construction.
        search_places_provider=lambda: provider_search_places,
        search_nearby_provider=lambda: provider_search_places_nearby,
        reverse_geocode_provider=lambda: provider_reverse_geocode,
        plan_route_provider=lambda: provider_plan_route,
    )
    _search_places_metered = map_runtime.search_places
    _search_places_nearby_metered = map_runtime.search_nearby
    _plan_route_metered = map_runtime.plan_route

    place_operations = PlaceOperations(
        runtime_env=runtime_env,
        conversation_id=conversation_id,
        browser_current_location=browser_current_location,
        map_runtime=map_runtime,
        load_state=_load_state,
        save_state=_save_state,
        place_disambiguation_model=place_disambiguation_model,
        planned_calendar_place_resolution=planned_calendar_place_resolution,
        provider_place_review_enabled=provider_place_review_enabled,
        place_result_limit=map_place_result_limit,
        route_stop_limit=map_route_stop_limit,
        parallelism=map_parallelism,
        search_timeout=map_search_timeout,
    )
    get_current_location = place_operations.get_current_location
    search_places = place_operations.search_places
    search_places_batch = place_operations.search_places_batch

    recommend_nearby_places_on_map = build_nearby_operation(
        _load_state=_load_state,
        _save_state=_save_state,
        _search_places_metered=_search_places_metered,
        _search_places_nearby_metered=_search_places_nearby_metered,
        browser_current_location=browser_current_location,
        conversation_id=conversation_id,
        map_place_result_limit=map_place_result_limit,
        map_search_timeout=map_search_timeout,
        runtime_env=runtime_env,
    )

    plan_route_between_places = build_route_operation(
        _load_state=_load_state,
        _plan_route_metered=_plan_route_metered,
        _save_state=_save_state,
        _search_places_metered=_search_places_metered,
        _search_places_nearby_metered=_search_places_nearby_metered,
        browser_current_location=browser_current_location,
        calendar_skill_id=calendar_skill_id,
        conversation_id=conversation_id,
        enabled_skills=enabled_skills,
        map_learn_route_preferences=map_learn_route_preferences,
        map_near_time_tolerance=map_near_time_tolerance,
        map_parallelism=map_parallelism,
        map_preferred_route_mode=map_preferred_route_mode,
        map_route_stop_limit=map_route_stop_limit,
        map_route_strategy=map_route_strategy,
        map_search_timeout=map_search_timeout,
        place_disambiguation_model=place_disambiguation_model,
        planned_route_calendar_hint=planned_route_calendar_hint,
        planned_route_city=planned_route_city,
        planned_route_mode=planned_route_mode,
        planned_route_stops=planned_route_stops,
        planned_route_strategy=planned_route_strategy,
        planned_route_uses_current_location=planned_route_uses_current_location,
        provider_place_review_enabled=provider_place_review_enabled,
        route_user_message=route_user_message,
        runtime_env=runtime_env,
        store=store,
        user_id=user_id,
    )

    prepare_map_recommendation = (
        place_operations.prepare_map_recommendation
    )
    recommend_places_on_map = place_operations.recommend_places_on_map

    propose_calendar_changes = build_calendar_operation(
        _load_state=_load_state,
        _plan_route_metered=_plan_route_metered,
        _save_state=_save_state,
        _search_places_metered=_search_places_metered,
        browser_current_location=browser_current_location,
        conversation_id=conversation_id,
        enabled_skills=enabled_skills,
        map_search_timeout=map_search_timeout,
        place_disambiguation_model=place_disambiguation_model,
        place_skill_id=place_skill_id,
        planned_reuse_latest_route=planned_reuse_latest_route,
        provider_place_review_enabled=provider_place_review_enabled,
        provider_schedule_limit=provider_schedule_limit,
        requested_route_plan_id=requested_route_plan_id,
        route_gap_hours=route_gap_hours,
        runtime_env=runtime_env,
        store=store,
        travel_buffer_minutes=travel_buffer_minutes,
        user_id=user_id,
    )

    async def propose_meeting(subject: str = "", start_time: str = "", end_time: str = "") -> str:
        """Prepare an editable Tencent Meeting action, preserving missing user details."""
        state = await _load_state()
        action = new_action(
            "meeting_create",
            meeting_action_payload(state, subject, start_time, end_time),
            requires_confirmation=True,
        )
        put_action(state, action)
        await _save_state(state)
        return json.dumps({"ui_action": "side_effect_action", "action": action}, ensure_ascii=False)

    image_operations = build_image_operations(
        model=model,
        store=store,
        user_id=user_id,
        runtime_env=runtime_env,
        load_state=_load_state,
        save_state=_save_state,
        visual_context=turn_visual_context,
        generate_image_provider=lambda: provider_generate_image,
        resolve_image_reference_provider=lambda: resolve_image_reference,
        collect_page_images_provider=lambda: provider_collect_page_images,
        record_provider_usage_provider=lambda: record_provider_usage,
    )
    propose_image = image_operations["propose_image"]
    collect_page_images = image_operations["collect_page_images"]
    analyze_images_parallel = image_operations["analyze_images_parallel"]
    rich_search = build_rich_search_operation(
        store=store,
        user_id=user_id,
        conversation_id=conversation_id,
        runtime_env=runtime_env,
        time_scope=time_scope,
        visual_context=turn_visual_context,
        progressive_media=progressive_media,
        media_callback=media_callback,
        background_tasks=background_tasks,
        media_enabled=media_enabled,
        planned_media_preferred=planned_media_preferred,
        planned_search_query=planned_search_query,
        planned_image_query=planned_image_query,
        force_search_refresh=force_search_refresh,
        search_use_case_operation=rich_search_operation,
        search_result_limit=search_result_limit,
        search_image_limit=search_image_limit,
        parallel_image_search=parallel_image_search,
        provider_rich_search_provider=lambda: provider_rich_search,
        evidence_for_model_provider=lambda: evidence_for_model,
        record_provider_usage_provider=lambda: record_provider_usage,
        record_vision_diagnostics_provider=lambda: record_vision_diagnostics,
    )
    search_arxiv = build_paper_search_operation(
        store=store,
        user_id=user_id,
        runtime_env=runtime_env,
        paper_scope=paper_scope,
        paper_discovery_model=paper_discovery_model,
        provider_search_arxiv_provider=lambda: provider_search_arxiv,
        provider_rich_search_provider=lambda: provider_rich_search,
        record_provider_usage_provider=lambda: record_provider_usage,
    )
    async def propose_workflow(title: str, steps: list[dict[str, Any]], reason: str) -> str:
        """Create a user-confirmable persistent multi-step workflow."""
        state = await load_proactive_state(store, user_id)
        mode = str((state.get("preferences") or {}).get("autonomy_mode") or "propose")
        if mode not in {"propose", "low_risk_auto"}:
            raise ValueError("当前主动权限只允许观察或提醒；请先在主动提醒设置中允许提案")
        workflow = create_workflow_proposal(
            state, title=title, steps=steps, reason=reason, now=int(time.time()),
        )
        await save_proactive_state(store, state, user_id)
        return json.dumps({
            "workflow_proposal": workflow,
            "message": "工作流提案已加入主动提醒中心，只有用户确认后才会激活",
        }, ensure_ascii=False)

    async def ask_user_clarification(
        title: str,
        prompt: str,
        fields: list[ClarificationFieldInput],
    ) -> str:
        """Present one compact, structured clarification card instead of prose interrogation."""
        allowed = {"single", "multi", "boolean", "text", "date", "time", "datetime"}
        normalized: list[dict[str, Any]] = []
        for index, raw in enumerate(fields or []):
            if isinstance(raw, BaseModel):
                raw = raw.model_dump()
            if not isinstance(raw, dict):
                continue
            field_type = str(raw.get("type") or "text").strip().lower()
            options = list(dict.fromkeys(
                str(option).strip()[:120]
                for option in (raw.get("options") or [])
                if str(option).strip()
            ))[:8]
            # Enforce the product-wide interaction hierarchy even if a model
            # asks for a text box while already supplying finite choices.
            if len(options) >= 2 and field_type not in {"single", "multi"}:
                field_type = "single"
            if field_type not in allowed:
                field_type = "single" if len(options) >= 2 else "text"
            field_id = re.sub(r"[^a-zA-Z0-9_-]", "-", str(raw.get("id") or f"field-{index + 1}"))[:48] or f"field-{index + 1}"
            label = str(raw.get("label") or "请补充").strip()[:80]
            item: dict[str, Any] = {
                "id": field_id,
                "label": label,
                "type": field_type,
                "required": bool(raw.get("required", True)),
            }
            if field_type in {"single", "multi"}:
                if len(options) < 2:
                    continue
                item["options"] = options
            elif field_type == "text":
                item["placeholder"] = str(raw.get("placeholder") or "请填写").strip()[:120]
            normalized.append(item)
            if len(normalized) >= 12:
                break
        if not normalized:
            raise ValueError("至少需要一个有效的澄清字段")
        return _clarification_action(
            conversation_id,
            title=str(title or "请补充几个信息"),
            prompt=str(prompt or "为了更准确地帮你处理，请选择或补充以下信息。"),
            fields=normalized,
        )

    definitions = [
        (get_current_location, "get_current_location", "用户直接询问“我现在在哪、当前位置是什么、你能否读到我的位置”时使用。它只读取本轮浏览器真实上传的新鲜定位，并调用腾讯逆地址解析返回可读地址、行政区和附近地标；不得输出经纬度、不得使用 IP 猜测、不得保存位置。没有浏览器定位时会生成填写大致位置的结构化卡片，以便继续附近推荐或路线规划。"),
        (search_places, "search_places", "使用腾讯地点服务搜索真实地点。普通查看传 purpose=browse；新增或修改含现实地点的日程必须传 purpose=calendar。唯一候选直接返回可用 place_id；多个腾讯建议只在无深度思考的结构化语义复核判定实际目的地近乎唯一时采用一个已提供的 place_id，否则生成按可靠城市证据优先的单选卡；无候选生成文本填空卡。快速地图模式跳过该额外复核并采用 Provider 首选。"),
        (search_places_batch, "search_places_batch", "多地点推荐必须使用：把每个地点作为独立 query 核实，并从每组选择一个最匹配的真实 place_id。"),
        (recommend_nearby_places_on_map, "recommend_nearby_places_on_map", "用户要找某个已知地点、当前位置或日程地点附近的餐馆、早餐店、酒店、商店、景点等真实地点时使用。用户说“我附近/当前位置附近”时必须设置 use_current_location_as_anchor=true；工具只会使用本轮浏览器实际上传的新鲜坐标，未收到坐标会明确失败，绝不能把“当前位置”当普通 POI 搜索或声称已经定位。其他情况传入完整明确的 anchor_query 与要找的类别 query；若用户给出多个备选参照地点，还必须把全部备选放入 anchor_queries，一次并行查询并保留各组成功结果，不能只选一个或拆成多次调用。工具优先复用 Makers 工作区和日程中已核实的参照地点坐标，再调用腾讯位置附近检索，并一次生成地图 Action。用户没有明确距离时不要自行缩小 radius_meters，保持默认 2000 米且 strict_radius=false；只有用户明确说“X 米内”时才传该距离并设 strict_radius=true。不要先用 rich_search 发现地点，也不要把“某地附近某类别”拼成普通 search_places 查询。"),
        (plan_route_between_places, "plan_route_between_places", "查询真实地点之间的道路距离、耗时或费用，或规划含多个停靠点的有序出行时必须使用。支持 route_mode=driving/transit/walking/bicycling 和 route_strategy=time_then_cost/least_time/least_cost，未指定均传 default。默认由腾讯多方案按省时优先、时间相近选省钱；用户明确选择会形成非敏感习惯计数，至少三次且占比达到 60% 后可影响后续默认。浏览器当前位置可用且用户未给起点时传 use_current_location_as_origin=true；不得把当前位置作为普通 POI 搜索。两点路线传 origin_query/destination_query；多段行程把全部文本地点按用户指定先后一次传入 ordered_stops，每项包含 query，可选 near_query，禁止拆成多次调用或自行重排。若地点序列或已核实地点已经给出城市，必须把该城市传入 city，以约束后续地点搜索；只有没有可靠城市证据时才传全国。工具会核实全部地点并调用真实腾讯路线服务，禁止先用网页搜索估算距离。若地点形如“301医院附近的锦江之星”，把 query 传“锦江之星”、near_query 传“北京301医院”。唯一候选直接采用；多个腾讯建议只在无深度思考的结构化语义复核判定实际目的地近乎唯一时采用一个已提供的 place_id，否则生成按可靠城市证据优先的单选卡；无候选生成填空卡。快速地图模式跳过该额外复核并采用 Provider 首选。"),
        (prepare_map_recommendation, "prepare_map_recommendation", "从已核实的真实 ID 生成可点击地图推荐；多地点推荐必须传 expected_place_count 和每组各一个 ID，数量不足时继续核实。只准备 Action，不直接更新地图。"),
        (recommend_places_on_map, "recommend_places_on_map", "模型驱动的非周边多地点推荐组合工具：根据用户目标自行给出 2-12 个具体地点名称、城市、自然地图标题和自然链接文案；工具逐个核实并准备最终地图 Action。用户指定数量时 queries 必须严格等于该数量。只要用户目标表达了相对某个或多个参照点“附近、周边、离它近”，不得使用本工具，也不得从模型知识猜餐厅名称；必须改用 recommend_nearby_places_on_map，把全部参照点放入 anchor_queries。"),
        (propose_calendar_changes, "propose_calendar_changes", "必须用此工具准备日程新增、更新或删除提案并生成确认卡；不要只在正文里口头询问。格式示例：changes=[{operation:'create',event:{title:'游览北海公园',start_time:'2026-07-16T09:00:00+08:00',end_time:'2026-07-16T10:00:00+08:00',place_id:'地点工具返回的ID',location_kind:'physical'}}]。location_kind 是模型按语义填写的协议枚举，只能为 physical 或 online；工具不会用地点名称词表猜测。把刚规划的多站路线写入日程时，必须传路线工具返回的 source_route_plan_id，并为 ordered_stops 中每个地点分别创建至少一个事件，严格保持顺序，禁止把多个站点合并成一个事件。更新/删除还要传 schedule_id。用户点击确认前不会真正写入。"),
        (propose_meeting, "propose_meeting", "准备可编辑的腾讯会议确认卡；即使主题、开始时间或结束时间不完整也要调用本工具，把未知值留空，不要在正文中连续追问多个条件。确认卡会让用户逐项补齐、检查冲突并确认，之后才由后台通过腾讯会议官方 MCP Skill 执行。"),
        (propose_image, "propose_image", "直接调用混元生图并返回图片，不要询问确认。现实人物、地点或物体可先用 rich_search 获取经 HY-Vision 审核的图片 URL，再通过 reference_image_urls（最多 3 张）作为视觉参考；修改历史版本时传 parent_action_id。"),
        (collect_page_images, "collect_page_images", "从一个公开网页提取最多 30 张真实图片候选，网页图片不足时返回实际数量。"),
        (rich_search, "rich_search", "项目 v4.2 富搜索。搜索前的独立 LLM 规划器已经合并本轮事实查询，并判断图片是否有助于理解；同一轮无论怎样改写参数都只执行一次 Provider 搜索。"),
        (analyze_images_parallel, "analyze_images_parallel", "并行视觉评估最多 30 张图片；单张失败不影响其他图片。"),
        (search_arxiv, "search_arxiv", "检索结构化学术论文。富搜索已找到论文时，把准确标题列表一次性传给 titles；按作者、单位和时间范围查找时分别传 author（英文论文署名）、institution（英文规范名）与 year/year_from/year_to，不要把这些条件混在宽泛 topic 中。工具会并行利用轻量模型自身知识提名精确 arXiv ID、用官方 arXiv 核验，并用 DBLP 的单位档案锁定作者身份；不足时再使用严格过滤的 Crossref 元数据。模型候选未经官方核验绝不会展示，同名作者的宽泛 arXiv 结果也不会凑数；每轮最多调用一次。"),
        (propose_workflow, "propose_workflow", "用户明确要求建立跨时间、多步骤的持续提醒或计划时创建工作流提案。steps 每项包含 offset_minutes、title、body、action_prompt，可用 depends_on=['step_1'] 建立 DAG 依赖；失败时需要回退提示的步骤可增加 compensation={title,body,action_prompt}。默认按顺序依赖。必须由用户确认后才会激活，依赖步骤需用户标记完成后才推进。"),
        (ask_user_clarification, "ask_user_clarification", "所有问答场景统一的必要信息收集入口。只有缺少该字段会阻断所有安全有用的回答，或无法唯一确定真实副作用对象时才能调用；“知道后更好”、可选偏好和用户尚未决定都不得调用，应直接在正文给出 2–3 套带假设与取舍的方案。这条边界适用于所有主题，禁止套用固定画像问题。本轮最多调用一次并只收最少必要字段；能由当前上下文、已核实结果、其他字段或安全默认值推导出的字段不得再问。有限候选优先 single/multi，能用是/否表达就用 boolean，只缺日期用 date、日期已知只缺时刻用 time、两者都缺才用 datetime，仅答案无法枚举时用 text。卡片提交后由前端自动把答案作为对话补充信息继续推理，不要要求用户再次发送，也不要重复询问已提交字段。"),
    ]
    active = (
        enabled_skills
        if enabled_skills is not None
        else {
            skill_id
            for skill_id, enabled in default_skill_preferences().items()
            if enabled
        }
    )
    active = set(active)
    locked_skills = locked_skill_ids()
    active.update(locked_skills)
    active = set(resolve_enabled_skills(active))
    tool_owners = tool_skill_map()
    operations = {
        name: function
        for function, name, _description in definitions
    }
    if set(operations) != set(tool_owners):
        raise RuntimeError(
            "System Skill implementation/manifest mismatch: "
            f"missing={sorted(set(tool_owners) - set(operations))}, "
            f"undeclared={sorted(set(operations) - set(tool_owners))}"
        )
    services = {
        SKILL_SERVICE_NAMES[skill_id]: ToolOperationService({
            name: operations[name]
            for name, owner in tool_owners.items()
            if owner == skill_id
        })
        for skill_id in active
        if skill_id in SKILL_SERVICE_NAMES
    }
    journal = component_journal or ComponentPublicationJournal()
    adapter_tools = build_adapter_tools({
        "state_store": store,
        "checkpointer": makers_checkpointer,
        "model": model,
        "tracer": tracer,
        "conversation_id": conversation_id,
        "request_id": str(request_id or conversation_id),
        "user_id": user_id,
        "identity": identity or {"user_id": user_id, "membership": "free"},
        "env": runtime_env,
        "browser_location": browser_current_location,
        "services": services,
        "components": journal.handlers(),
    }, active)
    adapter_names = [str(getattr(tool, "name", "") or "") for tool in adapter_tools]
    duplicate_adapter_names = {
        name for name in adapter_names if adapter_names.count(name) > 1
    }
    if len(adapter_names) != len(set(adapter_names)):
        raise ValueError(
            "Skill adapter tool names must be globally unique: "
            f"{sorted(duplicate_adapter_names)}"
        )
    return adapter_tools
