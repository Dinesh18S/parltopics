# 03 — Data & API Notes

All sources are public and need no key. Data licence: OpenParlData publishes under **CC BY 4.0** — attribute as "Source: OpenParlData.ch" in the README, UI footer and report.

> Items marked **VERIFY** are assumptions. The first build slice must check them against a real response and update this file.

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

- [ ] The `openparldata_id` in the PolitMonitor CSV equals the `id` in `/v1/affairs/{id}`
- [ ] Which relation holds the full affair text (`docs`? `texts`?) and the field name of the extracted text
- [ ] Field names for title, type, begin_date, body_key, url in nested format
- [ ] Which URL to use as the human-facing "source link" (parliament page vs OpenParlData page)
- [ ] How many affairs (especially municipal) have title only
- [ ] Rate limiting headers, if any

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

- `topic` should be "Digitalisierung" on every row (VERIFY).
- `politmonitor_scope` defines which parliaments/periods PolitMonitor covers. **Negatives may only come from inside this scope.**
- Three title columns = free multilingual test for titles (texts for CHE come from `che_affair_texts`).

### `aps_topics.xlsx`

Sheets: `Topics`, `Chapters`, `Domains`. Columns: `code, domain_de, domain_fr, chapter_de, chapter_fr, topic_de, topic_fr, url_de`. `code` is a file-local join key; do not present it as an official APS id. No IT/EN labels exist.

### VERIFY

- [ ] Exact file names/extensions of `che_affairs_keywords` and `cantonal_affairs_keywords` (csv? ndjson?) and their columns
- [ ] Join key between `che_affair_texts` and `che_affairs_keywords` and the CSV (`openparldata_id`? affair number?)
- [ ] How the text file marks language and text type
- [ ] Sizes; anything over 100 MB never goes in `data/`

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

Language per affair: from the data; if missing, detect from title with a cheap detector and flag `lang_detected=true`.
