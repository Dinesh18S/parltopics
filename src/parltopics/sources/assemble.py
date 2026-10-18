"""Build the exact text the model sees for one affair."""

import hashlib
import re
from collections import Counter
from html import unescape
from html.parser import HTMLParser

from pydantic import BaseModel

from parltopics.sources.api import Affair

LANG_ORDER = ("de", "fr", "it", "rm")

# Federal text types (type.de in OpenParlData / che_affair_texts) → header, in reading order.
TEXT_SECTIONS = {
    "Eingereichter Text": "TEXT",
    "Begründung": "REASONING",
    "Antwort BR / Büro": "ANSWER",
}
SKIPPED_TEXT_TYPES = {"Titel des Geschäftes"}


class SourceText(BaseModel):
    affair_id: int
    lang: str
    lang_source: str
    text: str
    sha256: str
    sections: list[str]
    title_only: bool
    truncated: bool
    n_chars_full: int
    url: str


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"p", "br", "div", "li", "tr"}:
            self.parts.append(" ")


def clean_text(raw: str) -> str:
    """Strip HTML tags, unescape entities, collapse whitespace."""
    if "<" in raw:
        parser = _TextExtractor()
        parser.feed(raw)
        parser.close()
        raw = "".join(parser.parts)
    return re.sub(r"\s+", " ", unescape(raw)).strip()


def choose_lang(affair: Affair, requested: str | None) -> tuple[str, str]:
    """Language to assemble in, and where that choice came from."""
    if requested:
        return requested, "requested"
    if len(affair.title) == 1:
        return next(iter(affair.title)), "title_single"
    candidates = [lang for lang in LANG_ORDER if lang in affair.title]
    if not candidates:
        raise ValueError(f"affair {affair.id} has no title in any language")
    votes = Counter(d.language for d in affair.docs if d.text and d.language in candidates)
    if votes:
        top = max(votes.values())
        leaders = [lang for lang in candidates if votes[lang] == top]
        if len(leaders) == 1:
            return leaders[0], "doc_majority"
        return leaders[0], "default_order"
    return candidates[0], "default_order"


def _sections(affair: Affair, lang: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    if lang in affair.title:
        sections.append(("TITLE", clean_text(affair.title[lang])))

    known: list[tuple[int, str, str]] = []
    other: list[tuple[str, str]] = []
    for part in sorted(affair.texts, key=lambda t: t.id):
        kind = part.type.get("de") or ""
        body = part.text.get(lang)
        if kind in SKIPPED_TEXT_TYPES or not body or not clean_text(body):
            continue
        if kind in TEXT_SECTIONS:
            known.append((list(TEXT_SECTIONS).index(kind), TEXT_SECTIONS[kind], clean_text(body)))
        else:
            other.append((f"OTHER ({part.type.get(lang) or kind or 'untyped'})", clean_text(body)))
    sections += [(header, body) for _, header, body in sorted(known)] + other

    docs = [d for d in affair.docs if d.text and d.language in (lang, None)]
    seen: set[str] = set()
    for doc in sorted(docs, key=lambda d: (d.date or "9999", d.id)):
        body = clean_text(doc.text or "")
        if body and body not in seen:
            seen.add(body)
            sections.append((f"DOCUMENT ({doc.name or doc.id})", body))
    return sections


def assemble(affair: Affair, max_chars: int, lang: str | None = None) -> SourceText:
    lang, lang_source = choose_lang(affair, lang)
    sections = _sections(affair, lang)
    if not sections:
        raise ValueError(f"affair {affair.id} has no title or text in '{lang}'")
    full = "\n\n".join(f"{header}: {body}" for header, body in sections)
    text = full[:max_chars]
    url = affair.url_external.get(lang) or next(iter(affair.url_external.values()), affair.url_api)
    return SourceText(
        affair_id=affair.id,
        lang=lang,
        lang_source=lang_source,
        text=text,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        sections=[header for header, _ in sections],
        title_only=[header for header, _ in sections] == ["TITLE"],
        truncated=len(full) > max_chars,
        n_chars_full=len(full),
        url=url,
    )
