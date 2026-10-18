# 08 — Scale-up plan (from demo to a tool people can rely on)

Status 2026-10-18 ~19:30. All build slices S0–S9 are done on `main` (backup). This plan runs on branch `scale-up`.
**Hard stop: 2026-10-19 12:00.** After that only pitch, report and video. If something is not finished by then,
`main` (or the last good commit on `scale-up`) is what we submit.

## Why
The demo pool (204 affairs) is a sample, not a product. A DVS editor or a canton employee can only rely on the tool if
it covers *their whole parliament*, stays up to date, and fits their routine (find, review, export). Full populations
also give **exact** precision/recall against PolitMonitor (no sampling, no prevalence correction).

## Facts measured before planning
| | Bern (BE) | Thurgau (TG) | Federal (CHE) |
|---|---|---|---|
| Affairs since 2018 | 5,249 | 1,545 | 27,465 (no consultations) |
| PolitMonitor-tagged | 171 | 42 | 1,396 |
| Real text (sample of 40) | 39/40 | 32/40 | ~95 % |
| Notes | bilingual DE/FR | own classification (118 keywords) in the challenge data; long texts (median 8.5k chars) | baseline computed (D35) |

Gateway throughput (adhoc_v5, Bern sample, 0 errors): 182 affairs/min at concurrency 16, **256/min at 32**.
→ Bern ≈ 20 min, Thurgau ≈ 6 min, all federal ≈ 2 h.

## Decisions (user, 2026-10-18)
1. Bern full, plus Thurgau (it is small).
2. All federal affairs since 2018 for digitalisation, if buildable (≈ 2 h machine time, can run overnight).
3. adhoc_v6 first, before the big runs.

## Phases
### Phase 0 — adhoc_v6 (≈ 30 min)
- Restate the topic name + the question after the affair text (D61: topic drift on texts ≥ ~12k chars).
- Dev only first (S6 dev split + `make check-topics` + the 199828 probe). Adopt only if dev is at least as good and the
  drift is gone. Then re-run the S6 **test** once as a new, separately logged evaluation (pre-register before running).
- All large runs use the final prompt.
- **Result (D66): not adopted.** Dev F1 0.576 < 0.611 (v5); drift checks pass. adhoc_v5 stays final; no new test run.

### Phase 1 — pipeline (≈ 1.5 h, the core)
| Command | Does |
|---|---|
| `parltopics ingest --body BE --since 2018-01-01` | fetch all affairs + texts once (federal from the bulk table), store affairs/sources; data-quality report (title-only, lang missing/mismatch, truncated) |
| `parltopics index --topic … / --scheme … --body BE` | classify every ingested affair; **resumable** (skips affairs already done for the same prompt_version), retries failures, progress + ETA + tokens, concurrency 32 |
| `parltopics update --body BE` | only affairs new since the last ingest → classify them → "new since last visit" feed (cron/Docker) |
| export | Excel/CSV of suggestions + review status (what staff already use) |
Tests for: resumability (no duplicate work), idempotency, update picks only new affairs.
**Result (D67):** done; ingested BE 5,249 / TG 1,447 / CHE 27,465 (1 lang_missing); TG digitalisation indexed (1,447, resumed after 3 interruptions, no repeat work); default concurrency 16.

### Phase 2 — run it (mostly machine time)
- Bern + Thurgau: digitalisation, Covid-19, Curia Vista/APS.
- Federal ≥ 2018 (27,465): digitalisation.

### Phase 3 — the app for real users (≈ 1.5 h)
- Collection switch: Demo pool / Bern / Thurgau / Federal; filters and presets instant on indexed data.
- Task-based start: (1) **What's new?** since last visit, (2) **Find everything on a topic** in my parliament,
  (3) **Review queue** (unreviewed, by confidence, keyboard, export confirmed).
- Custom topic on a full collection: show estimate first ("Bern: 5,249 affairs ≈ 20 min"), then run (resumable).
- 20-minute user test: the partner does the 3 tasks as a DVS user; time them; fix friction.
- Offline mode: keep the demo pool cache + compact result files (no full texts in git, 10 MB file limit).
**Result (D68):** collection switch, What's new / Find all / Review queue, estimate → job → progress → cancel/continue, Excel export; verified in Chrome on a DB copy. Open: offline collection files (after Phase 2), user test with the partner.

### Phase 4 — evaluation on full populations (≈ 1 h)
- Bern and federal: exact precision/recall vs PolitMonitor next to the baselines (Curia Vista area, core keywords).
- Bern DE vs FR on real cantonal data.
- After-review numbers when the partner's sheet is back (D55, D56, D58).

### Phase 5 — report, README, video script, PDF (≈ 2 h, before 12:00)

## Rules that still apply
AGENTS.md hard rules (no commits by the agent, no names, topics only from YAML, no tuning on test, pre-register before
test runs, append-only store, never commit .env / raw data / caches / designs / private notes, files ≤ 10 MB).
Every phase ends with verification on real data, a decision log entry (D65+), private notes, and a stop for the user.
