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



def _pattern(word: str) -> str:
    """`word*` = any word starting with `word`; a plain word or phrase must match as whole word(s)."""
    word = word.strip()
    if word.endswith("*"):
        return r"\b" + re.escape(word.rstrip("*"))
    return r"\b" + r"\s+".join(re.escape(w) for w in word.split()) + r"\b"


def _absent(text: str, keywords: dict[str, list[str]]) -> bool | None:
    """True if no keyword (any language) occurs in the text; None if the topic has no keywords at all."""
    words = [w for ws in keywords.values() for w in ws if w.strip().rstrip("*")]
    if not words:
        return None
    pattern = "|".join(_pattern(w) for w in words)
    return re.search(pattern, text, flags=re.IGNORECASE) is None


def keyword_absent(text: str, topic: Topic) -> bool | None:
    """None of the topic's core keywords appears (the pitch claim). None if the topic has no keywords."""
    return _absent(text, topic.keywords)


def tech_vocab_absent(text: str, topic: Topic) -> bool | None:
    """None of the core or broad keywords appears (stricter badge). None if the topic has no keywords."""
    if not topic.keywords:
        return None
    merged = {lang: topic.keywords.get(lang, []) + topic.keywords_broad.get(lang, [])
              for lang in set(topic.keywords) | set(topic.keywords_broad)}
    return _absent(text, merged)
