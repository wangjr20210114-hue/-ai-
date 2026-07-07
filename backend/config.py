"""应用配置：读取 .env 环境变量。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ===== LLM 提供方选择：hunyuan | deepseek =====
    llm_provider: str = "deepseek"

    # 混元 API
    hunyuan_api_key: str = "sk-your-hunyuan-api-key"
    hunyuan_base_url: str = "https://api.hunyuan.cloud.tencent.com/v1"
    hunyuan_model: str = "hunyuan-turbo"

    # DeepSeek API（OpenAI 兼容接口）
    deepseek_api_key: str = "sk-your-deepseek-api-key"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # 腾讯位置服务 API
    tencent_map_key: str = "REMOVED_TENCENT_MAP_KEY"

    # 应用
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    db_path: str = "./yuanbao.db"

    @property
    def hunyuan_ready(self) -> bool:
        return bool(self.hunyuan_api_key) and not self.hunyuan_api_key.startswith(
            "sk-your"
        )

    @property
    def use_deepseek(self) -> bool:
        return self.llm_provider.lower() == "deepseek"

    @property
    def llm_ready(self) -> bool:
        if self.use_deepseek:
            return bool(self.deepseek_api_key) and not self.deepseek_api_key.startswith(
                "sk-your"
            )
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
    def llm_price_per_1k(self) -> float:
        return 0.002 if self.use_deepseek else 0.015


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
