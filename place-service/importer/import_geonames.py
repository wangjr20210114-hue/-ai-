"""Import important global cities and landmarks from a GeoNames dump."""
from __future__ import annotations

import argparse
import os
import zipfile

import psycopg


LANDMARK_CODES = {"MUS", "MUSM", "MSTY", "PAL", "CSTL", "RUIN", "PYR", "TMPL", "CH", "MNMT",
                  "PRK", "RES", "RGN", "ISL", "MT", "PK", "CAVE", "BAY", "FLLS", "BCH"}


def keep(feature_class: str, feature_code: str, population: int) -> bool:
    return population >= 50_000 or feature_code in LANDMARK_CODES


UPSERT = """
INSERT INTO places (id,name,name_en,aliases,city,country_code,category,importance,source,
 source_updated_at,geom)
VALUES (%(id)s,%(name)s,%(name_en)s,%(aliases)s,%(city)s,%(country_code)s,%(category)s,
 %(importance)s,'geonames',now(),
 ST_SetSRID(ST_MakePoint(%(lng)s,%(lat)s),4326))
ON CONFLICT (id) DO UPDATE SET name=excluded.name,name_en=excluded.name_en,
 aliases=excluded.aliases,city=excluded.city,country_code=excluded.country_code,category=excluded.category,
 importance=excluded.importance,source_updated_at=excluded.source_updated_at,
 geom=excluded.geom
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("zipfile")
    parser.add_argument("--batch-size", type=int, default=5000)
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    batch, total = [], 0
    with psycopg.connect(database_url) as connection, zipfile.ZipFile(args.zipfile) as archive:
        text_name = next(name for name in archive.namelist() if name.endswith(".txt"))
        with archive.open(text_name) as source:
            for raw in source:
                fields = raw.decode("utf-8").rstrip("\n").split("\t")
                if len(fields) < 19:
                    continue
                population = int(fields[14] or 0)
                if not keep(fields[6], fields[7], population):
                    continue
                batch.append({
                    "id": f"geonames:{fields[0]}", "name": fields[1], "name_en": fields[2],
                    "aliases": " ".join(fields[3].split(",")[:20])[:1000],
                    "city": fields[1] if fields[6] == "P" else "", "country_code": fields[8].lower(),
                    "category": "other" if fields[6] == "P" else "attraction",
                    "importance": min(1.0, 0.1 + population / 10_000_000),
                    "lat": float(fields[4]), "lng": float(fields[5]),
                })
                if len(batch) >= args.batch_size:
                    with connection.cursor() as cursor:
                        cursor.executemany(UPSERT, batch)
                    connection.commit(); total += len(batch); batch.clear()
                    print(f"imported={total}", flush=True)
        if batch:
            with connection.cursor() as cursor:
                cursor.executemany(UPSERT, batch)
            connection.commit(); total += len(batch)
    print(f"complete imported={total}")


if __name__ == "__main__":
    main()
