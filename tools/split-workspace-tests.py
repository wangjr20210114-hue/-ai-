"""Split and verify the historical workspace regression suite by domain."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "agents" / "_tests" / "test_workspace.py"
SUPPORT = ROOT / "agents" / "_tests" / "support"
INVENTORY = SUPPORT / "test_inventory.json"

DOMAINS = {
    "chat/planning": ("ChatPlanningTests", ROOT / "agents/_tests/chat/test_planning.py"),
    "chat/streaming": ("ChatStreamingTests", ROOT / "agents/_tests/chat/test_streaming.py"),
    "search/pipeline": ("SearchPipelineTests", ROOT / "agents/_tests/search/test_search_pipeline.py"),
    "search/media": ("SearchMediaReviewTests", ROOT / "agents/_tests/search/test_media_review.py"),
    "workspace/calendar": ("CalendarWorkspaceTests", ROOT / "agents/_tests/workspace/test_calendar.py"),
    "workspace/workflows": ("WorkspaceWorkflowTests", ROOT / "agents/_tests/workspace/test_workflows.py"),
    "maps/places": ("MapPlaceTests", ROOT / "agents/_tests/maps/test_places.py"),
    "maps/routes/core": (
        "MapRouteCoreTests",
        ROOT / "agents/_tests/maps/test_routes_core.py",
    ),
    "maps/routes/continuations": (
        "RouteContinuationTests",
        ROOT / "agents/_tests/maps/test_route_continuations.py",
    ),
    "proactive/opportunities": ("ProactiveOpportunityTests", ROOT / "agents/_tests/proactive/test_opportunities.py"),
    "proactive/memory": ("ProactiveMemoryTests", ROOT / "agents/_tests/proactive/test_memory.py"),
    "papers/discovery": ("PaperDiscoveryTests", ROOT / "agents/_tests/papers/test_discovery.py"),
    "providers/contracts": ("ProviderContractTests", ROOT / "agents/_tests/providers/test_provider_contracts.py"),
}


def classify(test_name: str) -> str:
    value = test_name.removeprefix("test_").lower()
    words = set(value.split("_"))
    if any(token in value for token in (
        "paper", "arxiv", "openalex", "dblp", "crossref",
        "named_author", "author_institution", "title_matching",
    )):
        return "papers/discovery"
    if value.startswith("route") and any(token in value for token in (
        "calendar", "revalidates", "failure", "nearby_brand",
        "card_choices", "silently_picks", "route_change",
    )):
        return "maps/routes/continuations"
    if value.startswith("route") or any(token in value for token in (
        "latest_route", "planned_route", "multi_stop",
    )):
        return "maps/routes/core"
    if value.startswith("calendar") or value.startswith("meeting"):
        return "workspace/calendar"
    if value.startswith("hunyuan") and "workflow" in words:
        return "providers/contracts"
    if words.intersection({
        "vision", "media", "image", "images", "reference", "references", "img2img",
    }):
        return "search/media"
    if any(token in value for token in (
        "rich_search", "searchpro", "web_search", "search_preferences",
        "search_evidence", "today_filter", "publication_date", "temporal_policy",
    )):
        return "search/pipeline"
    if value.startswith("map_") or any(token in value for token in (
        "nearby", "place", "current_location", "reverse_geocode",
        "polyline", "distance", "location_tool", "browser_location",
    )):
        return "maps/places"
    if any(token in value for token in ("calendar", "schedule", "meeting")):
        return "workspace/calendar"
    if value.startswith("workspace_") or any(token in value for token in (
        "workflow", "action_snapshot", "provider_ledger", "reconciliation",
        "side_effect", "travel_plan_asset", "execution",
    )):
        return "workspace/workflows"
    if any(token in value for token in (
        "memory", "feedback", "budget", "usage", "user_assets",
    )):
        return "proactive/memory"
    if any(token in value for token in (
        "proactive", "opportunity", "notification", "reminder", "window_queues",
    )):
        return "proactive/opportunities"
    if any(token in value for token in (
        "stream", "delta", "checkpoint", "public_content", "public_answer",
        "fallback", "message_restore", "empty_generation", "recovery",
    )):
        return "chat/streaming"
    if any(token in value for token in (
        "plan", "capability", "prompt", "clarification", "history",
        "resume_protocol", "required_input", "skill_policy", "tool_protocol",
        "follow_up", "runtime_datetime", "model_timeout", "optional_or_undecided",
    )):
        return "chat/planning"
    return "providers/contracts"


def legacy_parts():
    if LEGACY.exists():
        source = LEGACY.read_text(encoding="utf-8")
    else:
        source = subprocess.check_output(
            ["git", "show", "HEAD:agents/_tests/test_workspace.py"],
            cwd=ROOT,
            encoding="utf-8",
        )
    tree = ast.parse(source)
    suite = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "WorkspaceUnitTests"
    )
    lines = source.splitlines(keepends=True)
    tests = [
        node for node in suite.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]
    return source, lines, suite, tests


def source_segment(lines, node):
    start = min(
        [node.lineno, *(item.lineno for item in node.decorator_list)],
    )
    return "".join(lines[start - 1:node.end_lineno]).replace(
        "Path(__file__).parents[1]",
        "AGENTS_ROOT",
    )


def indent_segment(segment):
    return textwrap.indent(textwrap.dedent(segment), "    ")


def write_split():
    source, lines, suite, tests = legacy_parts()
    SUPPORT.mkdir(parents=True, exist_ok=True)
    header = "".join(lines[: suite.lineno - 1])
    fake_start = next(
        node.lineno for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name == "FakeStore"
    )
    environment = "".join(lines[: fake_start - 1])
    fake_source = "".join(lines[fake_start - 1:suite.lineno - 1])
    fakes_header = (
        "from __future__ import annotations\n\n"
        "import asyncio\n"
        "from types import SimpleNamespace\n\n"
        "from agents._tests.auth_helpers import auth_env, auth_headers\n\n\n"
    )
    (SUPPORT / "fakes.py").write_text(fakes_header + fake_source, encoding="utf-8")
    environment += (
        "\nfrom agents._tests.support.fakes import (\n"
        "    FakeCheckpointer,\n"
        "    FakeContext,\n"
        "    FakeRequest,\n"
        "    FakeStore,\n"
        "    FakeStores,\n"
        "    FailingStructuredPlannerModel,\n"
        "    MakersCheckpointMessage,\n"
        "    RecoveringStructuredPlannerModel,\n"
        "    StructuredPlannerModel,\n"
        ")\n\n"
        "AGENTS_ROOT = Path(__file__).resolve().parents[2]\n\n"
        "__all__ = [name for name in globals() if not name.startswith('__')]\n"
    )
    (SUPPORT / "workspace_environment.py").write_text(environment, encoding="utf-8")

    grouped = {key: [] for key in DOMAINS}
    for test in tests:
        grouped[classify(test.name)].append(test)
    for key, (class_name, path) in DOMAINS.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        (path.parent / "__init__.py").touch()
        body = [
            "from agents._tests.support.workspace_environment import *  # noqa: F401,F403\n\n\n",
            f"class {class_name}(unittest.IsolatedAsyncioTestCase):\n",
        ]
        for node in grouped[key]:
            body.append(indent_segment(source_segment(lines, node)))
            body.append("\n")
        path.write_text("".join(body), encoding="utf-8")

    inventory = {
        "schema_version": 1,
        "source": "agents/_tests/test_workspace.py",
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "test_count": len(tests),
        "tests": [test.name for test in tests],
        "routing": {test.name: classify(test.name) for test in tests},
    }
    INVENTORY.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print_plan(grouped)


def discovered_tests():
    found = {}
    for domain, (_, path) in DOMAINS.items():
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("test_")
            ):
                found.setdefault(node.name, []).append(domain)
    return found


def check_split():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    expected = set(inventory["tests"])
    found = discovered_tests()
    actual = set(found)
    duplicates = {name: domains for name, domains in found.items() if len(domains) != 1}
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    wrong_routes = {
        name: domains[0]
        for name, domains in found.items()
        if name in inventory["routing"]
        and domains[0] != inventory["routing"][name]
    }
    if duplicates or missing or unexpected or wrong_routes:
        raise SystemExit(json.dumps({
            "duplicates": duplicates,
            "missing": missing,
            "unexpected": unexpected,
            "wrong_routes": wrong_routes,
        }, indent=2))
    if LEGACY.exists():
        raise SystemExit("legacy agents/_tests/test_workspace.py must be deleted")
    print(f"Workspace test split passed: {len(actual)} tests mapped exactly once.")


def print_plan(grouped=None):
    if grouped is None:
        _, _, _, tests = legacy_parts()
        grouped = {key: [] for key in DOMAINS}
        for test in tests:
            grouped[classify(test.name)].append(test)
    for key, tests in grouped.items():
        line_count = sum(node.end_lineno - node.lineno + 1 for node in tests)
        print(f"{key}: {len(tests)} tests, about {line_count} method lines")


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.plan:
        print_plan()
    elif args.write:
        write_split()
    else:
        check_split()


if __name__ == "__main__":
    main()
