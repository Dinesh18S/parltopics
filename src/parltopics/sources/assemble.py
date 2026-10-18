"""Build the exact text the model sees for one affair."""

import hashlib
import re
from collections import Counter
from html import unescape
from html.parser import HTMLParser

from pydantic import BaseModel

from parltopics.sources.api import Affair, Doc
from parltopics.sources.langcheck import detect_lang

# Bodies whose affairs exist as official translations; the caller must pick the language.
TRANSLATED_BODY_TYPES = {"country"}

# Federal text types (type.de in OpenParlData / che_affair_texts) → header, in reading order.
TEXT_SECTIONS = {
    "Eingereichter Text": "TEXT",
    "Begründung": "REASONING",
    "Antwort BR / Büro": "ANSWER",
}
SKIPPED_TEXT_TYPES = {"Titel des Geschäftes"}


class LangMissing(ValueError):
    """The affair has no (complete) text in the chosen language. Recorded as status=lang_missing."""


class SourceText(BaseModel):
    affair_id: int
    lang: str
    lang_source: str
    detected_lang: str | None
    lang_mismatch: bool
    text: str
    sha256: str
    sections: list[str]
    title_only: bool
    truncated: bool
    cut_section: str | None
    chars_lost: int
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


def _doc_lang(doc: Doc) -> str | None:
    return detect_lang(doc.text or "") or doc.language


def choose_lang(affair: Affair, requested: str | None) -> tuple[str, str]:
    """Language to assemble in, and where that choice came from: requested | body | detected."""
    if affair.body.type in TRANSLATED_BODY_TYPES:
        if not requested:
            raise ValueError(f"affair {affair.id} ({affair.body.key}) is translated: pass a language")
        return requested, "requested"
    if requested:
        raise ValueError(
            f"affair {affair.id} ({affair.body.key}): language comes from the parliament, not the request"
        )
    languages = affair.body.languages
    if len(languages) == 1:
        return languages[0], "body"
    chars: Counter[str] = Counter()
    for doc in affair.docs:
        lang = _doc_lang(doc)
        if doc.text and lang in languages:
            chars[lang] += len(doc.text)
    if chars:
        return chars.most_common(1)[0][0], "detected"
    if affair.body.primary:
        return affair.body.primary, "body"
    raise LangMissing(f"affair {affair.id}: cannot determine language of {affair.body.key}")


def _check_complete(affair: Affair, lang: str) -> None:
    """Translated affairs: every part that exists in some language must exist in `lang`."""
    missing = [] if lang in affair.title else ["title"]
    for part in affair.texts:
        kind = part.type.get("de") or "untyped"
        has_any = any(v and clean_text(v) for v in part.text.values())
        if has_any and not clean_text(part.text.get(lang) or ""):
            missing.append(kind)
    if missing:
        raise LangMissing(f"affair {affair.id}: no '{lang}' version of {', '.join(missing)}")


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

    if affair.body.type in TRANSLATED_BODY_TYPES:
        return sections
    docs = [d for d in affair.docs if d.text and _doc_lang(d) == lang]
    seen: set[str] = set()
    for doc in sorted(docs, key=lambda d: (d.date or "9999", d.id)):
        body = clean_text(doc.text or "")
        if body and body not in seen:
            seen.add(body)
            sections.append((f"DOCUMENT ({doc.name or doc.id})", body))
    return sections


def _cut(sections: list[tuple[str, str]], full: str, max_chars: int) -> str | None:
    if len(full) <= max_chars:
        return None
    pos = 0
    for header, body in sections:
        pos += len(header) + 2 + len(body)
        if pos > max_chars:
            return header
        pos += 2
    return None


def assemble(affair: Affair, max_chars: int, lang: str | None = None) -> SourceText:
    lang, lang_source = choose_lang(affair, lang)
    if lang_source == "requested":
        _check_complete(affair, lang)
    sections = _sections(affair, lang)
    if not sections:
        raise LangMissing(f"affair {affair.id} has no title or text in '{lang}'")
    full = "\n\n".join(f"{header}: {body}" for header, body in sections)
    text = full[:max_chars]
    detected = detect_lang(" ".join(body for _, body in sections))
    url = affair.url_external.get(lang) or next(iter(affair.url_external.values()), affair.url_api)
    return SourceText(
        affair_id=affair.id,
        lang=lang,
        lang_source=lang_source,
        detected_lang=detected,
        lang_mismatch=detected is not None and detected != lang,
        text=text,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        sections=[header for header, _ in sections],
        title_only=[header for header, _ in sections] == ["TITLE"],
        truncated=len(full) > max_chars,
        cut_section=_cut(sections, full, max_chars),
        chars_lost=max(0, len(full) - max_chars),
        n_chars_full=len(full),
        url=url,
    )
