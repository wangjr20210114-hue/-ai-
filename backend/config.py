"""应用配置：读取 .env 环境变量。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ===== LLM 提供方选择：hunyuan | deepseek =====
    llm_provider: str = "hunyuan"

    # 混元 API（问答 — LKEAP 平台）
    hunyuan_api_key: str = "sk-your-hunyuan-api-key"
    hunyuan_base_url: str = "https://api.lkeap.cloud.tencent.com/plan/v3"
    hunyuan_model: str = "hy3"

    # 混元生图 API（TokenHub 平台，独立的 key 和 URL）
    hunyuan_image_api_key: str = ""
    hunyuan_image_base_url: str = "https://tokenhub.tencentmaas.com"
    hunyuan_image_model: str = "hy-image-lite"

    # 混元视觉理解模型（多模态，用于图片描述 → 图文交错）
    # 使用 LKEAP 同一 key/base_url，模型名 hunyuan-vision
    hunyuan_vision_model: str = "hunyuan-vision"

    # DeepSeek API（意图推断 + 搜索总结）
    deepseek_api_key: str = "sk-your-deepseek-api-key"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # WSA 联网搜索 API
    wsa_api_key: str = ""
    wsa_base_url: str = "https://api.wsa.cloud.tencent.com"

    # 腾讯位置服务 API
    tencent_map_key: str = ""

    # 应用
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    db_path: str = "./yuanbao.db"
    mock_mode: bool = False

    @property
    def hunyuan_ready(self) -> bool:
        return bool(self.hunyuan_api_key) and not self.hunyuan_api_key.startswith(
            "sk-your"
        )

    @property
    def use_deepseek(self) -> bool:
        return self.llm_provider.lower() == "deepseek"

    @property
    def deepseek_ready(self) -> bool:
        return bool(self.deepseek_api_key) and not self.deepseek_api_key.startswith(
            "sk-your"
        )

    @property
    def llm_ready(self) -> bool:
        if self.use_deepseek:
            return self.deepseek_ready
        return self.hunyuan_ready

    @property
    def llm_api_key(self) -> str:
        return self.deepseek_api_key if self.use_deepseek else self.hunyuan_api_key

    @property
    def llm_base_url(self) -> str:
        return self.deepseek_base_url if self.use_deepseek else self.hunyuan_base_url

    @property
    def llm_model(self) -> str:
        return self.deepseek_model if self.use_deepseek else self.hunyuan_model

    @property
    def image_capable(self) -> bool:
        """是否支持文生图。"""
        return bool(self.hunyuan_image_api_key)

    @property
    def llm_price_per_1k(self) -> float:
        return 0.002 if self.use_deepseek else 0.015


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
