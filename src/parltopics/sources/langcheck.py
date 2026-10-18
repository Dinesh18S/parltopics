"""Cheap, deterministic language check by stopword counts."""

import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

MIN_HITS = 5
MIN_SHARE = 0.5


@lru_cache
def _stopwords() -> dict[str, frozenset[str]]:
    raw = json.loads((Path(__file__).parent.parent / "data" / "stopwords.json").read_text())
    return {lang: frozenset(words) for lang, words in raw.items()}


def detect_lang(text: str) -> str | None:
    """Most likely language code, or None if the text gives too little signal."""
    scores: Counter[str] = Counter()
    for token in re.findall(r"\w+", text.lower()):
        for lang, words in _stopwords().items():
            if token in words:
                scores[lang] += 1
    if not scores:
        return None
    (best, hits), total = scores.most_common(1)[0], sum(scores.values())
    if hits < MIN_HITS or hits / total < MIN_SHARE:
        return None
    return best
