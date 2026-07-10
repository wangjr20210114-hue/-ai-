"""REST 路由：旅游计划、通用日程、腾讯地图、会议创建。"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter

from database.repositories.conversation_repo import LOCAL_USER_ID
from database.repositories.plan_repo import delete_plan, get_plan, list_plans, save_plan, update_plan
from database.repositories.schedule_repo import (
    check_conflict,
    delete_schedule,
    get_schedule,
    list_schedules,
    save_schedule,
    toggle_done,
    update_schedule,
)
from models.schemas import (
    GeneratePlanRequest,
    MeetingCreateRequest,
    SavePlanRequest,
    SaveScheduleRequest,
    ScheduleItem,
    TravelPlan,
)
from prompts.templates import MEETING_EXTRACT_PROMPT, TRAVEL_SYSTEM_PROMPT
from scenarios.scenario_type import ScenarioType
from services.city_service import search_cities
from services.hunyuan_service import hunyuan_service, ApiNotConfiguredError
from services.map_service import map_service
from services.meeting_service import meeting_service

router = APIRouter(prefix="/api")


# ============ 旅游计划 ============

@router.get("/cities")
async def search_city(keyword: str = "", limit: int = 15) -> dict:
    """模糊搜索城市。"""
    return {"cities": search_cities(keyword, limit)}


@router.post("/travel/analyze")
async def analyze_travel_intent(req: dict) -> dict:
    """AI 驱动的旅游意图分析。"""
    message = req.get("message", "")
    collected = req.get("collected", {})
    history = req.get("history", [])

    required_fields = ["destination", "departure", "start_date", "end_date", "travel_style", "scenery_preference"]

    system_prompt = """你是一个旅游规划助手。根据用户的对话内容和已收集的信息，完成两件事：

1. 提取/更新已知信息
2. 决定下一步该问什么（如果信息还不完整）

## 必须收集的字段：
- destination: 目的地城市
- departure: 出发城市
- start_date: 出发日期（YYYY-MM-DD 格式）
- end_date: 结束日期（YYYY-MM-DD 格式）
- travel_style: 旅行风格（可多选）
- scenery_preference: 景色偏好（可多选）

## 日期规则：
- start_date 和 end_date 是必填项
- 日期格式必须是 YYYY-MM-DD

## 生成问题的规则：
- 问题要基于用户已说的内容进行针对性提问
- 例：用户说"想去西安"，已提取 destination=西安，还缺出发地 → "去西安的话，你从哪个城市出发呢？"

## 选项生成规则：
- destination/departure：提供热门城市选项 + 允许自定义
- travel_style：提供选项（特种兵/深度游/休闲游/亲子游/蜜月游），允许多选
- scenery_preference：提供选项（Citywalk/自然景观/人文景观/美食探店/摄影打卡/户外探险），允许多选
- start_date/end_date：不提供选项，用日期输入（is_date=true）

## 输出格式（严格 JSON）：
{
  "extracted": {"destination":"","departure":"","start_date":"","end_date":"","travel_style":"","scenery_preference":""},
  "next_question": {"field":"departure","question":"去西安的话，你从哪个城市出发呢？","options":["北京","上海"],"multi":false,"allow_custom":true,"is_date":false},
  "reasoning": "..."
}

