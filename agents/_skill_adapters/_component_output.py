"""Project trusted tool results into versioned host Component API calls."""

from __future__ import annotations

import inspect
import json
from collections import defaultdict
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping


def _decoded(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, Mapping) else None


def _workspace_action(value: Mapping[str, Any]) -> Mapping[str, Any] | None:
    action = value.get("action")
    return action if isinstance(action, Mapping) else None


def component_payloads(
    action: str,
    result: Any,
) -> tuple[dict[str, Any], ...]:
    """Return only payloads whose required fields exist in trusted output."""
    value = _decoded(result)
    if value is None:
        return ()

    if action == "clarification.request":
        clarification = value.get("clarification")
        return (
            ({"clarification": deepcopy(dict(clarification))},)
            if isinstance(clarification, Mapping)
            else ()
        )

    if action == "search.evidence.publish":
        metadata = value.get("search_results")
        if not isinstance(metadata, Mapping):
            return ()
        sources = metadata.get("results") or metadata.get("sources") or ()
        return tuple(
            {
                "source_id": str(source.get("id") or source.get("source_id") or ""),
                "title": str(source.get("title") or ""),
                "url": str(source.get("url") or ""),
            }
            for source in sources
            if isinstance(source, Mapping)
            and str(source.get("id") or source.get("source_id") or "").strip()
            and str(source.get("title") or "").strip()
            and str(source.get("url") or "").strip()
        )

    if action == "search.media.publish":
        metadata = value.get("search_results")
        if not isinstance(metadata, Mapping):
            return ()
        sources = metadata.get("results") or metadata.get("sources") or ()
        source_ids = {
            str(source.get("id") or source.get("source_id") or "").strip()
            for source in sources
            if isinstance(source, Mapping)
            and str(source.get("id") or source.get("source_id") or "").strip()
        }
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in metadata.get("media") or ():
            if not isinstance(item, Mapping):
                continue
            source_id = str(item.get("source_id") or "").strip()
            if source_id in source_ids:
                grouped[source_id].append(deepcopy(dict(item)))
        return tuple(
            {"source_id": source_id, "media": media}
            for source_id, media in grouped.items()
        )

    if action == "maps.place.select":
        if value.get("ui_action") != "map_action":
            return ()
        workspace_action = _workspace_action(value)
        payload = (
            workspace_action.get("payload")
            if isinstance(workspace_action, Mapping)
            else None
        )
        places = payload.get("places") if isinstance(payload, Mapping) else None
        if not isinstance(places, list):
            return ()
        publication: dict[str, Any] = {"places": deepcopy(places)}
        route = value.get("route")
        if isinstance(route, Mapping):
            publication["route"] = deepcopy(dict(route))
        return (publication,)

    if action == "calendar.change.propose":
        if value.get("ui_action") != "calendar_action":
            return ()
        workspace_action = _workspace_action(value)
        payload = (
            workspace_action.get("payload")
            if isinstance(workspace_action, Mapping)
            else None
        )
        changes = payload.get("changes") if isinstance(payload, Mapping) else None
        if not isinstance(changes, list):
            return ()
        return ({
            "changes": deepcopy(changes),
            "warnings": deepcopy(payload.get("warnings") or []),
        },)

    if action == "paper.results.publish":
        papers = value.get("papers")
        if value.get("ui_action") != "paper_results" or not isinstance(papers, list):
            return ()
        return ({
            "papers": deepcopy(papers),
            "topic": str(value.get("topic") or ""),
        },)

    if action == "image.result.publish":
        workspace_action = _workspace_action(value)
        if (
            value.get("ui_action") != "side_effect_action"
            or not isinstance(workspace_action, Mapping)
            or workspace_action.get("kind") != "image_generate"
        ):
            return ()
        result_value = workspace_action.get("result")
        if not isinstance(result_value, Mapping):
            return ()
        storage_key = str(result_value.get("storage_key") or "").strip()
        versions = result_value.get("versions")
        if not storage_key or not isinstance(versions, list):
            return ()
        return ({
            "storage_key": storage_key,
            "versions": deepcopy(versions),
        },)

    if action == "workspace.action.propose":
        workspace_action = _workspace_action(value)
        if not isinstance(workspace_action, Mapping):
            return ()
        kind = str(workspace_action.get("kind") or "").strip()
        payload = workspace_action.get("payload")
        if not kind or not isinstance(payload, Mapping):
            return ()
        return ({"kind": kind, "payload": deepcopy(dict(payload))},)

    return ()


def bind_component_publications(
    context,
    operation,
    actions: tuple[str, ...],
    *,
    publication_key: str,
):
    """Wrap one operation without changing its model-visible return value."""
    dispatchers = tuple(
        (
            action,
            context.component(action, publication_key=publication_key),
        )
        for action in actions
    )

    @wraps(operation)
    async def invoke(*args, **kwargs):
        result = operation(*args, **kwargs)
        if inspect.isawaitable(result):
            result = await result
        for action, dispatch in dispatchers:
            for payload in component_payloads(action, result):
                published = dispatch(payload)
                if inspect.isawaitable(published):
                    await published
        return result

    return invoke


__all__ = ("bind_component_publications", "component_payloads")
