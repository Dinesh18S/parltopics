"""Fixed classification schemes are data: Curia Vista areas and APS chapters/topics loaded from the challenge files."""

from pathlib import Path

import openpyxl
import pandas as pd
from pydantic import BaseModel


class Category(BaseModel):
    code: str  # short local id shown to the model (CV01, C01, T001 …)
    source_id: str  # id in the source scheme (Curia Vista topic id, APS code)
    labels: dict[str, str]  # language → label


class Scheme(BaseModel):
    name: str
    definition: str
    kind: str
    categories: list[Category]

    def label(self, category: Category, lang: str, fallback: str = "") -> str:
        return category.labels.get(lang) or category.labels.get(fallback) or next(iter(category.labels.values()))

    def by_code(self) -> dict[str, Category]:
        return {c.code: c for c in self.categories}


def _labels(row: dict, prefix: str, id_column: str = "") -> dict[str, str]:
    return {k[len(prefix):]: str(v).strip() for k, v in row.items()
            if k.startswith(prefix) and k != id_column and v and str(v).strip()}


def load_curia_vista(raw_dir: Path) -> Scheme:
    vocab = pd.read_csv(raw_dir / "che_topics_vocabulary.csv", dtype=str, keep_default_na=False)
    cats = [Category(code=f"CV{i:02d}", source_id=r["topic_id"], labels=_labels(r, "topic_", "topic_id"))
            for i, r in enumerate(vocab.to_dict("records"), start=1)]
    return Scheme(name="Curia Vista subject areas", kind="curia_vista", categories=cats,
                  definition="The federal parliament's 28 subject areas (Sachbereiche) used in Curia Vista.")


def _aps_rows(raw_dir: Path, sheet: str) -> list[dict]:
    ws = openpyxl.load_workbook(raw_dir / "aps_topics.xlsx", read_only=True)[sheet]
    rows = list(ws.iter_rows(values_only=True))
    header = [str(h) for h in rows[0]]
    return [dict(zip(header, r)) for r in rows[1:] if r[0]]


def load_aps_chapters(raw_dir: Path) -> Scheme:
    cats = [Category(code=f"C{i:02d}", source_id=str(r["code"]), labels=_labels(r, "chapter_"))
            for i, r in enumerate(_aps_rows(raw_dir, "Chapters"), start=1)]
    return Scheme(name="APS chapters", kind="aps_chapter", categories=cats,
                  definition="Année Politique Suisse thematic scheme, chapter level (22 chapters).")


def load_aps_topics(raw_dir: Path, chapter_ids: list[str] | None = None) -> Scheme:
    rows = [r for r in _aps_rows(raw_dir, "Topics")
            if chapter_ids is None or str(r["code"]).rsplit(".", 1)[0] in chapter_ids]
    cats = [Category(code=f"T{i:03d}", source_id=str(r["code"]), labels=_labels(r, "topic_")) for i, r in enumerate(rows, 1)]
    return Scheme(name="APS topics", kind="aps_topic", categories=cats,
                  definition="Année Politique Suisse thematic scheme, topic level (within the chosen chapters).")
