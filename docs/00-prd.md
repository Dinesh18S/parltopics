# OpenParlData Topic Classification — PRD

Oct 18, 2026 · @Dinesh

v2 · revised with domain review (Arivinchsa)

**What changed in v2:** APS levels corrected to chapter → topic (22 chapters, 165 topics, 8 domains above). Standard-mode evaluation fixed: the 70,008 federal affairs carry Curia Vista labels, not APS, so we add an APS ↔ Curia Vista mapping and measure on Curia Vista directly. Negative set restricted to PolitMonitor's scope; disputed cases adjudicated by hand. 41% baseline compared like-for-like (federal affairs since 2018). Multi-label metric; cross-language consistency as the main bias check. Human-in-the-loop wording: the service supports DVS, it does not replace them. Plus: APS labels are German/French only (from aps\_topics.xlsx), so Italian affairs get the DE/FR label and an unofficial gloss.

## In one line

We build an open, reusable service that automatically suggests topics for any Swiss parliamentary affair, in German, French and Italian, and explains why, with a link to the source. It works two ways: standard topics (the APS scheme) and ad-hoc topics anyone defines ("digitalisation", "Covid-19") without retraining. We prove it on the real DVS digitalisation case, where a team does this tagging by hand today, so we can measure ourselves against their existing list.

This doc is for you to double-check: the use case, the problem, our solution, the pipeline, and the pitch. Comment on anything that looks wrong for the Swiss-politics side.

## The problem

Switzerland has parliaments at three levels (federal, 26 cantons, hundreds of municipalities). OpenParlData collects 90 of them: 300,000+ affairs in German, French, Italian and, to a tiny extent, Romansh. There is no shared way to organise them by topic. To find all affairs about a subject, someone has to read and tag them by hand, in each language, and the result is always incomplete. Two things make it hard:

To find all affairs about a subject, someone has to read and tag them by hand, in each language, and the result is always incomplete. Two things make it hard:

1. **Keyword search misses things.** A cybersecurity motion, an e-ID law and an e-voting interpellation are all "about digitalisation" but may never use that word — and they use different words in DE, FR and IT. So searching "Digitalisierung" finds only a fraction.
2. **The parliaments' own categories don't fit.** Curia Vista has no "digitalisation" subject area. The closest, "Medien und Kommunikation", contains 81% of the digitalisation affairs (recall) but only 41% of its affairs are about digitalisation (precision), measured on federal affairs since 2018. A fixed scheme can't answer a question it wasn't designed for.

Cantonal schemes differ again (SG, TG, Zug, ZH each use their own). The data exists; its thematic structure does not. That gap is what we fill.

## Our use case and solution

We build **one engine, two modes** — a topic-agnostic classifier, not a digitalisation-specific one.

