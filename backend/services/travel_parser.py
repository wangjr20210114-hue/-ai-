"""旅游行程 Markdown 解析器：把 LLM 生成的 Markdown 行程解析成结构化日程项。

解析规则：
- ## Day N（日期）→ 一天的日程
- ### 上午/中午/下午/晚上 → 时段
- - **HH:MM-HH:MM**：**地点名** → 定时日程项
- - **地点名**（无时间）→ 全天/时段日程项

每个日程项包含：title, start_time(时间戳), duration_minutes, location, description
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from typing import Any


def parse_travel_markdown(
    markdown: str, start_date: str, days: int
) -> list[dict[str, Any]]:
    """解析旅游 Markdown 行程为结构化日程项列表。

    参数：
    - markdown: LLM 生成的 Markdown 行程文本
    - start_date: 出发日期 "YYYY-MM-DD"
    - days: 天数

    返回：[{title, start_time, duration_minutes, location, description, day_index}, ...]
    """
    items: list[dict[str, Any]] = []
    
    # 解析出发日期
    try:
        base_date = datetime.strptime(start_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        base_date = datetime.now()

    lines = markdown.split("\n")
    current_day = 0  # 第几天（0-indexed）
    current_period = ""  # 上午/中午/下午/晚上
    current_day_title = ""

    # 时间正则：**09:00-12:00** 或 **09:00** 或 **9:00-12:00**
    time_pattern = re.compile(
        r"\*{0,2}(\d{1,2}):(\d{2})\s*[-—~至到]\s*(\d{1,2}):(\d{2})\*{0,2}"
    )
    # Day 标题
    day_pattern = re.compile(r"^##\s+.*Day\s*(\d+)", re.IGNORECASE)
    # 时段标题
    period_pattern = re.compile(r"^###\s+(上午|中午|下午|傍晚|晚上|夜间|早晨|清晨)")

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 匹配 Day 标题
        day_match = day_pattern.search(line)
        if day_match:
            current_day = int(day_match.group(1)) - 1
            current_day_title = line
            i += 1
            continue

        # 匹配时段标题
        period_match = period_pattern.search(line)
        if period_match:
            current_period = period_match.group(1)
            i += 1
            continue

        # 匹配时间+地点行
        # 格式：- **09:00-12:00**：**龙井村 & 龙井问茶**
        # 或：- 09:00-12:00：龙井村
        if line.startswith("- ") or line.startswith("* "):
            content = line[2:].strip()
            
            time_match = time_pattern.search(content)
            if time_match:
                start_h = int(time_match.group(1))
                start_m = int(time_match.group(2))
                end_h = int(time_match.group(3))
                end_m = int(time_match.group(4))

                # 计算日期
                item_date = base_date + timedelta(days=current_day)
                start_dt = item_date.replace(hour=start_h, minute=start_m, second=0)
                end_dt = item_date.replace(hour=end_h, minute=end_m, second=0)
                
                # 如果结束时间小于开始时间，跨天
                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)

                duration = int((end_dt - start_dt).total_seconds() / 60)

                # 提取地点名（去掉时间部分后的文本）
                location_text = time_pattern.sub("", content).strip()
                # 去掉前导冒号、星号
                location_text = re.sub(r"^[\s:：\*]+", "", location_text)
                # 去掉 ** 包裹
                location_text = re.sub(r"\*\*", "", location_text)
                # 取第一个逗号/句号前的部分作为标题
                title = location_text.split("，")[0].split("。")[0].split("（")[0].strip()
                
                # 提取地点（粗略提取）
                location = ""
                # 查找括号内的地址
                addr_match = re.search(r"[（(]([^）)]*(?:地址|路|号|街|号|店|站|地铁))[）)]", location_text)
                if addr_match:
                    location = addr_match.group(1)

                # 如果标题太长，截断
                if len(title) > 40:
                    title = title[:40] + "..."

                items.append({
                    "title": title or f"第{current_day+1}天{current_period}活动",
                    "start_time": start_dt.timestamp(),
                    "duration_minutes": duration,
                    "location": location or title,
                    "description": location_text,
                    "day_index": current_day,
                    "period": current_period,
                })

        i += 1

    return items


def parse_travel_plan_to_schedules(
    markdown: str, start_date: str, days: int, destination: str = ""
) -> list[dict[str, Any]]:
    """解析旅游计划 Markdown 为日程项（可直接存入 schedules 表）。

    返回：[{title, category, start_time, duration_minutes, location, description, markdown_content}, ...]
    """
    parsed = parse_travel_markdown(markdown, start_date, days)
    
    schedules = []
    for item in parsed:
        schedules.append({
            "title": item["title"],
            "category": "travel",
            "start_time": item["start_time"],
            "duration_minutes": item["duration_minutes"],
            "duration_days": 0,
            "location": item.get("location", ""),
            "description": f"{item.get('period','')} · {item.get('description','')}",
            "markdown_content": "",
            "extra": {"day_index": item.get("day_index", 0)},
        })
    
    return schedules
