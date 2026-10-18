# 05 — Prompt Specification

Two prompts, one engine. Prompt templates are versioned files in `src/parltopics/prompts/` (`<name>.system.txt` + `<name>.user.txt`). Change a template → new template name → re-run eval. Never edit a prompt that produced a reported number without re-running.

### Prompt versioning (what makes two numbers comparable)

- **Run level** (stored on every run manifest / `runs` row): `prompt_version` = sha256 over the hashes of **every input that shapes the prompt or the stored result**: template files, topic YAML content (or the scheme file in standard mode), few-shot examples (if any), and model params (model id, temperature, max_tokens, json mode, `MAX_INPUT_CHARS`, `TITLE_ONLY_CONF_CAP`). The individual part hashes (`template`, `topic`, `fewshot`, `params`) are stored too, so a diff shows which part changed. The human-readable template name (e.g. `adhoc_v2`) is stored as `prompt_template` and is part of the template hash.
- **Call level** (stored on every prediction): `source_sha256` of the exact assembled affair text, plus `run_id`.
- Consequence: when the partner edits `topics/digitalisation.yaml`, every later run gets a new `prompt_version`; numbers from different `prompt_version`s are never reported as comparable.

## 1. Shared principles

1. **Topic-agnostic.** The topic or scheme is injected as data. The template contains no topic words.
2. **Instructions in English, evidence in the source language.** The model must copy the evidence verbatim from the text and never translate it. (Verification in code depends on this.)
3. **Neutral.** Ask only what the affair is about. Never ask for stance, party, merit, or sentiment. The prompt says so explicitly.
4. **Main subject, not passing mention.** An affair matches a topic only if the topic is a main subject, not if a word appears once in passing. This is what beats keyword search on precision.
5. **Explicit abstain.** The model can say "abstain" (ad-hoc) or `NONE_OTHER` (standard). Forcing a choice inflates false positives; the None/Other option is a known way to improve LLM topic labelling.
6. **Strict JSON.** Output is one JSON object matching the schema; nothing else. Enforced by server-side JSON schema where available.
7. **Short rationale last.** A ≤25-word reason helps debugging; it comes after the label so it doesn't steer it, and it is never shown as evidence.
8. **Temperature 0.** Max output ~400 tokens.

## 2. Ad-hoc mode — `adhoc_v2`

