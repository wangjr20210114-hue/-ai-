"""Shared StructuredTool construction for trusted system Skill adapters."""

from __future__ import annotations

from typing import Any, Mapping

from langchain_core.tools import StructuredTool

from ._component_output import bind_component_publications


def build_service_tools(
    context,
    service_name: str,
    descriptions: Mapping[str, str],
    *,
    schemas: Mapping[str, Any] | None = None,
):
    service = context.service(service_name)
    schema_by_name = schemas or {}

    def operation_for(name: str):
        operation = service.operation(name)
        publications = context.component_actions_for_tool(name)
        return (
            bind_component_publications(
                context,
                operation,
                publications,
                publication_key=name,
            )
            if publications
            else operation
        )

    return tuple(
        StructuredTool.from_function(
            coroutine=operation_for(name),
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
