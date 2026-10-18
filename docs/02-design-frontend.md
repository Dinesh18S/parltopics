# 02 — Design & Frontend (Demo UI)

The UI exists for one 90-second live demo and for a human to confirm labels. It is not a product website. Optimise for: readable on a projector, fast, works offline from cached results.

## 1. Stack

- FastAPI serves the API **and** one static page (`src/web/index.html`): vanilla JS + a small CSS file. No build step, no framework, no npm.
- Visual design follows the private UI reference in `designs/` (gitignored; token sheet = screen 15): light civic theme, one plum accent `#564B68`, status by text label, never colour alone.
- Fonts: Inter + IBM Plex Mono, **served locally** from `src/web/fonts/` (OFL, licences included) so the demo works offline / air-gapped. Charts: inline SVG.
- Must run inside the same Docker container as the backend.

## 2. Screens

### 2.1 Search (main screen)

```
┌──────────────────────────────────────────────────────────────────┐
│ ParlTopics   [Ad-hoc ▾ | Standard]                    [Metrics]   │
├──────────────────────────────────────────────────────────────────┤
│ Topic      [ digitalisation                                  ]   │
│ Definition [ Affairs whose main subject is digital technology…]  │
│ Filters: Level [All ▾] Language [All ▾] Parliament [All ▾]       │
│          Date from [2018] ☐ Only affairs without the keyword     │
│                                              [ Classify ▶ ]       │
├──────────────────────────────────────────────────────────────────┤
│ 47 suggested · 12 confirmed · pool: 200 affairs · Apertus 8B      │
├──────────────────────────────────────────────────────────────────┤
│ ▌CHE · Motion · 2021 · DE         match  ███████░░ 0.82          │
│ ▌E-ID: Vertrauenswürdige staatliche Identität                    │
│ ▌“…die Einführung einer staatlich anerkannten elektronischen      │
│ ▌  Identität …”   ✓ evidence verified   ⚑ keyword absent         │
│ ▌[Source ↗]                    [✓ Confirm] [✗ Reject] [✎ Correct] │
└──────────────────────────────────────────────────────────────────┘
```

- **Mode toggle:** Ad-hoc shows Topic + Definition. Standard shows a scheme picker (APS / Curia Vista) and the result card shows the chapter → topic path.
- **Preset topics** (chips under the inputs): "Digitalisation", "Covid-19", plus one APS topic. One click fills name + definition. This is the "it's general" moment in the pitch.
- **"Only affairs without the keyword"** toggle: filters to matches whose text does not contain the topic name in DE/FR/IT. This is the strongest demo argument; keep it one click away.
- **Classify** runs over a fixed demo pool (see §4), streaming results in as they finish.

### 2.2 Result card (one per affair)

Required fields, in this order:
1. Parliament (body_key), affair type, year, language badge (DE/FR/IT/RM)
2. Title (original language)
3. Label chip: `match` (green), `no_match` (grey, hidden by default), `abstain` (amber), `NONE_OTHER` (amber)
4. Confidence bar + number (2 decimals)
5. Evidence as a quote, in the source language, never translated. Badge: `✓ verified` or `title only` (and capped)
6. `⚑ keyword absent` badge when none of the topic's core keywords appears (for digitalisation: Digitalisierung, digital…, numérique, numérisation, digitale, digitalizzazione); a second, quieter `tech vocab absent` badge when the broad words (Daten/données/dati, elektronisch/électronique/elettronico, Cyber) are absent too
7. Source link (opens the parliament's / OpenParlData page)
8. Review buttons. After review the card shows who/what: "Confirmed by human" in a different colour from the AI suggestion
9. Small label "AI suggestion — needs human confirmation" on every unreviewed card

Standard mode extras: chapter → topic path (DE or FR label per affair language). APS has no Italian labels: IT affairs show the DE label (`SCHEME_LABEL_FALLBACK`) and the strip says so; the "IT (unofficial)" gloss from the design is **not** generated (it would be one more unverified model output). Each label is reviewed on its own in the detail panel.

### 2.3 Metrics (second tab)

Static page rendered from `results/metrics.json`:
- Digitalisation P/R vs baseline (bar pair: ours vs *Medien und Kommunikation*), with CIs and n; before/after adjudication.
- Curia Vista: at-least-one-correct, micro-F1.
- Cross-language agreement %.
- Cost/time per affair, 300k estimate.
- Model + prompt version + run date.

## 3. States

| State | Behaviour |
|---|---|
| Empty | Show preset topic chips and one sentence of what to do |
| Running | Progress "34 / 200 classified", cards appear as they finish; Cancel button |
| Model unreachable | Banner "Model endpoint unreachable — showing cached results from run <id>" and load the cache |
| No matches | "No matches in this pool" + suggestion to widen filters |
| Evidence failed | Card hidden by default; a counter "3 rejected (evidence not found)" that expands them, so we stay honest |

## 4. Demo pool (why not "all 300k live")

Live classification of everything is impossible in a demo. The UI classifies a **fixed pool** (default 200 affairs: mix of PolitMonitor positives, in-scope negatives, cantonal affairs, DE/FR/IT), stored in `data/samples/demo_pool.csv`. Digitalisation results are **pre-computed** and loaded instantly; the second topic runs **live** on the pool. Say this plainly in the pitch.

## 5. Copy rules

- UI language: English. Affair content: original language, untranslated; the evidence is always checked and shown in the original.
- Reading aid for reviewers who don't read the original (`REVIEW_LANG`, e.g. `de`): the parliament's **official** version when it exists (federal affairs), otherwise an **unofficial Apertus translation** on request (`TRANSLATE_MODEL`, labelled "unofficial machine translation — not evidence"). Never used for labels or evidence.
- Never show party or author on the card (neutrality; keeps attention on the topic).
- Use "suggested", never "classified as" or "is about".
- Confidence is described as "model confidence", not probability.

## 6. Accessibility & projector

- Minimum body text 16px, high contrast, not colour-only (chips also carry text).
- Keyboard: Enter runs Classify; `c` / `r` confirm/reject focused card.
- Works at 1280×720.

## 7. Acceptance checklist

Verified in S8 (headless Chrome, both live and cached-from-a-fresh-DB): items 1–5 pass; item 6 (backup video) is still open.


- [x] Typing a new topic + definition and pressing Classify returns cards with no code change (streamed; Cancel works)
- [x] Every visible `match` card has verified evidence + working source link
- [x] Keyword-absent filter (core keywords) works and shows ≥3 PolitMonitor-confirmed affairs for digitalisation (23 shown, 21 PolitMonitor-tagged)
- [x] Confirm/Reject persists across page reload
- [x] With the model endpoint down, the page still demos from cache (committed `results/demo/*.json` seed an empty DB)
- [ ] Recorded backup video of the full demo exists in `docs/`
