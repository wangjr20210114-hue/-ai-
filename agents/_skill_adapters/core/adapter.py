from .._tool_factory import build_service_tools
from ..._application.i18n import text


def build_tools(context):
    return build_service_tools(
        context,
        "core",
        {
            "ask_user_clarification": text(
                "model.tool.ask_user_clarification.description",
                context.response_language,
            ),
        },
    )
