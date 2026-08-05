"""Run a redacted, repeatable real WSA SearchPro sample benchmark.

This is intentionally opt-in: it reads an explicitly named env file, never
prints credentials, never sends generated answer text, and disables page/media
enrichment so the result measures only the factual SearchPro path.  The
production adapter remains the single implementation under test.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents._infrastructure.providers.http_transport import close_http_transport
from agents._infrastructure.providers.rich_search import rich_search


DEFAULT_QUERIES = (
    "最近 AI 有什么新进展",
    "2026 年生成式 AI 最新产品发布",
    "杭州一日游省钱路线",
    "北京故宫最新开放时间与预约规则",
    "DeepSeek 最近发布了什么新模型",
)


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        env[key.strip()] = value
    return env


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


async def run(args: argparse.Namespace) -> dict[str, Any]:
    env = load_env(Path(args.env_file))
    queries = tuple(args.query or DEFAULT_QUERIES)
    rows: list[dict[str, Any]] = []
    try:
        for round_index in range(args.rounds):
            for query_index, query in enumerate(queries):
                started = time.perf_counter()
                try:
                    result = await rich_search(
                        env,
                        query,
                        include_media=False,
                        result_limit=args.result_limit,
                        image_limit=0,
                    )
                    config = result.get("search_config") or {}
                    rows.append({
                        "round": round_index + 1,
                        "query_index": query_index + 1,
                        "ok": True,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000),
                        "provider_ms": (result.get("timings_ms") or {}).get("search"),
                        "sources": len(result.get("results") or []),
                        "source_domain_count": config.get("source_domain_count", 0),
                        "provider_request_count": config.get("provider_request_count", 0),
                    })
                except Exception as error:  # pragma: no cover - live provider branch
                    rows.append({
                        "round": round_index + 1,
                        "query_index": query_index + 1,
                        "ok": False,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000),
                        "error_type": type(error).__name__,
                    })
    finally:
        await close_http_transport()

    successful = [row for row in rows if row["ok"]]
    provider_times = [float(row["provider_ms"]) for row in successful if row.get("provider_ms") is not None]
    summary = {
        "mode": "real-wsa-searchpro",
        "rounds": args.rounds,
        "query_count": len(queries),
        "sample_count": len(rows),
        "success_count": len(successful),
        "success_rate": round(len(successful) / len(rows), 4) if rows else 0.0,
        "provider_ms_p50": round(percentile(provider_times, 0.50), 1),
        "provider_ms_p95": round(percentile(provider_times, 0.95), 1),
        "sources_p50": round(percentile([row["sources"] for row in successful], 0.50), 1),
        "domains_p50": round(percentile([row["source_domain_count"] for row in successful], 0.50), 1),
        "provider_requests": sorted({row.get("provider_request_count") for row in successful}),
        "error_types": sorted({row["error_type"] for row in rows if not row["ok"]}),
        "samples": rows,
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--result-limit", type=int, default=8)
    parser.add_argument("--query", action="append")
    args = parser.parse_args()
    args.rounds = max(1, min(5, args.rounds))
    args.result_limit = max(4, min(18, args.result_limit))
    summary = asyncio.run(run(args))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return int(
        summary["success_count"] != summary["sample_count"]
        or summary["provider_requests"] not in ([1], []),
    )


if __name__ == "__main__":
    raise SystemExit(main())
