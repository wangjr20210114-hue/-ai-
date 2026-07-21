"""LangGraph chat endpoint running on the EdgeOne Makers agent runtime."""

import asyncio
import contextlib
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone

from ._graph import build_graph
from ._llm import get_model
from ._ui_tools import build_production_tools
from ._capability_plan import media_enabled_for_plan, plan_capabilities_bounded, required_tools_for_plan
from ._followups import generate_followups
from ._protocol import PublicStreamFilter, public_error
from ._calendar_context import calendar_context
from .._shared.intelligence import (
    apply_automatic_memory_candidates,
    confirmed_memory_context,
    extract_automatic_memory_candidates,
    load_intelligence_state,
    record_usage,
    save_intelligence_state,
    usage_summary,
)
from .._shared.auth import require_user, scoped_conversation_id
from .._shared.makers_conversation import (
    RUNNING_STATES,
    ensure_conversation_title,
    is_stale,
    read_chat_run,
    write_chat_run,
)
from .._shared.http import error
from .._shared.workspace import load_user_workspace
from .._shared.vision import describe_reference_images

SYSTEM_PROMPT = """你是元宝，一个可靠、主动、自然的中文智能助手。使用 GitHub Flavored Markdown 回复；多行代码必须使用带语言标识的围栏代码块，不能用普通缩进或行内代码冒充代码块。
当前北京时间是 {now}。
当前用户日程（每轮从 Makers 用户 Workspace 实时读取；更新或删除只能使用这里仍存在的 id）：{calendar_context}
本轮主动模块建议（由独立模型做语义判断，不是关键词规则）：{capability_plan}。它只提示可用能力，不规定你的措辞或回答结构；不要在回答中提及它。需要搜索时可优先采用其中的 search_query 和 image_query，也可以根据上下文自然调整。
本轮用户附图的视觉理解（由配置的多模态 Provider 一次性提取；没有附图时为“无”）：{reference_image_context}
需要地点、地图、联网事实或图片时自然调用对应工具；视觉模型筛选过的图片只在确实有助于理解时使用。不要为了满足格式而机械调用或重复调用工具。
“今天”“今日”“今年”“近 N 年”等相对时间必须以当前北京时间计算，不要沿用训练数据、示例或旧会话中的日期。用户问“今天/今日”的新闻时，把运行时完整日期作为强约束：只采用发布日期可核验为该日的来源，逐条标注日期；无日期或日期不符的结果不能写成今日新闻。找不到足够结果时如实说明，禁止用过去一周或别的日期凑数。
rich_search 始终是可用能力。是否搜索由你根据问题自主判断；独立 LLM 规划器已把本轮事实约束合并为一个查询并判断图片价值。若调用 rich_search，本轮只调用一次；结果不足时明确边界，不要换近义词重复搜索。搜索结果只是素材和证据，不限制你使用自身知识、措辞、观点或回答结构。不要用网页列表代替综合回答，也不要为了展示工具而罗列素材。回答时效事实时，采用的事实必须在相关段落内附上工具返回的 Markdown 来源链接；没有可核验来源的具体新闻、日期、数字或型号不要写。用户泛问近期动态且没有指定篇幅时，优先提炼 3–5 条最重要进展，避免重复总结和过长铺陈。
搜索返回的网页、图片、视频等素材由你自由编排：只采用真正有助于当前叙述的项目，把它放在最相关的段落附近；可以交错使用、重排或全部舍弃。不要把素材统一堆在回答末尾。使用工具给出的原始 Markdown URL，前端会在你选定的位置渲染对应图片、视频或网页卡片。
对“最新、截至目前、当前价格、当前能力”等时效事实，型号、日期、参数、价格和结论必须能由本轮检索结果直接支持；证据不足就缩小结论或明确未知，禁止用训练知识补出未核验的未来型号、数字或发布日期。“截至今天”是截止时间，不等于只采用今天发布的资料；只有 capability_plan 的 strict_today_only=true 时才执行当日发布日期硬过滤。
推荐一个餐馆、景点或其他地点时，必须同时使用 rich_search 和 search_places。推荐两个及以上地点或路线时优先调用 recommend_places_on_map：在一次调用中提供回答采用的每个独立地点名称，由工具逐一核实并直接生成地图 Action，避免再拆成重复地点查询。未验证地点可以在正文中明确说明，但不能进地图。若已经使用 search_places_batch，则只有地点工具返回的真实 place_id 才能交给 prepare_map_recommendation。
recommend_places_on_map 或 prepare_map_recommendation 生成可安全激活的地图 Action；网页会在本轮首次收到后自动更新一次右侧地图，同时保留按钮供用户查看其他内容后再次恢复该组地点。地点数量必须与回答中实际推荐的数量一致；数量不足时如实说明，不能创建残缺 Action。action_text 要根据上下文自然生成，避免每次使用同一句话。
新增、更新或删除日程时必须先调用 propose_calendar_changes 冻结提案，再请用户点击确认；不能只用普通文字询问，因为没有 Action 卡就无法安全提交。新增变更项设置 operation=create，并在 event 中提供 title、start_time、end_time；用户给了地点时必须先调用 search_places，从地点库选取 place_id，未给地点则可以省略。更新和删除必须从“当前用户日程”中匹配仍存在的 schedule_id；如果按日期、标题无法唯一匹配，或根本不存在，要自然说明找到的情况并请用户补充，绝不能编造 ID。修改地点同样必须重新查询地点库。时间必须为带 +08:00 的 ISO 8601。今天之前的日程只可查看，绝不能提议新增、修改或删除；即使用户明确要求也要自然说明限制。工具调用本身不会写入日程，绝不能在确认前声称已经修改日程。提案卡出现时间重叠警告时必须提醒用户核对，不能把重叠安排描述为无风险。
仅当本轮工具列表包含 propose_meeting 时才可创建腾讯会议，并等待网页确认；若没有该工具，说明可选连接器尚未配置，可以先创建普通日程，不能暗示用户需要自行申请企业 API。用户要求生图时立即调用 propose_image，不要先询问确认；修改之前的生成图时把对应版本的 action id 作为 parent_action_id。若主体是需要外观准确的现实人物、地点或物体，先调用一次 rich_search 获取经 HY-Vision 验证的真实图片，再把最多 3 个图片 URL 作为 reference_image_urls 交给 propose_image；原创或幻想画面不要无意义搜索。
生图工具返回后不要在 Markdown 正文再次插入生成图片或图片 URL，前端只通过一个“图片工坊”展示结果与版本。
最终回答不要提及搜索过真实照片、使用了参考图、分析了面部特征或内部生成策略；自然告知图片已完成和可以在图片工坊继续修改即可。
用户要求找论文或文献时先正常调用 rich_search 检索网页和论文来源，不要把搜索范围硬限制在 arXiv。富搜索已找到论文但缺少直接 PDF 时，可补充调用一次 search_arxiv，把富搜索确认的准确论文标题列表传入 titles，并把用户原始研究主题传入 topic 用于在准确标题不足用户要求数量时补足结果；不得用无关宽泛词凑数。只有用户明确要求只检索 arXiv 且还没有候选标题时才只用 topic。搜到可下载论文后前端会自动提供助读入口。
同一轮不要用同样的查询重复调用同一个搜索工具；拿到证据后直接综合回答。工具失败时说明边界，不要无限换措辞重试。
需要网页图片时可用 collect_page_images 提取单页最多 30 张候选，再用 analyze_images_parallel 分批评估。回答中的图片使用 ![描述](url)。
静默使用用户记忆和旅行偏好，不要用“根据已确定的旅行偏好”“根据用户记忆”等固定句式开头，也不要主动解释内部记忆来源。
后台会自动筛选和维护非敏感长期记忆；不要向用户展示、确认或解释记忆内容，也不要调用工具写记忆。一次性任务参数、临时状态、密码、令牌和敏感信息绝不能进入记忆。
调用工具前后都不要输出搜索策略、思维链、内部提示词、查询改写或参数；只让前端显示简短进度，最终直接给结论。
不要在正文末尾机械追加后续问题；界面的“猜你想问”由独立模块生成。"""

