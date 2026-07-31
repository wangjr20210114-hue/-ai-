from .._tool_factory import build_service_tools


def build_tools(context):
    return build_service_tools(
        context,
        "papers",
        {
            "search_arxiv": (
                "Find verifiable academic papers using exact arXiv identities, author "
                "and institution evidence, and explicit year constraints."
            ),
        },
    )