如果所有必填信息已收集完毕，next_question 设为 null。"""

    collected_str = json.dumps(collected, ensure_ascii=False) if collected else "{}"
    user_content = f"用户原始消息：{message}\n\n已收集信息：{collected_str}"
    if history:
        user_content += f"\n\n对话历史：\n{chr(10).join(history[-6:])}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    try:
        result, cost = await hunyuan_service.chat_json(messages, LOCAL_USER_ID, ScenarioType.TRAVEL)
    except ApiNotConfiguredError as e:
        return {"error": str(e)}

    extracted = result.get("extracted", {})
    for field in required_fields:
        new_val = extracted.get(field, "")
        if new_val:
            collected[field] = str(new_val)

    missing = [f for f in required_fields if not collected.get(f)]
    ready = len(missing) == 0

    DATE_QUESTIONS = {
        "start_date": {"field": "start_date", "question": "你计划几号出发？（请选择日期）", "options": [], "multi": False, "allow_custom": True, "is_date": True},
        "end_date": {"field": "end_date", "question": "你计划几号回来？（请选择日期）", "options": [], "multi": False, "allow_custom": True, "is_date": True},
    }

    next_question = None
    date_missing = [f for f in ("start_date", "end_date") if not collected.get(f)]
    if date_missing:
        next_question = DATE_QUESTIONS[date_missing[0]]
    elif not ready:
        llm_q = result.get("next_question")
        if llm_q and llm_q.get("field") in missing:
            next_question = llm_q
        else:
            next_field = missing[0]
            defaults = {
                "destination": ("你想去哪里旅游？", ["杭州", "成都", "西安", "厦门", "三亚", "丽江"], False),
                "departure": ("你从哪里出发？", ["北京", "上海", "广州", "深圳", "杭州", "成都"], False),
                "travel_style": ("你喜欢的旅行风格？（可多选）", ["特种兵", "深度游", "休闲游", "亲子游", "蜜月游"], True),
                "scenery_preference": ("你更偏好哪种体验？（可多选）", ["Citywalk", "自然景观", "人文景观", "美食探店", "摄影打卡", "户外探险"], True),
            }
            q, opts, multi = defaults.get(next_field, (f"请提供{next_field}", [], False))
            next_question = {"field": next_field, "question": q, "options": opts, "multi": multi, "allow_custom": True, "is_date": False}
    else:
        if not collected.get("extra_notes"):
            next_question = {"field": "extra_notes", "question": "您还有什么其他需求吗？（默认无，直接确认即可）", "options": ["无"], "multi": False, "allow_custom": True, "is_date": False}
            ready = False
        else:
            next_question = None

    return {
        "collected": collected,
        "missing": missing,
        "next_question": next_question,
        "ready": ready,
        "reasoning": result.get("reasoning", ""),
    }


@router.post("/travel/generate")
async def generate_plan(req: GeneratePlanRequest) -> dict:
    """生成旅游计划 Markdown（调用 LLM）。"""
    days = req.days
    if not days and req.start_date and req.end_date:
        try:
            from datetime import datetime
            d1 = datetime.strptime(req.start_date, "%Y-%m-%d")
            d2 = datetime.strptime(req.end_date, "%Y-%m-%d")
            days = max(1, (d2 - d1).days + 1)
        except (ValueError, TypeError):
            days = 3

    user_content = (
        f"出发地：{req.departure}\n"
        f"目的地：{req.destination}\n"
    )
    if req.start_date and req.end_date:
        user_content += f"出发日期：{req.start_date}\n结束日期：{req.end_date}\n天数：{days}天\n"
    else:
        user_content += f"天数：{days}天\n"
    user_content += (
        f"旅行风格：{req.travel_style}\n"
        f"景色偏好：{req.scenery_preference}\n"
    )
    if req.budget:
        user_content += f"预算：{req.budget}\n"
    if req.extra_notes:
        user_content += f"备注：{req.extra_notes}\n"
    user_content += f"\n请为从{req.departure}出发到{req.destination}的{days}日{req.travel_style}生成详细行程。"

    messages = [
        {"role": "system", "content": TRAVEL_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        raw_output, cost = await hunyuan_service.chat_markdown(
            messages, LOCAL_USER_ID, ScenarioType.TRAVEL
        )
    except ApiNotConfiguredError as e:
        return {"error": str(e)}

    if "===SPLIT===" in raw_output:
        parts = raw_output.split("===SPLIT===", 1)
        markdown_content = parts[0].strip()
        json_str = parts[1].strip()
    else:
        markdown_content = raw_output
        json_str = ""

    start_ts = 0
    base_date = None
    if req.start_date:
        try:
            from datetime import datetime
            base_date = datetime.strptime(req.start_date, "%Y-%m-%d")
            start_ts = int(base_date.timestamp())
        except (ValueError, TypeError):
            pass

    plan = TravelPlan(
        session_id=LOCAL_USER_ID,
        title=f"{req.destination}{days}日{req.travel_style}行程",
        departure=req.departure,
        destination=req.destination,
        days=days,
        travel_style=req.travel_style,
        scenery_preference=req.scenery_preference,
        budget=req.budget,
        extra_notes=req.extra_notes,
        markdown_content=markdown_content,
    )

    parsed_schedules = []
    if json_str:
        parsed_schedules = await _parse_schedule_json(json_str, base_date, days, req.destination)

    agent_plan = {}
    try:
        from agents.travel import TravelAgent
        agent_plan = await TravelAgent().plan_trip_dict({
            "departure": req.departure,
            "destination": req.destination,
            "days": days,
            "start_date": req.start_date,
            "end_date": req.end_date,
            "travel_style": req.travel_style,
            "scenery_preference": req.scenery_preference,
            "budget": req.budget,
            "extra_notes": req.extra_notes,
        })
    except Exception as e:
        agent_plan = {"error": f"TravelAgent v1 规划失败：{type(e).__name__}: {e}"}

    return {
        "plan": plan.model_dump(),
        "cost": cost.model_dump(),
        "start_date": req.start_date,
        "end_date": req.end_date,
        "start_ts": start_ts,
        "parsed_schedules": parsed_schedules,
        "agent_plan": agent_plan,
    }


@router.post("/travel/plans")
async def create_plan(req: SavePlanRequest) -> dict:
    plan = TravelPlan(**req.plan)
    plan.session_id = LOCAL_USER_ID
    await save_plan(plan)
    return {"ok": True, "plan_id": plan.id}


@router.get("/travel/plans/{session_id}")
async def list_user_plans(session_id: str) -> dict:
    plans = await list_plans(LOCAL_USER_ID)
    return {"plans": plans}


@router.get("/travel/plans/{session_id}/{plan_id}")
async def get_user_plan(session_id: str, plan_id: str) -> dict:
    plan = await get_plan(plan_id)
    if plan is None or plan.session_id != LOCAL_USER_ID:
        return {"plan": None}
    return {"plan": plan.model_dump()}


@router.put("/travel/plans/{session_id}/{plan_id}")
async def update_user_plan(session_id: str, plan_id: str, req: SavePlanRequest) -> dict:
    existing = await get_plan(plan_id)
    if existing is None or existing.session_id != LOCAL_USER_ID:
        return {"ok": False, "error": "计划不存在"}
    plan = TravelPlan(**req.plan)
    plan.id = plan_id
    plan.session_id = LOCAL_USER_ID
    plan.created_at = existing.created_at
    await update_plan(plan)
    return {"ok": True}


@router.delete("/travel/plans/{session_id}/{plan_id}")
async def delete_user_plan(session_id: str, plan_id: str) -> dict:
    existing = await get_plan(plan_id)
    if existing is None or existing.session_id != LOCAL_USER_ID:
        return {"ok": False}
    ok = await delete_plan(plan_id)
    return {"ok": ok}


# ============ 通用日程 ============

@router.get("/schedules/{session_id}")
async def list_user_schedules(session_id: str) -> dict:
    items = await list_schedules(LOCAL_USER_ID)
    return {"schedules": items}


@router.post("/schedules")
async def create_schedule(req: SaveScheduleRequest) -> dict:
    sched_data = {**req.schedule, "session_id": LOCAL_USER_ID}
    item = ScheduleItem(**sched_data)
    await save_schedule(item)
    conflicts = await check_conflict(
        LOCAL_USER_ID, item.start_time, item.duration_minutes, exclude_id=item.id
    )
    return {"ok": True, "schedule_id": item.id, "conflicts": conflicts}


@router.put("/schedules/{session_id}/{schedule_id}")
async def update_user_schedule(session_id: str, schedule_id: str, req: SaveScheduleRequest) -> dict:
    existing = await get_schedule(schedule_id)
    if existing is None or existing.session_id != LOCAL_USER_ID:
        return {"ok": False, "error": "日程不存在"}
    item_data = {**req.schedule, "session_id": LOCAL_USER_ID, "id": schedule_id, "created_at": existing.created_at}
    item = ScheduleItem(**item_data)
    await update_schedule(item)
    return {"ok": True}


@router.delete("/schedules/{session_id}/{schedule_id}")
async def delete_user_schedule(session_id: str, schedule_id: str) -> dict:
    existing = await get_schedule(schedule_id)
    if existing is None or existing.session_id != LOCAL_USER_ID:
        return {"ok": False}
    ok = await delete_schedule(schedule_id)
    return {"ok": ok}


@router.patch("/schedules/{session_id}/{schedule_id}/done")
async def toggle_schedule_done(session_id: str, schedule_id: str, done: bool = True) -> dict:
    existing = await get_schedule(schedule_id)
    if existing is None or existing.session_id != LOCAL_USER_ID:
        return {"ok": False}
    ok = await toggle_done(schedule_id, done)
    return {"ok": ok}


# ============ 腾讯地图 ============

@router.post("/map/route")
async def plan_route(req: dict) -> dict:
    """规划城市间路线。"""
    origin = req.get("origin", "")
    destination = req.get("destination", "")
    waypoints = req.get("waypoints", [])
    if not origin or not destination:
        return {"error": "请提供出发地和目的地"}
    result = await map_service.plan_travel_route(origin, destination, waypoints)
    return result


@router.get("/map/search")
async def search_places(city: str, keyword: str, category: str = "") -> dict:
    """搜索地点。"""
    results = await map_service.place_search(keyword, city)
    plans = []
    for r in results[:5]:
        loc = r.get("location", {})
        plans.append({
            "id": r.get("id", ""),
            "title": r.get("title", ""),
            "address": r.get("address", ""),
            "tel": r.get("tel", ""),
            "category": r.get("category", ""),
            "lat": loc.get("lat", 0),
            "lng": loc.get("lng", 0),
            "distance": r.get("_distance", 0),
        })
    return {"plans": plans, "city": city, "keyword": keyword}


@router.post("/map/daily-route")
async def plan_daily_route(req: dict) -> dict:
    """规划一天内多个地点之间的路线（四层架构优化版）。

    流程：POI数据库查询 → 坐标缓存 → 距离矩阵(1次API) → TSP排序 → Direction waypoints(1次API)
    缓存命中时仅消耗 2 次地图 API。
    """
    from services.poi_service import match_poi
    from services.geo_cache import get_coords

    city = req.get("city", "")
    locations_input = req.get("locations", [])
    api_call_count = 0  # 统计本次调用的地图 API 次数

    if len(locations_input) < 2:
        return {"error": "至少需要2个地点才能规划路线"}

    # 1. POI 数据库查询（0 次 API）
    resolved = []
    for loc in locations_input:
        keyword = loc.get("keyword", "")
        if not keyword:
            continue

        poi = await match_poi(city, keyword)
        if poi:
            resolved.append({
                "id": loc.get("id", ""),
                "keyword": keyword,
                "name": poi["name"],
                "address": poi["address"],
                "lat": poi["lat"],
                "lng": poi["lng"],
                "alternatives": poi.get("alternatives", []),
                "ticket": poi.get("ticket", 0),
                "cost_estimate": poi.get("cost_estimate", 0),
                "stay_time": poi.get("stay_time", 60),
                "place_type": poi.get("place_type", "other"),
            })

    if len(resolved) < 2:
        return {"error": "无法找到足够的地标来规划路线"}

    # 2. 距离矩阵（1 次 API）
    points = [{"lat": r["lat"], "lng": r["lng"], "name": r["name"]} for r in resolved]
    matrix = await map_service.batch_distance_matrix(points)
    api_call_count += 1

    # 3. TSP 最近邻排序（0 次 API，本地计算）
    if len(resolved) > 2:
        order = _tsp_nearest_neighbor(matrix)
        resolved = [resolved[i] for i in order]
        points = [{"lat": r["lat"], "lng": r["lng"], "name": r["name"]} for r in resolved]

    # 4. Direction waypoints（1 次 API，一次规划完整路线）
    try:
        route = await map_service.direction_with_waypoints(points)
    except RuntimeError as e:
        return {"error": str(e)}
    api_call_count += 1

    total_distance = route["distance"]
    total_duration = route["duration"]
    total_toll = route["toll"]
    all_polyline = route["polyline"]

    # 5. 构建路段信息（从 polyline 拆分，不额外调 API）
    segments = []
    for i in range(len(resolved) - 1):
        segments.append({
            "from": resolved[i]["name"],
            "to": resolved[i + 1]["name"],
            "distance": 0,  # waypoints 模式不返回逐段距离
            "duration": 0,
            "toll": 0,
            "polyline": [],
        })

    # 6. 费用估算 = 交通费 + POI 门票/餐饮/酒店
    distance_km = total_distance / 1000
    transport_cost = {
        "self_driving": round(distance_km * 0.7 + total_toll),
        "taxi": round(distance_km * 3),
        "toll": total_toll,
    }

    # POI 费用汇总
    poi_cost = sum(r.get("cost_estimate", 0) for r in resolved)
    total_cost = transport_cost["self_driving"] + poi_cost

    # 7. 天气（使用缓存 adcode，命中时 0 次 API）
    weather = await map_service.get_weather(city)

    return {
        "city": city,
        "locations": resolved,
        "segments": segments,
        "polyline": all_polyline,
        "total_distance": total_distance,
        "total_duration": total_duration,
        "total_distance_km": round(distance_km, 1),
        "total_duration_hours": round(total_duration / 3600, 1),
        "total_toll": total_toll,
        "cost_estimate": {
            **transport_cost,
            "poi_cost": poi_cost,
            "total": total_cost,
        },
        "weather": weather,
        "api_calls": api_call_count,
    }


def _tsp_nearest_neighbor(matrix: list[list[dict]]) -> list[int]:
    """TSP 最近邻算法：从第 0 个点出发，每次选最近的未访问点。

    Returns: 访问顺序索引列表
    """
    n = len(matrix)
    if n <= 2:
        return list(range(n))

    visited = [False] * n
    order = [0]
    visited[0] = True

    for _ in range(n - 1):
        current = order[-1]
        nearest = -1
        min_dist = float("inf")
        for j in range(n):
            if not visited[j]:
                d = matrix[current][j]["distance"]
                if d < min_dist and d > 0:
                    min_dist = d
                    nearest = j
        if nearest == -1:
            # 所有剩余点距离为 0，按原顺序
            for j in range(n):
                if not visited[j]:
                    nearest = j
                    break
        order.append(nearest)
        visited[nearest] = True

    return order


# ============ 会议创建 ============

@router.post("/meeting/create")
async def create_meeting(req: MeetingCreateRequest) -> dict:
    """从用户消息中提取会议信息，调用 tmeet CLI 创建腾讯会议。"""
    # 1. LLM 提取会议信息
    messages = [
        {"role": "system", "content": MEETING_EXTRACT_PROMPT},
        {"role": "user", "content": f"用户消息：{req.message}\n当前日期：{date.today().isoformat()}"},
    ]

    try:
        result, cost = await hunyuan_service.chat_json(
            messages, LOCAL_USER_ID, ScenarioType.MEETING, max_tokens=200
        )
    except ApiNotConfiguredError as e:
        return {"error": str(e)}

    if not result.get("detected", False):
        return {"ok": False, "error": "未检测到明确的会议意图"}

    subject = result.get("subject", "快速会议")
    start_iso = result.get("start_time", "")
    duration = result.get("duration_minutes", 60)

    if not start_iso:
        return {"ok": False, "error": "无法确定会议时间"}

    # 计算 end_time
    try:
        from datetime import datetime, timedelta
        dt = datetime.fromisoformat(start_iso)
        end_dt = dt + timedelta(minutes=duration)
        end_iso = end_dt.isoformat()
    except (ValueError, TypeError):
        return {"ok": False, "error": f"时间格式错误: {start_iso}"}

    # 2. 调用 tmeet 创建会议
    meeting_result = await meeting_service.create_meeting(subject, start_iso, end_iso)
    return meeting_result


@router.get("/meeting/status")
async def meeting_status() -> dict:
    """检查 tmeet CLI 安装和授权状态。"""
    return await meeting_service.check_auth()


# ============ AI 生图 ============

@router.post("/image/generate")
async def generate_image(req: dict) -> dict:
    """调用混元文生图，返回图片 URL。"""
    prompt = req.get("prompt", "")
    if not prompt:
        return {"error": "请提供图片描述"}

    from services.hunyuan_service import hunyuan_service, ApiNotConfiguredError

    try:
        image_url = await hunyuan_service.text_to_image(prompt)
        return {"ok": True, "image_url": image_url, "prompt": prompt}
    except ApiNotConfiguredError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"生图失败：{type(e).__name__}: {e}"}


# ============ 日程解析 ============

async def _parse_schedule_json(json_str: str, base_date, days: int, city: str = "") -> list[dict]:
    """解析 LLM 输出的结构化日程 JSON。"""
    import json as _json
    import re as _re
    from datetime import datetime, timedelta

    json_str = json_str.strip()
    if json_str.startswith("```"):
        json_str = json_str.strip("`")
        if json_str.startswith("json"):
            json_str = json_str[4:]

    try:
        data = _json.loads(json_str)
    except _json.JSONDecodeError:
        match = _re.search(r'\{.*\}', json_str, _re.DOTALL)
        if match:
            try:
                data = _json.loads(match.group())
            except _json.JSONDecodeError:
                return []
        else:
            return []

    schedules_raw = data.get("schedules", [])
    if not base_date:
        base_date = datetime.now()

    result = []
    for s in schedules_raw:
        search_q = s.get("search_query") or s.get("search_keyword", "")
        day = s.get("day", 1)
        hour = s.get("start_hour", 9)
        minute = s.get("start_minute", 0)
        dur = s.get("duration_minutes", 60)
        desc = s.get("description", "")
        cost = s.get("cost_estimate", 0)
        title = s.get("title", "活动")[:20]

        item_date = base_date + timedelta(days=day - 1)
        start_dt = item_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        start_ts = start_dt.timestamp()

        result.append({
            "title": title,
            "category": "travel",
            "start_time": start_ts,
            "duration_minutes": dur,
            "duration_days": 0,
            "location": search_q,
            "description": desc,
            "markdown_content": "",
            "extra": {
                "day": day,
                "place_type": s.get("place_type", "other"),
                "search_query": search_q,
                "city": city,
                "cost_estimate": cost,
            },
        })

    return result
