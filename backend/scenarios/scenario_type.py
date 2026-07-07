"""场景类型枚举。"""
from enum import Enum


class ScenarioType(str, Enum):
    TRAVEL = "travel"
    MEETING = "meeting"
    NEWS = "news"
    IMAGE = "image"
    TRANSLATION = "translation"
    PAPER = "paper"
    CHAT = "chat"


SCENARIO_LABELS: dict[ScenarioType, str] = {
    ScenarioType.TRAVEL: "旅游规划",
    ScenarioType.MEETING: "腾讯会议",
    ScenarioType.NEWS: "新闻搜索",
    ScenarioType.IMAGE: "AI 生图",
    ScenarioType.TRANSLATION: "翻译",
    ScenarioType.PAPER: "论文助读",
    ScenarioType.CHAT: "通用对话",
}