### Inputs
- `topic.name`, `topic.definition` (one or a few sentences), optional `topic.include` / `topic.exclude` borderline rules as lists (from the partner's definition doc)
- `affair.text` (assembled, see data doc), `affair.lang`

### Output schema
```json
{
  "label": "match | no_match | abstain",
  "confidence": 0.0,
  "evidence": "verbatim sentence from the text, or empty string",
  "rationale": "max 25 words, English"
}
```
- `match` → evidence required.
- `abstain` → text too short/unclear to decide, or only procedural content.
- `confidence` = the model's confidence that its label is correct (0–1). Treated as a ranking score, calibrated on dev data; not shown as a probability.

### System message
```
You are a careful assistant that labels Swiss parliamentary affairs by topic for a public
database. You decide only what an affair is about. You never judge whether it is good or bad,
and you never consider party, author, or political position.

Rules:
- An affair matches the topic only if the topic is a MAIN subject of the affair, not a
  passing mention.
- The affair may be in German, French, Italian or Romansh. Read it in its own language.
- If it matches, copy ONE sentence (or one clause of at least 15 characters) from the affair
  text that best shows the topic. Copy it exactly, character for character, in the original
  language. Do not translate, shorten with "...", or paraphrase.
- If the text is too short or unclear to decide, answer "abstain".
- Respond with one JSON object only, matching the schema. No other text.
```

### User message
```
TOPIC: {topic.name}
DEFINITION: {topic.definition}
{if include}COUNTS AS THIS TOPIC:
- {each topic.include item}{/if}
{if exclude}DOES NOT COUNT:
- {each topic.exclude item}{/if}

AFFAIR (language: {affair.lang}):
<<<
{affair.text}
>>>

Return JSON: {"label": "match"|"no_match"|"abstain", "confidence": number 0-1,
"evidence": string, "rationale": string}
```

### Few-shot (optional, `adhoc_v2_fs`)
2–3 short examples **from the dev split only** (never a test-split affair, and never an affair whose `title_de` equals a test affair's): one match where the topic word never appears, one no_match where the word appears in passing, one abstain (title only, vague). Few-shot vs zero-shot is an A/B we report, not an assumption.

### Digitalisation topic file
The source is the partner's definition `data/gold/digitalisation_definition.md` (derived from how PolitMonitor actually tagged; follows PolitMonitor where it differs from the challenge slides). Its prompt form is `topics/digitalisation.yaml`: `definition` (one paragraph), `include` and `exclude` as **lists** (rendered as bullet lists), `keywords` per language (used only for the keyword-absent flag and the keyword baseline, never in the prompt). Any edit to the YAML changes `prompt_version`.

## 3. Standard mode — `standard_v1`

### Schemes
- `curia_vista` — 28 areas, one stage (needed for eval against 70k federal labels).
- `aps` — two stages: chapters (22) → topics (within chosen chapters). Labels in DE or FR matching the affair language; IT affairs get the DE label (configurable) + an unofficial IT gloss generated separately and marked `gloss_unofficial=true`.

### Output schema
```json
{
  "labels": [
    {"code": "string from the list, or NONE_OTHER",
     "confidence": 0.0,
     "evidence": "verbatim sentence from the text, or empty for NONE_OTHER"}
  ],
  "rationale": "max 25 words"
}
```
- 1–3 labels, most relevant first. `NONE_OTHER` must be the only label if used.
- Codes must come from the list; unknown codes → `status=invalid_label` (counted, not silently dropped).

### System message
Same as ad-hoc, plus:
```
- Choose between 1 and 3 categories from the list that are MAIN subjects of the affair,
  most relevant first. Use only codes from the list.
- If no category fits, or the affair is purely procedural, return exactly one label with
  code "NONE_OTHER".
```

### User message
```
CATEGORIES ({scheme.name}):
{for c in scheme}{c.code}: {c.label_in_affair_lang} — {c.short_description_if_any}
{/for}
NONE_OTHER: none of the above fits, or purely procedural

AFFAIR (language: {affair.lang}):
<<<
{affair.text}
>>>

Return JSON: {"labels": [{"code": string, "confidence": number 0-1, "evidence": string}],
"rationale": string}
```

Codes in the prompt are short local ids (`C01…C22`, `CV01…CV28`) mapped back in code, so the model never has to reproduce long labels exactly.

## 4. Post-processing (code, not prompt)

1. Validate JSON with pydantic → `parse_error` if invalid after one repair retry.
2. Verify each evidence string (see backend doc §4.3) → drop labels with failed evidence, keep the record.
3. Title-only cap on confidence.
4. Keyword-absent flag: none of `topic.keywords` (any language, case-insensitive, word-boundary) appear in the source text.
5. Decision threshold for "shown as match" (`MATCH_THRESHOLD`, default 0.5) is tuned on the dev split only, then frozen for test.

## 5. Known risks & mitigations

| Risk | Mitigation |
|---|---|
| 8B model paraphrases or translates evidence | Strong instruction + verify; report evidence-fail rate per language; try 70B |
| Over-tagging on keyword presence | "main subject" rule + negatives that contain the keyword in the dev set |
| Definition mismatch with PolitMonitor | Partner's include/exclude rules; adjudication separates model errors from label noise |
| Language bias (DE better than FR/IT) | Cross-language agreement test; per-language metrics |
| Long texts truncated | Title + submitted text first; log truncation rate |
| Prompt leakage into test | Few-shot examples only from dev split; IDs logged |
| Self-reported confidence poorly calibrated | Use as ranking; report a reliability table on dev; threshold tuned on dev |

## 6. Prompt changelog

| Version | Date | Change | Dev P/R |
|---|---|---|---|
| adhoc_v1 | 2026-10-18 | Initial (only smoke calls, no reported numbers) | — |
| adhoc_v2 | 2026-10-18 | include/exclude rendered as bullet lists (partner's definition has 11 include / 3 exclude rules); text otherwise unchanged | — |
| standard_v1 | 2026-10-18 | Initial | — |
