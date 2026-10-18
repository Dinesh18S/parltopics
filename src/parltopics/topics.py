"""Topics are data: one YAML file per ad-hoc topic in topics/."""

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator


class Topic(BaseModel):
    name: str
    definition: str
    include: list[str] = []
    exclude: list[str] = []
    keywords: dict[str, list[str]] = {}
    keywords_broad: dict[str, list[str]] = {}

    @field_validator("include", "exclude", mode="before")
    @classmethod
    def _as_list(cls, value: str | list[str] | None) -> list[str]:
        items = [value] if isinstance(value, str) else (value or [])
        return [item.strip() for item in items if item and item.strip()]


def load_topic(path: Path) -> Topic:
    return Topic(**yaml.safe_load(Path(path).read_text()))



def _absent(text: str, keywords: dict[str, list[str]]) -> bool:
    """True if no keyword (any language) starts a word in the text; `*` marks a prefix, all match at word start."""
    words = [w.strip().rstrip("*") for ws in keywords.values() for w in ws if w.strip().rstrip("*")]
    if not words:
        return True
    pattern = r"\b(?:" + "|".join(re.escape(w) for w in words) + ")"
    return re.search(pattern, text, flags=re.IGNORECASE) is None


def keyword_absent(text: str, topic: Topic) -> bool:
    """None of the topic's core keywords appears (the pitch claim)."""
    return _absent(text, topic.keywords)


def tech_vocab_absent(text: str, topic: Topic) -> bool:
    """None of the core or broad keywords appears (stricter badge)."""
    merged = {lang: topic.keywords.get(lang, []) + topic.keywords_broad.get(lang, [])
              for lang in set(topic.keywords) | set(topic.keywords_broad)}
    return _absent(text, merged)
