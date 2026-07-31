from .._tool_factory import build_service_tools


def build_tools(context):
    return build_service_tools(
        context,
        "vision",
        {
            "analyze_images_parallel": (
                "Review up to 30 image candidates independently and return only "
                "evidence suitable for deterministic source binding."
            ),
        },
    )