- **Standard mode:** classify an affair against the APS scheme at chapter → topic (22 chapters, 165 topics; 8 domains sit above). An affair may receive more than one topic. This gives every affair the same standard tag, making parliaments comparable. Note: APS publishes labels in German and French only — no Italian or English. For Italian affairs we assign the DE/FR label and can show an unofficial IT gloss, clearly marked. (Confirmed against aps\_topics.xlsx: sheets Topics/Chapters/Domains; columns code, domain\_de/fr, chapter\_de/fr, topic\_de/fr, url\_de; the \`code\` is a file-local join key, not an official APS id.)
- **Ad-hoc mode:** give the engine any topic name plus a one-line definition ("digitalisation", "Covid-19"), and it tags affairs for that topic — no retraining. Changing the topic is changing one line of the prompt.

For every affair the system returns the topic, a confidence score, the exact sentence that justifies it, and a source link. Labels are suggestions: a human confirms or corrects them. It runs on open Apertus, deployable locally or on Swiss infrastructure, with no closed model.

Why topic-agnostic matters for our 24 hours: generality is free. We don't build a separate "other topics" feature; we just avoid hardcoding "digitalisation" into the prompt. So we can spend our real time on the pipeline and on measuring digitalisation well.

## How we prove it

Digitalisation is not the whole project — it is the test case, chosen because it has real ground truth and a real customer (DVS, who does this tagging by hand today).

**1. Ad-hoc proof (headline).**

- Positive set: politmonitor\_digitalisierung.csv (3,433 affairs, 35 parliaments).
- Negative set: non-tagged affairs drawn only from the same parliaments and periods PolitMonitor covers (check politmonitor\_scope). PolitMonitor is manual and incomplete, so "not tagged" is not proof of "not digital".
- Disputed cases (model says digital, PolitMonitor didn't) are adjudicated by hand. We report precision both before and after adjudication.
- Baseline is like-for-like: our precision/recall on federal affairs since 2018 vs "Medien und Kommunikation" (41% precision, 81% recall).

**2. Standard proof (backbone).** The 70,008 federal affairs carry Curia Vista subject areas (28), not APS topics, so APS accuracy can't be measured on them directly. We do three things:

- Curia Vista run: run standard mode with the 28 Curia Vista areas and measure directly against the federal labels.
- APS ↔ Curia Vista mapping at chapter level (domain work), so APS chapter predictions can be scored against existing labels.
- Small APS gold sample: \~50 affairs hand-labelled with APS chapter/topic for a direct APS check.
- Multi-label metric: Curia Vista assigns \~2 areas per affair, so we report "at least one correct" and micro-F1, not single-label accuracy.

**3. Generality proof (30 seconds live).** Run the same engine on a second topic with no code change.

Together these cover the challenge's actual objective (a reusable classifier) while giving us a concrete, measurable result.

## The pipeline

Every affair runs through the same five steps. The topic (name + one-line definition) is the only thing that changes between digitalisation, Covid-19 or an APS topic.

1. **Fetch** the affair from the OpenParlData API (title + text, in its language).
2. **Classify** with Apertus: send the affair plus the topic definition, get back strict JSON — label, confidence, and the exact sentence that justifies it.
3. **Verify** in plain code, no model: the evidence sentence must appear in the source; otherwise reject. If an affair has only a title (common for municipal parliaments), the title counts as evidence and confidence is capped lower. This is what keeps us traceable.
4. **Store** the topic, confidence, evidence sentence and source link.
5. **Show** in a small demo UI: type a topic, see matching affairs across parliaments and languages, each with its evidence. A human can confirm or correct.

That loop repeats across affairs, languages and parliament levels. The model reads text, so it doesn't care whether an affair is federal or cantonal — coverage is about running it on more data, not changing the model.

## Scope for 24 hours

**Build (core):**

- One topic-agnostic pipeline (covers any keyword for free).
- Explainability baked in: confidence + evidence sentence + source link on every label.
- A small demo UI: type a topic, see matching affairs light up.
- A suggest-and-confirm step so a human can correct labels.

**Measure:**

- Digitalisation precision/recall, like-for-like vs the 41% baseline (federal since 2018).
- Curia Vista + APS sample accuracy (multi-label: at least one correct, micro-F1).
- Cross-language consistency: same affair in DE/FR/IT, how often labels agree (main bias check).

**Only demo, don't fully build:**

- A second topic run live (proves generality, 30 seconds).
- A couple of cantonal affairs (proves it works across levels; full per-canton evaluation is out of scope).
- A rough cost/time estimate for scaling to 300k+ (not an actual full run).

**Skip:**

- Reviving the dead 1996–2014 descriptors (nice idea, mention only).
- Full per-canton / per-topic coverage (would blow the 24h). Party-level bias analysis is a named next step, not in scope now.

## Data we use

All public, no key. Main source is the OpenParlData API (REST/JSON): affairs, documents with extracted text, bodies, persons, votes, in de/fr/it/rm, federal + cantonal + municipal.

The challenge also provides labelled files at files.openparldata.ch/hackapertus (see its README):

| File | What's in it | We use it for |
| --- | --- | --- |
| politmonitor\_digitalisierung.csv | 3,433 affairs across 35 parliaments tagged "Digitalisierung" | Digitalisation ground truth (our headline eval) |
| che\_affairs\_keywords | 70,008 federal affairs with Curia Vista subject areas (28), DE/FR/IT | Curia Vista evaluation; APS chapter check via mapping |
| che\_affair\_texts.ndjson.gz | 210,437 texts: submitted text, reasoning, Federal Council answer, DE/FR/IT | Affair text for classification |
| cantonal\_affairs\_keywords | 10,742 affairs from SG, TG, Zug, ZH with their own labels | Cross-level spot-check |
| aps\_topics.xlsx | APS scheme: 8 domains, 22 chapters, 165 topics (DE/FR only, no IT/EN) | Standard-mode label set |

About the digitalisation CSV: its columns are openparldata\_id, body\_key, number, begin\_date, type\_en, title\_de, title\_fr, title\_it, url, politmonitor\_scope, politmonitor\_id, topic. The `openparldata_id` links each row to the full affair via the API; the three title columns give us the multilingual test for free. This file is our **positive set** (affairs that are digitalisation); to measure precision we also pull non-tagged affairs as a **negative set**.

One consequence of aps\_topics.xlsx: APS labels exist in German and French only, so in standard mode an Italian affair gets the DE/FR label plus, if useful, an unofficial IT gloss we generate and mark as such. Ad-hoc mode (including digitalisation) is unaffected, since we supply the topic definition ourselves.

## How we're scored

Two rubrics. We build each feature to hit a named line and say which line we're hitting in the pitch.

| Rubric line | How we hit it |
| --- | --- |
| Usefulness (community + public sector) | Supports and speeds up DVS's manual digitalisation monitoring; works for any topic |
| Technical quality & reproducibility | Public repo, README, one-command run, code-checked evidence |
| Multilingual performance | Measured on de/fr/it; same affair classified in all three languages |
| Innovation | Ad-hoc topics without retraining; builds on the proven LLM-labelling method (ParlaCAP) but adds ad-hoc + traceability |
| Ease of integration | Output as an API endpoint or export, as OpenParlData already accepts |
| Quality of the pitch | Partner delivers the domain story; live demo + numbers |
| Purposeful use of AI | Apertus does the language judgement; code does retrieval and verification |
| Technical rigour | Precision/recall vs ground truth, like-for-like baseline, honest error analysis |
| Value, cost & scalability | Cost/time per affair; estimate for 300k+ |
| Sovereign deployability | One OpenAI-compatible endpoint, swappable local Apertus / CSCS, no closed model |
| Implementation feasibility | Thin pipeline, standard tools, runs today |

Ethics (partner's lane): explainability (confidence + evidence), human-in-the-loop (suggestions only), bias check, political neutrality. Bias check has three parts: (1) cross-language consistency — classify the same federal affair in DE, FR and IT and report how often the labels agree; (2) accuracy by parliament level and by language; (3) party-level analysis named as a next step (needs authorship data from the API). Neutrality: the prompt asks only for the topic, never for a position or evaluation.

## The pitch (5 minutes)

Lead with the live demo, close with impact. Partner carries the "why it matters", builder carries the demo and the how.

1. **The gap (partner, \~45s).** The data exists for 90 parliaments, but its thematic structure doesn't. Finding all affairs on a topic means manual, multilingual work, and it's always incomplete.
2. **Live demo (builder, \~90s).** Type "digitalisation"; affairs come up across federal and cantonal parliaments, DE/FR/IT, each with evidence and a source link. Show 2–3 where the word "Digitalisierung" never appears — use only examples confirmed in the PolitMonitor list (cybersecurity sits under security policy in APS and may be contested).
3. **It's general (builder, \~30s).** Type a second topic (an APS topic, or "Covid-19"). Same engine, no retraining.
4. **The numbers (partner, \~60s).** Precision/recall vs PolitMonitor on federal affairs since 2018, compared with the 41% baseline; affairs we found that the manual list missed (after adjudication); Curia Vista / APS accuracy; cross-language agreement.
5. **Why it matters + what's next (partner, \~45s).** One shared classification makes parliaments comparable; it supports a real manual process with human review; it's open and sovereign. Next: OpenParlData endpoint, party-level bias check.

Backups: a recorded screen capture of the demo in case Wi-Fi or the endpoint fails; the slides in the repo.

## Your lane (research + pitch, no code)

**Research / data**

- Curate the eval set: \~100 affairs across de/fr/it and levels; confirm the digitalisation gold labels make sense.
- Build the APS ↔ Curia Vista chapter mapping and hand-label \~50 affairs with APS chapter/topic.
- Judge disputed cases: when Apertus tags something digital that PolitMonitor didn't, decide who's right.
- Write a one-page definition of "digitalisation" with borderline rules (cybersecurity, media, data protection, post/telecom) for the prompt and the adjudication.
- Bias & neutrality check (see above). Skim ParlaCAP and the "None/Other" label trick — both sharpen our prompt.

**Pitch (you deliver this half)**

- Pick the demo affairs that look sharp to someone who knows Swiss politics.
- Write and deliver the "why it matters" story: the missing thematic layer, the 81/41 proof that fixed schemes fail ad-hoc questions, why shared classification helps 90 parliaments.
- Own problem, impact and the honest-evaluation framing; builder covers demo and architecture.

## Open questions for the case partner

Most things are answered by the deck and the data. These few are worth a quick ask:

1. Is politmonitor\_digitalisierung.csv the reference you want us measured against, or is there a cleaner one?
2. Is a strong result on a representative sample enough, or must we show a credible path to all 300,000+ affairs?
3. On Sunday, what would make you call this a success — high accuracy on digitalisation, broad APS coverage, or something you could actually integrate and keep running?
4. Is there an existing mapping between APS and the Curia Vista subject areas, or should we build one?
5. What counts as digitalisation for DVS/PolitMonitor, especially cybersecurity, media and data protection? Are the tagging criteria written down?

Already decided: integration format (API or export both fine), Romansh (nice-to-have, "tiny extent"). APS levels are chapter → topic per the deck, confirmed against aps\_topics.xlsx (DE/FR only); only the mapping to Curia Vista remains.

## Build approach

**Director workflow (pstack-style).** Dinesh builds by directing AI. We settle the plan first (this PRD + a thin spec), then let an agent build in vertical slices, and treat a verification step as the real definition of "done" (prove it on the running pipeline, not just "it compiles"). Borrowed from Matt Pocock's grill-then-spec chain and pstack's verification-first discipline. Keep it light for 24h: one pipeline, evidence on every claim, no over-planning.

**First loop (start now, no mentor answer needed):**

1. Load politmonitor\_digitalisierung.csv; take 20 rows (mix of DE/FR/IT and affair types).
2. For each, fetch the full affair from the OpenParlData API by openparldata\_id.
3. One Apertus call per affair: pass title+text + the digitalisation definition; return strict JSON {label, confidence, evidence}.
4. Verify the evidence sentence appears in the source (plain code); reject if not.
5. Compare to the CSV's topic column (all should be "yes"). Then add 20 non-tagged affairs and check the model says "no".

That five-step loop is the whole system in miniature and your first measurable result.

**Model / where to run.** Start on Apertus v1.5 8B locally (fast, cheap, private, easy sovereignty story) to build and measure today; A/B against 70B on the CSCS endpoint once the key arrives. Wrap the model call behind one OpenAI-compatible client with LLM\_NAME / LLM\_BASE\_URL / LLM\_API\_KEY, so switching local ↔ CSCS is a config change, not code.

**Evaluation plan (what we report):**

- Ad-hoc / digitalisation: precision & recall vs the PolitMonitor list, like-for-like on federal affairs since 2018, before and after hand-adjudication of disputed cases. Beat the 41% precision baseline.
- Standard: Curia Vista run (28 areas) scored directly on the 70k federal labels; APS chapter via the mapping; \~50 hand-labelled APS gold affairs. Multi-label metric: "at least one correct" + micro-F1.
- Multilingual: classify the same federal affair in DE/FR/IT; report how often labels agree.
- Scalability: cost/time per affair, then a back-of-envelope estimate for 300k+ (don't run it all).

**Requirement docs to generate before building (Dinesh's standard set), as .md:** product requirements (this PRD), design/frontend notes for the demo UI, data & API notes, backend/pipeline guidelines, prompt spec (both modes + the "None/Other" abstain), and an eval harness checklist.

## Kickoff prompt for a new chat

Paste this into a fresh chat to start building.

```
I'm at Hack Apertus Liebefeld (18-19 Oct 2026), solo-building with a partner who does the Swiss-politics research and pitch (no code). Our challenge: OpenParlData topic classification. I build by directing AI, not hand-coding.

WHAT WE'RE BUILDING
An open, reusable classifier for Swiss parliamentary affairs. One engine, two modes:
- Standard: classify to the APS scheme (chapter -> topic; 22 chapters, 165 topics; DE/FR only).
- Ad-hoc: any topic name + one-line definition ("digitalisation", "Covid-19"), no retraining.
For each affair return: topic, confidence, the exact evidence sentence, and a source link. Labels are suggestions a human confirms. Runs on open Apertus, locally or on Swiss cloud.

WE PROVE IT ON DIGITALISATION (the DVS use case): reproduce the manual PolitMonitor tagging automatically and measure against it.

PIPELINE: OpenParlData API (fetch affair) -> Apertus (classify, strict JSON) -> verify evidence sentence is in the source (plain code) -> store topic+confidence+evidence+link -> small demo UI (type a topic, see matching affairs across parliaments/languages, human confirms).

DATA (public, no key): OpenParlData API (api.openparldata.ch). Labelled files at files.openparldata.ch/hackapertus: politmonitor_digitalisierung.csv (3,433 tagged affairs = digitalisation ground truth), che_affairs_keywords (70,008 federal affairs, 28 Curia Vista areas), che_affair_texts.ndjson.gz (210,437 texts), cantonal_affairs_keywords (10,742). APS scheme in aps_topics.xlsx (8 domains/22 chapters/165 topics, DE/FR).

MODEL: Apertus v1.5 8B local first, 70B on CSCS endpoint when key arrives. Wrap behind one OpenAI-compatible client (LLM_NAME/LLM_BASE_URL/LLM_API_KEY) so local<->CSCS is config-only.

FIRST TASK: before any code, generate my requirement docs as .md files (product requirements, design/frontend for the demo UI, data & API notes, backend/pipeline guidelines, prompt spec for both modes incl. a "None/Other" abstain label, eval harness checklist). Then build the first loop: read the CSV, pull 20 affairs by openparldata_id from the API, one Apertus call each returning {label, confidence, evidence}, verify the evidence is in the source, compare to the CSV. Use the HackApertus project template, Apache-2.0, README with setup.

EVAL TO REPORT: digitalisation precision/recall like-for-like vs the 41% baseline (federal since 2018), before/after hand-adjudication; Curia Vista + APS sample accuracy (multi-label: at-least-one-correct + micro-F1); cross-language consistency (same affair in DE/FR/IT); cost/time per affair + estimate for 300k+.

Start by writing the requirement docs.
```

## Sources

**Challenge & data**

- Challenge slides: [hackapertus-topic-classification](https://hackapertus-topic-classification-5c233f.gitlab.io/#/1)
- [OpenParlData API](https://api.openparldata.ch/documentation) · [data export](https://files.openparldata.ch) · labelled files: files.openparldata.ch/hackapertus
- [OpenParlData classification wiki (prior work)](https://gitlab.com/groups/opendata.ch/openparldatach/-/wikis/Home/Future-Topics/Classification)
- [Glue: OpenParlData at Hack Apertus](https://www.glue.ch/en/2026/10/08/openparldata-hack-apertus-swiss-parliamentary-data/)
- [APS themes (scheme source)](https://anneepolitique.swiss/de/themen/) · [APS codebook (Gesamtdatensatz)](https://anneepolitique.swiss/wp-content/uploads/2026/06/Codebook-Gesamtdatensatz-zur-Politchronik_20260524.pdf)
- [Curia Vista explained](https://www.parlament.ch/en/ratsbetrieb/curia-vista/curia-vista-explained)
- Related federal work: [Bundeskanzlei DTI Innovation Challenge — semantic analysis of Curia Vista](https://www.bk.admin.ch/dam/bk/de/dokumente/dti/themen/veranstaltungen/Innovation_Challenge_DTI-SI.pdf.download.pdf) (the Federal Chancellery wants exactly this; good pitch point)

**Prior art (classification methods)**

- [BFH SwissParlTopicModelling prototype](https://huggingface.co/spaces/rcds/SwissParlTopicModelling)
- [Demokratis classification](https://github.com/Demokratis-ch/demokratis-ml) (deployed Swiss topic classifier; simple methods, honest scope)
- [ParlaCAP](https://arxiv.org/abs/2602.16516) (LLM zero-shot topic labelling across 29 parliaments — validates our method) · [classifier](https://huggingface.co/classla/ParlaCAP-Topic-Classifier)

**Model**

- [Apertus v1.5 8B](https://huggingface.co/swiss-ai/Apertus-v1.5-8B) · [70B](https://huggingface.co/swiss-ai/Apertus-v1.5-70B) · [swiss-ai](https://huggingface.co/swiss-ai)

**Build workflow**

- [HackApertus project template](https://github.com/HackApertus/project-template)
- [Matt Pocock skills](https://github.com/mattpocock/skills) (grill-with-docs, to-spec) · [pstack](https://github.com/cursor/plugins/tree/main/pstack) (verification-first) · [Agent Skills docs](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)

Finding: no public APS ↔ Curia Vista crosswalk exists, so the chapter-level mapping is build work (partner, \~1h).
