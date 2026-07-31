from .._tool_factory import build_service_tools


def build_tools(context):
    return build_service_tools(
        context,
        "core",
        {
            "ask_user_clarification": (
                "所有问答场景统一的必要信息收集入口。只有缺少该字段会阻断所有安全有用的回答，"
                "或无法唯一确定真实副作用对象时才能调用；可选偏好不得调用，应直接给出 "
                "2–3 套带假设与取舍的方案。本轮最多调用一次并只收最少必要字段；卡片提交后自动继续推理，"
                "不要要求用户再次发送，也不要重复询问已提交字段。"
            ),
        },
    )
