from .._tool_factory import build_service_tools


def build_tools(context):
    return build_service_tools(
        context,
        "search",
        {
            "rich_search": (
                "Search current external evidence once and return citable sources."
            ),
            "collect_page_images": (
                "Collect public image candidates from one supplied source page."
            ),
        },
    )

