# 03 — Data & API Notes

All sources are public and need no key. Data licence: OpenParlData publishes under **CC BY 4.0** — attribute as "Source: OpenParlData.ch" in the README, UI footer and report.

> Items marked **VERIFY** were assumptions; all were checked against real responses in S1 (2026-10-18) and are now ticked with the finding.

## 1. OpenParlData REST API

- Base: `https://api.openparldata.ch` · Swagger: `/documentation` · ReDoc: `/redoc` · OpenAPI: `/openapi.json`
- Version prefix: `/v1/`

### Endpoints we use

| Purpose | Call |
|---|---|
| One affair | `GET /v1/affairs/{id}` |
| Affair with related docs/texts | `GET /v1/affairs/{id}?expand=docs` (or `expand=*` to discover relations) |
| List / filter affairs | `GET /v1/affairs/?body_key=CHE&sort_by=-begin_date&limit=100&offset=0` |
| Keyword search (baseline comparisons only) | `GET /v1/affairs/?search=Digitalisierung&search_mode=natural&search_language=de&search_scope=metadata,docs` |
| Parliaments | `GET /v1/bodies/?indexed=true&fields=body_key,…` |
| Health | `GET /health` |

### Useful parameters

- `lang=de|fr|it|rm|en`, `lang_fallback=de`, `lang_format=nested|flat` (nested is default: multilingual fields come as objects)
- `fields=a,b,c` (dot notation for relations), `hide_null=true`, `exclude_null=begin_date`
- Pagination: `offset`, `limit` (relations: default 100, max 1000). **`offset` is capped at 100,000** → HTTP 400. For full-table work use bulk exports.
- Filtering: any filterable field as a query param, comma-separated values allowed (`body_key=AI,AR`).
- Search scopes: `metadata`, `docs`, `texts`, `speeches`, `all`.

### VERIFY on first call

