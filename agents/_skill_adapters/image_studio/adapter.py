from .._tool_factory import build_service_tools


def build_tools(context):
    return build_service_tools(
        context,
        "image",
        {
            "propose_image": (
                "Generate or edit an image immediately; reviewed real-world "
                "references may be supplied, with at most three reference URLs."
            ),
        },
    )

