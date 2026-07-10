"""Map payload builder for frontend route rendering."""
from __future__ import annotations

from agents.travel.models import DayItinerary


class MapRenderer:
    def build_day_map(self, day: DayItinerary) -> dict:
        points = []
        for stop in day.stops:
            points.append({
                "id": stop.poi.poi_id,
                "name": stop.poi.name,
                "lat": stop.poi.lat,
                "lng": stop.poi.lng,
                "category": stop.poi.category.value,
                "start_time": f"{stop.start_hour:02d}:{stop.start_minute:02d}",
                "duration_minutes": stop.duration_minutes,
                "alternatives": [
                    {"id": alt.poi_id, "name": alt.name, "lat": alt.lat, "lng": alt.lng, "category": alt.category.value}
                    for alt in stop.alternatives
                ],
            })
        return {"day": day.day, "points": points, "polyline": [], "provider": "local_v1"}