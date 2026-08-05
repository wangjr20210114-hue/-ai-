"""Print redacted fake search critical-path p50/p95 metrics."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from search_critical_path import run_fake_critical_path


def percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


async def main(turns: int) -> int:
    results = await asyncio.gather(
        *(run_fake_critical_path(index) for index in range(turns)),
    )
    first_tokens = [item.first_token_ms for item in results]
    output = {
        "mode": "fake",
        "turns": turns,
        "queries": "redacted",
        "plan_p50_ms": round(percentile([item.plan_ms for item in results], 0.50), 1),
        "plan_p95_ms": round(percentile([item.plan_ms for item in results], 0.95), 1),
        "sources_p50_ms": round(
            percentile([item.sources_ms for item in results], 0.50),
            1,
        ),
        "sources_p95_ms": round(
            percentile([item.sources_ms for item in results], 0.95),
            1,
        ),
        "first_token_p50_ms": round(percentile(first_tokens, 0.50), 1),
        "first_token_p95_ms": round(percentile(first_tokens, 0.95), 1),
        "provider_requests_per_turn": round(
            sum(item.provider_requests for item in results) / turns,
            2,
        ),
        "answer_graph_has_rich_search": any(
            "rich_search" in item.graph_tool_names
            for item in results
        ),
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return int(
        output["provider_requests_per_turn"] != 1
        or output["first_token_p95_ms"] >= 2_500
        or not output["answer_graph_has_rich_search"]
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fake",
        action="store_true",
        help="run the credential-free deterministic fake",
    )
    parser.add_argument("--turns", type=int, default=20)
    arguments = parser.parse_args()
    if not arguments.fake:
        parser.error("only the redacted --fake benchmark is supported")
    raise SystemExit(asyncio.run(main(max(1, min(100, arguments.turns)))))
