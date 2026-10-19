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
    llm_max_tokens_standard: int = 900  # up to 3 labels with evidence + rationale (400 truncated JSON, D62)
    llm_concurrency: int = 4
    llm_json_mode: str = "json_schema"
    max_input_chars: int = 12000
    title_only_conf_cap: float = 0.6
    match_threshold: float = 0.9  # D45: fixed on dev by the pre-registered rule
    demo_default_preset: str = ""
    translate_model: str = ""  # model for the unofficial reading-aid translation; empty = LLM_NAME
    review_lang: str = ""
    scheme_label_fallback: str = ""  # label language when a scheme has none in the affair language (APS has no IT)  # reader language for review aids (official version / unofficial translation); empty = off  # topics/<id>.yaml shown first in the UI; empty = first preset with results
    collection_exclude_types: list[str] = ["Consultation"]  # not parliamentary affairs; as the federal baseline (D67)
    translated_lang_order: list[str] = ["de", "fr", "it"]  # federal collections: first complete official version (D67)
    endpoint_label: str = ""  # shown in the UI next to the model, e.g. "CSCS"; empty = the endpoint's host name
    opd_api_base: str = "https://api.openparldata.ch"
    data_dir: Path = Path("./data")
    db_path: Path = Path("./data/parltopics.db")
    bulk_db_path: Path = Path("./data/cache/bulk.db")


@lru_cache
def get_settings() -> Settings:
    return Settings()
