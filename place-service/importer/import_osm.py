"""Normalize named POIs from an OSM PBF into the private place database."""
from __future__ import annotations

import argparse
import os
from uuid import uuid4

import osmium
import psycopg

from place_rules import category_for, compact_aliases, importance, is_place


UPSERT = """
INSERT INTO places (id,name,name_zh,name_en,aliases,city,country_code,category,address,phone,
 importance,source,source_region,import_run_id,source_updated_at,geom)
VALUES (%(id)s,%(name)s,%(name_zh)s,%(name_en)s,%(aliases)s,%(city)s,%(country_code)s,%(category)s,
 %(address)s,%(phone)s,%(importance)s,'openstreetmap',%(source_region)s,%(import_run_id)s,now(),
 ST_SetSRID(ST_MakePoint(%(lng)s,%(lat)s),4326))
ON CONFLICT (id) DO UPDATE SET name=excluded.name,name_zh=excluded.name_zh,
 name_en=excluded.name_en,aliases=excluded.aliases,city=excluded.city,country_code=excluded.country_code,
 category=excluded.category,address=excluded.address,phone=excluded.phone,
 importance=excluded.importance,source_region=excluded.source_region,
 import_run_id=excluded.import_run_id,source_updated_at=excluded.source_updated_at,geom=excluded.geom
"""


class PlaceHandler(osmium.SimpleHandler):
    def __init__(self, connection, batch_size: int = 3000, *, source_region: str = "",
                 country_code: str = "", import_run_id: str = ""):
        super().__init__()
        self.connection, self.batch_size = connection, batch_size
        self.source_region = source_region
        self.country_code = country_code
        self.import_run_id = import_run_id or str(uuid4())
        self.batch: list[dict] = []
        self.total = 0

    def _append(self, osm_type: str, osm_id: int, tags: dict[str, str], lat: float, lng: float):
        if not is_place(tags) or not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return
        address = " ".join(filter(None, (tags.get("addr:province"), tags.get("addr:city"),
            tags.get("addr:district"), tags.get("addr:place"), tags.get("addr:street"),
            tags.get("addr:housenumber"))))
        self.batch.append({
            "id": f"osm:{osm_type}:{osm_id}", "name": tags.get("name") or tags.get("name:zh") or tags.get("name:en"),
            "name_zh": tags.get("name:zh", ""), "name_en": tags.get("name:en", ""),
            "aliases": compact_aliases(tags),
            "city": (tags.get("addr:city") or tags.get("addr:town") or tags.get("is_in:city")
                     or tags.get("is_in:town") or tags.get("addr:place") or tags.get("is_in") or ""),
            "country_code": tags.get("addr:country", "").lower() or self.country_code,
            "category": category_for(tags),
            "address": address, "phone": tags.get("contact:phone") or tags.get("phone") or "",
            "importance": importance(tags), "source_region": self.source_region,
            "import_run_id": self.import_run_id, "lat": lat, "lng": lng,
        })
        if len(self.batch) >= self.batch_size:
            self.flush()

    def node(self, node):
        if node.location.valid():
            self._append("node", node.id, dict(node.tags), node.location.lat, node.location.lon)

    def way(self, way):
        tags = dict(way.tags)
        if not is_place(tags):
            return
        locations = [node.location for node in way.nodes if node.location.valid()]
        if locations:
            self._append("way", way.id, tags, sum(x.lat for x in locations) / len(locations),
                         sum(x.lon for x in locations) / len(locations))

    def flush(self):
        if not self.batch:
            return
        with self.connection.cursor() as cursor:
            cursor.executemany(UPSERT, self.batch)
        self.connection.commit()
        self.total += len(self.batch)
        print(f"imported={self.total}", flush=True)
        self.batch.clear()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pbf")
    parser.add_argument("--batch-size", type=int, default=3000)
    parser.add_argument("--region", default="")
    parser.add_argument("--country-code", default="")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    with psycopg.connect(database_url) as connection:
        handler = PlaceHandler(connection, max(100, args.batch_size), source_region=args.region,
                               country_code=args.country_code.lower())
        handler.apply_file(args.pbf, locations=True, idx="sparse_file_array")
        handler.flush()
        if args.region:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM places WHERE source='openstreetmap' AND source_region=%s "
                    "AND import_run_id IS DISTINCT FROM %s::uuid",
                    (args.region, handler.import_run_id),
                )
                removed = cursor.rowcount
            connection.commit()
            print(f"removed_stale={removed}", flush=True)
        print(f"complete imported={handler.total}")


if __name__ == "__main__":
    main()