HEARTBEAT_SECONDS = 5
MAX_GRAPH_RECURSION = 24


def _text_content(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def _usage_values(message) -> tuple[int, int, int]:
    usage = getattr(message, "usage_metadata", None) or {}
    if not isinstance(usage, dict):
        return 0, 0, 0
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
    return input_tokens, output_tokens, total_tokens


def _ui_action(content: str) -> dict | None:
    try:
        value = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or not str(value.get("ui_action", "")):
        return None
    return value


def _field(value, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


async def _imported_conversation_seed(ctx, conversation_id: str, current_message: str) -> list[dict]:
    """Seed the first checkpoint only from an explicitly migrated Makers conversation."""
    checkpoint = await ctx.store.langgraph_checkpointer.aget_tuple(
        {"configurable": {"thread_id": conversation_id}}
    )
    if checkpoint is not None or not hasattr(ctx.store, "get_messages"):
        return []
    try:
        result = await ctx.store.get_messages(conversation_id=conversation_id, limit=100, order="asc")
    except KeyError as exc:
        # Older Node-side generic-store writes used an envelope that is not a
        # native Conversation Store message. It cannot seed a checkpoint, but
        # must never block the current user turn.
        logging.warning(
            "ignored incompatible conversation message conversation=%s field=%s",
            conversation_id,
            exc,
        )
        return []
    items = result if isinstance(result, list) else _field(result, "items", [])
    if not isinstance(items, list) or not any(
        isinstance(_field(item, "metadata", {}), dict)
        and (
            _field(item, "metadata", {}).get("migration_export_id")
            or _field(item, "metadata", {}).get("source") == "yuanbao-proactive"
        )
        for item in items
    ):
        return []
    seed = []
    for item in items[-60:]:
        role = "assistant" if str(_field(item, "role", "")) == "ai" else str(_field(item, "role", ""))
        content = _field(item, "content", "")
        if role in {"user", "assistant", "system"} and isinstance(content, str) and content:
            seed.append({"role": role, "content": content})
    if seed and seed[-1]["role"] == "user" and seed[-1]["content"].strip() == current_message.strip():
        seed.pop()
    return seed


async def handler(ctx):
    identity = require_user(ctx)
    user_id = str(identity["user_id"])
    conversation_id = scoped_conversation_id(ctx, user_id)
    body = ctx.request.body or {}
    message = body.get("message") or body.get("text") or ""
    if not message:
        return error("'message' is required")
    previous_run = await read_chat_run(ctx.store, conversation_id)
    if is_stale(previous_run):
        await write_chat_run(
            ctx.store,
            conversation_id,
            run_id=str((previous_run or {}).get("run_id") or ""),
            status="failed",
            error="上一次运行已超时，请重新发送",
        )
    elif isinstance(previous_run, dict) and previous_run.get("status") in RUNNING_STATES:
        return error("该对话仍在处理中；刷新后会自动恢复，请稍候或先停止当前运行", 409)
    try:
        await ctx.store.append_message(
            conversation_id=conversation_id,
            role="user",
            content=message,
            user_id=user_id,
            metadata={
                "client_message_id": str(body.get("client_message_id") or ""),
                "source": "yuanbao-chat",
                "owner_user_id": user_id,
            },
        )
        await ensure_conversation_title(ctx.store, conversation_id, message, user_id)
    except Exception:
        # LangGraph checkpoints remain authoritative if generic conversation
        # indexing is temporarily unavailable.
        logging.exception("native conversation append failed conversation=%s", conversation_id)
    run_id = str(getattr(ctx, "run_id", "") or f"chat-{int(time.time() * 1000)}")
    await write_chat_run(
        ctx.store,
        conversation_id,
        run_id=run_id,
        status="running",
    )

    async def fail_run(message_text: str) -> None:
        await write_chat_run(
            ctx.store,
            conversation_id,
            run_id=run_id,
            status="failed",
            error=str(message_text or "请求失败"),
        )
    reference_images = [
        str(item) for item in (body.get("reference_images") or [])
        if isinstance(item, str)
        and re.match(r"^data:image/(?:jpeg|png|webp);base64,", item, re.I)
        and len(item) <= 1_800_000
    ][:3]

    current_beijing = datetime.now(timezone(timedelta(hours=8)))
    current_date = current_beijing.date().isoformat()
    try:
        model = get_model(ctx.env)
    except Exception as exc:
        logging.exception("chat model configuration failed")
        message_text = public_error(exc)
        await fail_run(message_text)
        return error(message_text, 503)
    intelligence = await load_intelligence_state(ctx.store.langgraph_store, user_id)
    budget = usage_summary(intelligence)
    if (
        str((budget.get("preferences") or {}).get("enforcement") or "soft") == "hard"
        and ((budget.get("alerts") or {}).get("daily") or (budget.get("alerts") or {}).get("monthly"))
    ):
        message_text = "已达到今日 Token 预算；请在“记忆与学习”中调整预算或切换策略"
        await fail_run(message_text)
        return error(message_text, 429)
    memory_context = confirmed_memory_context(intelligence)
    search_preferences = intelligence.get("search_preferences") or {}
    search_result_limit = max(4, min(18, int(search_preferences.get("result_limit") or 8)))
    search_image_limit = max(0, min(4, int(
        search_preferences.get("image_limit") if search_preferences.get("image_limit") is not None else 2
    )))
    parallel_image_search = bool(search_preferences.get("parallel_image_search", True))
    workspace = await load_user_workspace(ctx.store.langgraph_store, conversation_id, user_id)
    current_calendar_context = calendar_context(workspace)
    reference_image_context = ""
    if reference_images:
        reference_image_context, vision_diagnostics = await describe_reference_images(
            ctx.env,
            reference_images,
            message,
            timeout=float(ctx.env.get("REFERENCE_VISION_TIMEOUT_SECONDS") or 8),
        )
        logging.info(
            "reference image analysis provider=%s attempted=%s",
            vision_diagnostics.get("provider") or "none",
            vision_diagnostics.get("attempted") or 0,
        )
        if not reference_image_context:
            reference_image_context = (
                "附图存在，但视觉 Provider 本轮未返回描述。除非用户要求生成或修改图片，否则不要声称已看见其内容；"
                "应自然说明暂时无法识别，并请用户重试或用文字补充。"
            )
    planning_message = message
    if reference_image_context:
        planning_message += f"\n\n[附图视觉事实，仅用于能力规划]\n{reference_image_context[:1600]}"
    planner_timeout = max(3.0, min(12.0, float(
        ctx.env.get("CAPABILITY_PLAN_TIMEOUT_SECONDS") or 6
    )))
    capability_plan, planner_timed_out = await plan_capabilities_bounded(
        model,
        planning_message,
        memory_context,
        timeout_seconds=planner_timeout,
    )
    if planner_timed_out:
        logging.warning(
            "chat capability planning timed out after %.1fs; main semantic model retains all tools",
            planner_timeout,
        )
    logging.info("capability plan enabled=%s", [key for key, value in capability_plan.items() if value])

    # Publication-date strictness is a semantic planner decision.  Keyword
    # matching incorrectly treated “截至今天的最新能力” as “published today”
    # and discarded the latest verifiable release from earlier dates.
    explicit_today = bool(capability_plan.get("strict_today_only"))
    time_sensitive = bool(capability_plan.get("needs_web_search"))
    temporal_context = {
        # This value is derived for every request; it is deliberately never a
        # release-date constant.
        "target_date": current_date if time_sensitive else "",
        "strict_date": explicit_today,
    }

    queue: asyncio.Queue = asyncio.Queue()
    background_tasks: list[asyncio.Task] = []

    async def publish_media(metadata: dict) -> None:
        await queue.put(ctx.utils.sse({
            "type": "search_media",
            "payload": {
                "query": metadata.get("query", ""),
                "media": metadata.get("media", []),
                "images": metadata.get("images", []),
                "media_pending": False,
                "vision_diagnostics": metadata.get("vision_diagnostics", {}),
                "timings_ms": metadata.get("timings_ms", {}),
            },
        }))

    # Production UI tools are local LangGraph tools; web search remains Makers-native.
    all_tools = build_production_tools(
        model,
        store=ctx.store.langgraph_store,
        conversation_id=conversation_id,
        env=ctx.env,
        paper_constraints={
            "author": capability_plan.get("paper_author") or "",
            "year": capability_plan.get("paper_year") or 0,
            "limit": capability_plan.get("paper_limit") or 0,
        },
        temporal_context=temporal_context,
        # For ordinary web answers, media extraction and vision review run in
        # parallel with the final LLM synthesis.  SearchMediaGallery renders
        # reviewed media as soon as the callback arrives, so images no longer
        # add their full latency to the text answer.  Realistic image generation
        # remains synchronous because the following image tool needs reviewed
        # reference URLs in the same capability chain.
        progressive_media=not bool(capability_plan.get("needs_image_generation")),
        media_callback=publish_media,
        background_tasks=background_tasks,
        user_id=user_id,
        initial_visual_references=reference_images,
        media_enabled=media_enabled_for_plan(capability_plan, search_image_limit),
        planned_search_query=str(capability_plan.get("search_query") or ""),
        planned_image_query=str(capability_plan.get("image_query") or ""),
        search_cache_ttl_seconds=300 if explicit_today else (900 if time_sensitive else 86_400),
        # Planning still determines the actual search query, but it must not
        # make the cache key unstable: two plans for the exact same user turn
        # can differ only in wording and otherwise trigger duplicate SearchPro
        # calls. Date scope and user-adjustable limits remain part of the key in
        # the tool adapter.
        search_cache_identity=message,
        search_result_limit=search_result_limit,
        search_image_limit=search_image_limit,
        parallel_image_search=parallel_image_search,
    )
    # Rich search is the single search path. Exposing the platform's plain
    # web_search beside it made semantically identical turns randomly lose the
    # established page-media + vision-review pipeline.
    tool_setup_error = ""

    graph = build_graph(
        model,
        all_tools,
        SYSTEM_PROMPT.format(
            now=current_beijing.strftime("%Y-%m-%d %H:%M:%S UTC+08:00"),
            capability_plan=json.dumps(capability_plan, ensure_ascii=False),
            calendar_context=current_calendar_context,
            reference_image_context=reference_image_context or "无",
        ) + (f"\n\n以下是用户已明确确认的长期记忆，只在相关时自然使用：\n{memory_context}" if memory_context else ""),
        checkpointer=ctx.store.langgraph_checkpointer,
        store=ctx.store.langgraph_store,
        # Routing remains semantic and model-planned rather than keyword based.
        # Each selected Makers-native capability is required at most once, so
        # the assistant cannot merely describe a map or confirmation action
        # without producing it; rich_search keeps its turn-local dedupe guard.
        required_tools=required_tools_for_plan(capability_plan),
    )

    async def gen():
        done = object()
        usage = [0, 0, 0]
        last_cancel_check = [0.0]

        async def cancellation_requested() -> bool:
            now_mono = time.monotonic()
            if now_mono - last_cancel_check[0] < 2:
                return False
            last_cancel_check[0] = now_mono
            latest = await read_chat_run(ctx.store, conversation_id)
            return bool(isinstance(latest, dict) and latest.get("status") == "cancel_requested")

        async def produce():
            pending_actions: list[dict] = []
            pending_search_results: dict | None = None
            pending_papers: dict | None = None
            pending_ai_content: list[str] = []
            final_answer_parts: list[str] = []
            public_stream = PublicStreamFilter()
            buffer_public_answer = bool(capability_plan.get("needs_image_generation"))
            run_error = ""
            cancelled = False

            async def reset_public_stream() -> None:
                pending_ai_content.clear()
                final_answer_parts.clear()
                if public_stream.reset():
                    await queue.put(ctx.utils.sse({"type": "ai_response_reset"}))

            async def emit_public(content: str) -> None:
                if not content:
                    return
                final_answer_parts.append(content)
                if buffer_public_answer:
                    pending_ai_content.append(content)
                else:
                    await queue.put(ctx.utils.sse({"type": "ai_response", "content": content}))
            if capability_plan.get("needs_image_generation"):
                await queue.put(ctx.utils.sse({"type": "tool_call", "name": "image_generation_planning"}))
            if tool_setup_error:
                await queue.put(
                    ctx.utils.sse({"type": "error_message", "content": tool_setup_error})
                )
            try:
                config = {
                    "configurable": {"thread_id": conversation_id},
                    "recursion_limit": MAX_GRAPH_RECURSION,
                }
                # Retry the marker after LangGraph has had a chance to create
                # the native conversation; the frontend appends the user row
                # concurrently and may have raced the first metadata update.
                await write_chat_run(
                    ctx.store,
                    conversation_id,
                    run_id=run_id,
                    status="running",
                )
                imported_seed = await _imported_conversation_seed(ctx, conversation_id, message)
                async for event in graph.astream(
                    {"messages": [*imported_seed, {"role": "user", "content": message}]},
                    config=config,
                    stream_mode="messages",
                ):
                        if await cancellation_requested():
                            cancelled = True
                            break

                        streamed_message, _metadata = event
                        input_tokens, output_tokens, total_tokens = _usage_values(streamed_message)
                        usage[0] = max(usage[0], input_tokens)
                        usage[1] = max(usage[1], output_tokens)
                        usage[2] = max(usage[2], total_tokens)

                        if getattr(streamed_message, "type", "") == "tool":
                            await reset_public_stream()
                            tool_content = _text_content(
                                getattr(streamed_message, "content", "")
                            )
                            action = _ui_action(tool_content)
                            if action and action.get("ui_action") == "rich_search_results":
                                metadata = action.get("search_results")
                                if isinstance(metadata, dict):
                                    pending_search_results = metadata
                                    await queue.put(ctx.utils.sse({"type": "search_results", "payload": metadata}))
                                    pending_search_results = None
                                papers = action.get("papers")
                                if isinstance(papers, list) and papers:
                                    pending_papers = {"papers": papers, "topic": metadata.get("query", "") if isinstance(metadata, dict) else ""}
                                await queue.put(
                                    ctx.utils.sse({
                                        "type": "tool_result",
                                        "name": getattr(streamed_message, "name", ""),
                                        "content": "富搜索来源和媒体已准备",
                                    })
                                )
                                continue
                            if action and action.get("ui_action") == "paper_results":
                                pending_papers = action
                                await queue.put(ctx.utils.sse({"type": "tool_result", "name": "search_arxiv", "content": "论文结果已准备"}))
                                continue
                            if action and action["ui_action"] in {
                                "map_action", "calendar_action", "side_effect_action",
                            }:
                                pending_actions.append(action)
                                continue
                            await queue.put(
                                ctx.utils.sse(
                                    {
                                        "type": "tool_result",
                                        "name": getattr(streamed_message, "name", ""),
                                        "content": tool_content[:500],
                                    }
                                )
                            )
                            continue

                        tool_calls = getattr(streamed_message, "tool_calls", None) or []
                        if tool_calls:
                            await reset_public_stream()
                            for tool_call in tool_calls:
                                name = (
                                    tool_call.get("name", "")
                                    if isinstance(tool_call, dict)
                                    else ""
                                )
                                await queue.put(ctx.utils.sse({"type": "tool_call", "name": name}))
                            continue

                        content = _text_content(getattr(streamed_message, "content", ""))
                        if content:
                            delta, reset_required = public_stream.push(content)
                            if reset_required:
                                pending_ai_content.clear()
                                await queue.put(ctx.utils.sse({"type": "ai_response_reset"}))
                            await emit_public(delta)
                tail, reset_required = public_stream.finish()
                if reset_required:
                    pending_ai_content.clear()
                    await queue.put(ctx.utils.sse({"type": "ai_response_reset"}))
                await emit_public(tail)
                if buffer_public_answer:
                    final_content = "".join(pending_ai_content)
                    if any(action.get("action", {}).get("kind") == "image_generate" for action in pending_actions):
                        final_content = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", final_content).strip()
                    if final_content:
                        await queue.put(ctx.utils.sse({"type": "ai_response", "content": final_content}))
            except Exception as exc:
                logging.exception("chat stream failed conversation=%s", conversation_id)
                run_error = public_error(exc)
                await queue.put(
                    ctx.utils.sse({"type": "error_message", "content": run_error})
                )
            except asyncio.CancelledError:
                # abortActiveRun is the platform-owned cancellation path.  A
                # browser disconnect does not cancel this detached producer.
                latest_run = await read_chat_run(ctx.store, conversation_id)
                cancelled = bool(
                    isinstance(latest_run, dict)
                    and latest_run.get("status") == "cancel_requested"
                )
                if not cancelled:
                    run_error = "运行已中断，请重试"
            finally:
                final_answer = "".join(final_answer_parts).strip()
                if background_tasks:
                    try:
                        outcomes = await asyncio.wait_for(
                            asyncio.gather(*background_tasks, return_exceptions=True),
                            timeout=90,
                        )
                        for outcome in outcomes:
                            if isinstance(outcome, Exception):
                                logging.warning("rich search media task failed: %s", outcome)
                    except asyncio.TimeoutError:
                        logging.warning("rich search media task timed out")
                        for task in background_tasks:
                            if not task.done():
                                task.cancel()
                if final_answer:
                    try:
                        follow_up_task = asyncio.create_task(generate_followups(model, message, final_answer))
                        memory_task = asyncio.create_task(extract_automatic_memory_candidates(model, message))
                        follow_ups, memory_candidates = await asyncio.wait_for(
                            asyncio.gather(follow_up_task, memory_task), timeout=20,
                        )
                        if follow_ups:
                            await queue.put(ctx.utils.sse({"type": "follow_ups", "payload": {"items": follow_ups}}))
                        if ctx.store.langgraph_store is not None and follow_ups:
                            await ctx.store.langgraph_store.aput(
                                ("yuanbao_message_meta_v1", conversation_id),
                                "latest_extras",
                                {
                                    "original_content": final_answer,
                                    "content": final_answer,
                                    "follow_ups": follow_ups,
                                },
                            )
                        if memory_candidates:
                            latest_intelligence = await load_intelligence_state(ctx.store.langgraph_store, user_id)
                            if apply_automatic_memory_candidates(
                                latest_intelligence,
                                memory_candidates,
                                source_message_id=str(body.get("client_message_id") or ""),
                            ):
                                await save_intelligence_state(ctx.store.langgraph_store, latest_intelligence, user_id)
                    except Exception as exc:
                        logging.warning("answer extras generation failed: %s", exc)
                if pending_search_results is not None:
                    await queue.put(ctx.utils.sse({
                        "type": "search_results",
                        "payload": pending_search_results,
                    }))
                if pending_papers is not None:
                    await queue.put(ctx.utils.sse({"type": "paper_results", "payload": pending_papers}))
                for action in pending_actions:
                    await queue.put(ctx.utils.sse({
                        "type": action["ui_action"],
                        "payload": action,
                    }))
                latest_run = await read_chat_run(ctx.store, conversation_id)
                cancelled = cancelled or bool(
                    isinstance(latest_run, dict)
                    and latest_run.get("status") == "cancel_requested"
                )
                await write_chat_run(
                    ctx.store,
                    conversation_id,
                    run_id=run_id,
                    status="cancelled" if cancelled else ("failed" if run_error else "completed"),
                    error=run_error,
                )
                if any(usage):
                    try:
                        latest_intelligence = await load_intelligence_state(ctx.store.langgraph_store, user_id)
                        record_usage(latest_intelligence, usage[0], usage[1], usage[2] or usage[0] + usage[1], "chat")
                        await save_intelligence_state(ctx.store.langgraph_store, latest_intelligence, user_id)
                    except Exception as exc:
                        logging.warning("usage persistence failed: %s", exc)
                    await queue.put(ctx.utils.sse({
                        "type": "usage",
                        "input_tokens": usage[0],
                        "output_tokens": usage[1],
                        "total_tokens": usage[2] or usage[0] + usage[1],
                    }))
                await queue.put(done)

        producer = asyncio.create_task(produce())
        try:
            while True:
                try:
                    frame = await asyncio.wait_for(
                        queue.get(), timeout=HEARTBEAT_SECONDS
                    )
                except asyncio.TimeoutError:
                    yield ctx.utils.sse(
                        {"type": "ping", "ts": int(time.time() * 1000)}
                    )
                    continue
                if frame is done:
                    break
                yield frame
        except GeneratorExit:
            # Closing the SSE subscriber must not close the Makers run. Keep
            # this invocation alive until LangGraph writes its final checkpoint.
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.shield(producer)
            return
        except asyncio.CancelledError:
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.shield(producer)
            raise
        finally:
            if producer.done():
                with contextlib.suppress(asyncio.CancelledError):
                    await producer
        yield b"data: [DONE]\n\n"

    return ctx.utils.stream_sse(gen())