- [x] The `openparldata_id` in the PolitMonitor CSV equals the `id` in `/v1/affairs/{id}` — **yes**: body_key + number match the API for 142/142 sampled affairs (100 random PolitMonitor rows seed 42, all 12 municipal rows, 30 city-of-Zug affairs). All 1,448 CHE rows are also in `che_affairs_keywords.csv` with the same number.
- [x] Which relation holds the full affair text — **both, by level**. Federal: `/v1/affairs/{id}/texts`, each row has `type` and `text` as `{de,fr,it}` objects (HTML inside); same rows/ids as `che_affair_texts.ndjson.gz`. Cantonal/municipal: `/texts` is empty; content is PDF-extracted text in `/v1/affairs/{id}/docs`, field `text` (plain text, can be 100k+ chars), plus `name`, `date`, `language` (often null), `url`. Some docs have `text: null`.
- [x] Field names: `title` `{lang: str}` (only the languages that exist; cantonal usually one key), `type_harmonized.en` (null for some, e.g. GE), `begin_date` (`YYYY-MM-DDT00:00:00`), `body_key`, `number`, `url_external` `{lang: url}`, `url_api`. There is **no affair-level language field**; language comes from the title keys.
- [x] Source link: `url_external[lang]` (the parliament's own page, e.g. Curia Vista `geschaeft?AffairId=…`), falling back to any `url_external`, then `url_api`.
- [x] Title-only is rare in our pools: 3/100 random PolitMonitor affairs (1 CHE, 2 cantonal), 0/12 PolitMonitor municipal, 0/30 city of Zug. Long texts are common instead: 27/100 PolitMonitor affairs exceed `MAX_INPUT_CHARS`=12,000 after removing duplicate docs (median ~6,200 chars; city of Zug 12/30 truncated). Some cantons (GR) return the same document twice; the assembler drops exact duplicates.
- [x] Rate limiting headers: **none** seen (only `x-cache`, `x-cache-key`). No 429s during ~450 requests at concurrency 4.

### Client rules

- Disk cache every response under `data/cache/api/{sha1(url)}.json`; never re-fetch a cached URL in the same run.
- Max 4 concurrent requests, exponential backoff on 429/5xx, 3 retries, 20 s timeout.
- Set a `User-Agent` naming the project and repo URL.

## 2. Bulk exports

- Index: `https://files.openparldata.ch/exports/` — one gzipped NDJSON per table.
- Use these instead of paging the API for anything > ~500 affairs (negatives sampling, full-slice baseline).

## 3. Challenge files — `files.openparldata.ch/hackapertus` (read its README first)

| File | Contents | Our use |
|---|---|---|
| `politmonitor_digitalisierung.csv` | 3,433 affairs, 35 parliaments, tagged Digitalisierung | Positive set, headline eval |
| `che_affairs_keywords` | 70,008 federal affairs, 28 Curia Vista areas, DE/FR/IT | Baseline + Curia Vista eval; negatives pool for CHE |
| `che_affair_texts.ndjson.gz` | 210,437 texts (submitted text, reasoning, Federal Council answer), DE/FR/IT | Text input for federal affairs; cross-language test |
| `cantonal_affairs_keywords` | 10,742 affairs SG, TG, ZG, ZH with own labels | Cross-level spot-check |
| `aps_topics.xlsx` | APS: 8 domains, 22 chapters, 165 topics, DE/FR | Standard-mode label set |

### `politmonitor_digitalisierung.csv` columns

`openparldata_id, body_key, number, begin_date, type_en, title_de, title_fr, title_it, url, politmonitor_scope, politmonitor_id, topic`

- `topic` is "Digitalisierung" on all 3,433 rows (verified). `openparldata_id` is unique. Every row has ≥1 title (1,377 have DE+FR+IT). `politmonitor_scope` is the lowercase canton code, `ch` for federal; 50 CHE rows have scope `chv` (to inspect in S4).
- `politmonitor_scope` defines which parliaments/periods PolitMonitor covers. **Negatives may only come from inside this scope.**
- Three title columns = free multilingual test for titles (texts for CHE come from `che_affair_texts`).

### `aps_topics.xlsx`

Sheets: `Topics`, `Chapters`, `Domains`. Columns: `code, domain_de, domain_fr, chapter_de, chapter_fr, topic_de, topic_fr, url_de`. `code` is a file-local join key; do not present it as an official APS id. No IT/EN labels exist.

### VERIFY

- [x] File names: both come as `.csv` and `.jsonl` (we use `.csv`), plus `*_keywords_long.csv` and vocabularies. `che_affairs_keywords.csv`: `openparldata_id, affair_external_id, number, type_en, type_de, begin_date, title_de, title_fr, title_it, url, topic_ids, topics_de, topics_fr, topics_it, descriptors_de` (multi-values joined by ` | `). `cantonal_affairs_keywords.csv`: `openparldata_id, body_key, body_name, keyword_kind, affair_external_id, number, type_en, type_de, begin_date, title_de, title_fr, url, keywords, keyword_codes`. Also `dvs_digitalisierung.csv` (30 DVS affairs).
- [x] Join key: `openparldata_id` everywhere (= API affair id). `affair_external_id` is the Curia Vista id.
- [x] Text file: one row per text with `text_de`, `text_fr`, `text_it` (null if missing) and `type_de/fr/it/en`; types: `Titel des Geschäftes`, `Eingereichter Text`, `Begründung`, `Antwort BR / Büro`, `Lead`, empty. HTML inside even when `format=text`.
- [x] Sizes: `che_affair_texts.ndjson.gz` 232 MB (715 MB unzipped), `che_affairs_keywords.csv` 35 MB, others ≤ 3.3 MB. All live in gitignored `data/raw/`; only `data/raw_files.sha256` is committed.

## 4. Local layout

```
data/
  raw/            # downloaded challenge files (gitignored)
  cache/api/      # API responses (gitignored)
  samples/        # committed: the exact affair IDs for every eval set + demo pool (small CSVs)
  gold/           # committed: partner's hand labels (APS gold, adjudications, CV↔APS mapping)
results/          # committed: metrics.json + per-run summaries (not raw outputs if large)
```

`make data` downloads `raw/` with checksums. The repo `data/` stays under the template's 100 MB limit; committed samples are IDs + labels only.

## 5. Datasets we build

| File | Built by | Contents |
|---|---|---|
| `samples/first_loop.csv` | Dinesh | 20 PolitMonitor positives (mixed DE/FR/IT, types) + 20 in-scope negatives |
| `samples/digi_federal_2018.csv` | Dinesh | Like-for-like sample: CHE, `begin_date ≥ 2018-01-01`, stratified pos/neg, with the population counts needed for prevalence correction |
| `samples/curia_vista.csv` | Dinesh | Stratified sample over the 28 areas |
| `samples/crosslang.csv` | Dinesh | Federal affairs with text in all of DE, FR, IT |
| `samples/demo_pool.csv` | Both | ~200 affairs for the live UI |
| `gold/aps_gold.csv` | Arivinchsa | ~50 affairs, APS chapter + topic |
| `gold/cv_aps_mapping.csv` | Arivinchsa | Curia Vista area → APS chapter(s) |
| `gold/adjudications.csv` | Arivinchsa | Disputed affair id, model label, PolitMonitor label, adjudicated label, note |
| `gold/digitalisation_definition.md` | Arivinchsa | One-page definition + borderline rules (feeds the prompt) |

## 6. Text assembly per affair

Order: title → submitted text → reasoning → Federal Council answer (CHE) / other docs. Join with labelled headers (`TITLE:`, `TEXT:`, …). Truncate to `MAX_INPUT_CHARS` (config, default 12,000) from the end of the last section. Store the exact assembled string per affair (hash it) so evidence verification runs against what the model actually saw.

Language per affair (no language field exists in the API, see §1): explicit `lang` if the sample file gives one (`lang_source=requested`); else the only title language (`title_single`); else, among the title languages, the one most docs with text are written in (`doc_majority`); else first of de, fr, it (`default_order`). Multilingual titles occur for CHE, BE, VS, FR, GR. Federal affairs have official DE/FR/IT texts and no docs, so they fall to `default_order` (DE); eval samples therefore set `lang` explicitly per row. Doc `language` labels are occasionally wrong (e.g. affair 236793: a `de_…` file labelled French); we accept this as source noise.
