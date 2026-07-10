"""Import and clean POI data from medium or large offline datasets."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from agents.travel.place_db.schema import PlaceRecord
from agents.travel.place_db.tagger import clean_record


@dataclass(slots=True)
class ImportReport:
    total_rows: int = 0
    imported: int = 0
    skipped: int = 0
    duplicates: int = 0
    errors: list[str] = field(default_factory=list)


def iter_place_rows(path: str | Path) -> Iterator[dict]:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".jsonl":
        with source.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)
        return
    if suffix == ".json":
        data = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(data, list):
            for item in data:
                yield item
        elif isinstance(data, dict):
            for item in data.get("places", data.get("items", [])):
                yield item
        return
    if suffix == ".csv":
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            yield from csv.DictReader(handle)
        return
    if suffix == ".parquet":
        try:
            import pandas as pd  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("Parquet import requires pandas/pyarrow installed") from exc
        for item in pd.read_parquet(source).to_dict(orient="records"):
            yield item
        return
    raise ValueError(f"Unsupported place data format: {source.suffix}")


def import_records(rows: Iterable[dict]) -> tuple[list[PlaceRecord], ImportReport]:
    report = ImportReport()
    records: list[PlaceRecord] = []
    seen: set[str] = set()
    for row in rows:
        report.total_rows += 1
        try:
            record = clean_record(PlaceRecord.from_mapping(row))
            if not record:
                report.skipped += 1
                continue
            key = record.dedupe_key()
            if key in seen:
                report.duplicates += 1
                continue
            seen.add(key)
            records.append(record)
            report.imported += 1
        except Exception as exc:
            report.skipped += 1
            if len(report.errors) < 20:
                report.errors.append(f"row {report.total_rows}: {exc}")
    return records, report


def import_file(path: str | Path) -> tuple[list[PlaceRecord], ImportReport]:
    return import_records(iter_place_rows(path))
