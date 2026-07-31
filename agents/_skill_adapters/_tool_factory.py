"""Shared StructuredTool construction for trusted system Skill adapters."""

from __future__ import annotations

from typing import Any, Mapping

from langchain_core.tools import StructuredTool


def build_service_tools(
    context,
    service_name: str,
    descriptions: Mapping[str, str],
    *,
    schemas: Mapping[str, Any] | None = None,
):
    service = context.service(service_name)
    schema_by_name = schemas or {}
    return tuple(
        StructuredTool.from_function(
            coroutine=service.operation(name),
            name=name,
            description=description,
            **(
                {"args_schema": schema_by_name[name]}
                if name in schema_by_name
                else {}
            ),
        )
        for name, description in descriptions.items()
    )

