"""Topics are data: one YAML file per ad-hoc topic in topics/."""

from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator


class Topic(BaseModel):
    name: str
    definition: str
    include: list[str] = []
    exclude: list[str] = []
    keywords: dict[str, list[str]] = {}

    @field_validator("include", "exclude", mode="before")
    @classmethod
    def _as_list(cls, value: str | list[str] | None) -> list[str]:
        items = [value] if isinstance(value, str) else (value or [])
        return [item.strip() for item in items if item and item.strip()]


def load_topic(path: Path) -> Topic:
    return Topic(**yaml.safe_load(Path(path).read_text()))
