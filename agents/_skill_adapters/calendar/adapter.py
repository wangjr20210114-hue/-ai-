from .._tool_factory import build_service_tools


def build_tools(context):
    return build_service_tools(
        context,
        "calendar",
        {
            "propose_calendar_changes": (
                "Prepare versioned create, update, or delete calendar changes and "
                "conflict warnings; never write before user confirmation."
            ),
        },
    )

