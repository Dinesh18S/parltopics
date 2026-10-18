from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_name: str = "apertus-v1-5-70b"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_temperature: float = 0.0
    llm_max_tokens: int = 400
    llm_concurrency: int = 4
    llm_json_mode: str = "json_schema"
    max_input_chars: int = 12000
    title_only_conf_cap: float = 0.6
    opd_api_base: str = "https://api.openparldata.ch"
    data_dir: Path = Path("./data")


@lru_cache
def get_settings() -> Settings:
    return Settings()
