"""Topics are data: one YAML file per ad-hoc topic in topics/."""

from pathlib import Path

import yaml
from pydantic import BaseModel


class Topic(BaseModel):
    name: str
    definition: str
    include: str = ""
    exclude: str = ""
    keywords: dict[str, list[str]] = {}


def load_topic(path: Path) -> Topic:
    return Topic(**yaml.safe_load(Path(path).read_text()))
