"""Collect due, overdue, and conflicting schedule signals."""
from __future__ import annotations

import json
import time
from typing import Any

from agent.collectors.base import CollectedSignal, CollectionBatch
from database.connection import get_db
from database.repositories.conversation_repo import LOCAL_USER_ID


class ScheduleCollector:
    name = "schedule"

    def __init__(
        self,
        lookahead_minutes: int = 30,
        overdue_lookback_minutes: int = 60,
        scan_interval_seconds: int = 60,
    ) -> None:
        self.lookahead_minutes = max(1, lookahead_minutes)
        self.overdue_lookback_minutes = max(1, overdue_lookback_minutes)
        self.scan_interval_seconds = max(10, scan_interval_seconds)

    async def collect(
        self,
        checkpoint: dict[str, Any] | None = None,
        *,
        now: float | None = None,
    ) -> CollectionBatch:
        previous = dict(checkpoint or {})
        ts = now or time.time()
        upper = ts + self.lookahead_minutes * 60
        last_scan = float(previous.get("last_scan_at") or (ts - self.overdue_lookback_minutes * 60))
        overdue_lower = max(last_scan, ts - self.overdue_lookback_minutes * 60)
        db = await get_db()

        cursor = await db.execute(
            "SELECT * FROM schedules WHERE session_id=? AND done=0 AND start_time>? AND start_time<=? "
            "ORDER BY start_time,id",
            (LOCAL_USER_ID, overdue_lower, upper),
        )
        rows = [dict(row) for row in await cursor.fetchall()]
        events: list[CollectedSignal] = []

        for item in rows:
            start_time = float(item.get("start_time") or 0)
            if start_time <= 0:
                continue
            base_payload = {
                "schedule_id": item["id"],
                "title": item.get("title") or "未命名日程",
                "start_time": start_time,
                "duration_minutes": int(item.get("duration_minutes") or 0),
                "location": item.get("location") or "",
                "category": item.get("category") or "other",
                "minutes_until": round((start_time - ts) / 60),
            }
            if start_time > ts:
                events.append(
                    CollectedSignal(
                        event_type="schedule.due",
                        source="schedule_collector",
                        subject_id=str(item["id"]),
                        occurred_at=ts,
                        dedup_key=f"schedule-due:{item['id']}:{int(start_time)}:{self.lookahead_minutes}",
                        payload=base_payload,
                    )
                )
            else:
                events.append(
                    CollectedSignal(
                        event_type="schedule.overdue",
                        source="schedule_collector",
                        subject_id=str(item["id"]),
                        occurred_at=ts,
                        dedup_key=f"schedule-overdue:{item['id']}:{int(start_time)}",
                        payload={**base_payload, "minutes_overdue": max(0, round((ts - start_time) / 60))},
                    )
                )

        upcoming = [item for item in rows if float(item.get("start_time") or 0) > ts]
        for index, left in enumerate(upcoming):
            left_start = float(left.get("start_time") or 0)
            left_end = left_start + max(0, int(left.get("duration_minutes") or 0)) * 60
            if left_end <= left_start:
                continue
            for right in upcoming[index + 1 :]:
                right_start = float(right.get("start_time") or 0)
                if right_start >= left_end:
                    break
                right_end = right_start + max(0, int(right.get("duration_minutes") or 0)) * 60
                if right_end <= right_start:
                    continue
                pair = sorted([str(left["id"]), str(right["id"])])
                events.append(
                    CollectedSignal(
                        event_type="schedule.conflict",
                        source="schedule_collector",
                        subject_id=pair[0],
                        occurred_at=ts,
                        dedup_key=(
                            f"schedule-conflict:{pair[0]}:{int(left_start)}:"
                            f"{pair[1]}:{int(right_start)}"
                        ),
                        payload={
                            "schedule_ids": pair,
                            "left": {
                                "id": left["id"],
                                "title": left.get("title") or "未命名日程",
                                "start_time": left_start,
                                "duration_minutes": int(left.get("duration_minutes") or 0),
                            },
                            "right": {
                                "id": right["id"],
                                "title": right.get("title") or "未命名日程",
                                "start_time": right_start,
                                "duration_minutes": int(right.get("duration_minutes") or 0),
                            },
                            "overlap_seconds": max(0, min(left_end, right_end) - right_start),
                        },
                    )
                )

        counts: dict[str, int] = {}
        for event in events:
            counts[event.event_type] = counts.get(event.event_type, 0) + 1
        return CollectionBatch(
            events=events,
            next_checkpoint={
                **previous,
                "schema_version": 1,
                "last_scan_at": ts,
                "last_count": len(events),
                "event_counts": counts,
            },
            next_run_at=ts + self.scan_interval_seconds,
            diagnostics={
                "rows_scanned": len(rows),
                "event_counts": counts,
                "window": {"from": overdue_lower, "to": upper},
            },
        )
