from .._tool_factory import build_service_tools


def build_tools(context):
    return build_service_tools(
        context,
        "meeting",
        {
            "propose_meeting": (
                "Prepare an editable Tencent Meeting confirmation card; missing "
                "fields remain editable and no meeting is created before confirmation."
            ),
        },
    )

