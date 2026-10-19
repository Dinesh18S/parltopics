# Hack Apertus Liebefeld — OpenParlData: Topic classification for Swiss parliaments with Apertus — Unisono

Swiss parliaments publish hundreds of thousands of affairs (motions, interpellations, bills) through
OpenParlData.ch, but their topic labels are coarse and inconsistent across parliaments. Monitors such as
PolitMonitor tag affairs by hand, and keyword search misses affairs that never use the word. The challenge:
use Apertus to classify affairs from federal, cantonal and municipal parliaments by topic — in German, French
and Italian — both into a standard scheme and into ad-hoc topics such as "digitalisation", and measure the
result against the manual tags.

Submissions must use the v1.5 Apertus model family.
The submission must comply with the [HackApertus T&C](https://hackapertus.ch/terms-and-conditions).

## 🎯 The Challenge

**OpenParlData: Topic classification for Swiss parliaments with Apertus** —
[hackapertus.notion.site/openparldata](https://hackapertus.notion.site/openparldata)

## Unisono — open topic classifier for Swiss parliamentary affairs

Team: Unisono · builder (build) · partner (research & pitch)

Unisono finds every affair about a topic, in German, French and Italian, and shows the sentence that proves it.

**Demo video (2 min):** [youtu.be/EpF6-megCrY](https://youtu.be/EpF6-megCrY) · **Technical report:** [`technical_report.md`](technical_report.md)

- **Ad-hoc mode:** type any topic name plus a one-line definition ("digitalisation", "Wolf") — no retraining.
- **Standard mode:** Année Politique Suisse (chapter → topic) or Curia Vista subject areas.
- **Evidence, checked by code:** Apertus v1.5 70B answers with a label, a confidence and one sentence copied
  from the affair. Plain Python verifies the sentence is really in the source; without verified evidence
  nothing is shown. A human confirms or rejects every suggestion; confirmed affairs export to Excel.
- **Whole parliaments:** federal (27,465 affairs), Bern (5,249) and Thurgau (1,447) since 2018 are indexed;
  `update` classifies only new affairs ("What's new").
- **Sovereign:** one OpenAI-compatible endpoint serving Apertus (local vLLM/Ollama or Swiss-hosted); runs
  air-gapped with Docker + SQLite. Without an endpoint the app starts in cached mode with pre-computed results.

**Results (digitalisation, every affair since 2018, against PolitMonitor's manual tags):**

| Parliament | Unisono precision / recall | Keyword search | Curia Vista area |
|---|---|---|---|
| Federal | **62.9 % / 51.0 %** | 41.3 % / 56.4 % | 40.9 % / 80.2 % |
| Bern | **68.2 % / 67.8 %** | 32.7 % / 47.4 % | — |
| Thurgau | **50.0 % / 45.5 %** | 15.7 % / 72.7 % | — |

269 tagged affairs were found that contain none of the core keywords; the same affair gets the same answer
in DE/FR/IT 94 % of the time. Method, limitations and every number: [`technical_report.md`](technical_report.md),
[`results/metrics.md`](results/metrics.md).

**How it works:** OpenParlData API / bulk files → assemble text (title, submitted text, reasoning, answer,
documents; cleaned, cut at 12,000 chars) → Apertus (strict JSON) → verify evidence (plain code) → SQLite
(append-only) → web UI with human review. Builder docs: [`docs/`](docs/); AI coding agents start at
[`AGENTS.md`](AGENTS.md).

**Template and AI tools:** started from the Hack Apertus Liebefeld template repository. Claude (Anthropic) was
used as an AI coding assistant during development (code, tests, docs, under the team's direction); it is not
part of the pipeline — all classification and translation run on Apertus.

**Data:** Source: OpenParlData.ch — licensed CC BY 4.0. Challenge files: files.openparldata.ch/hackapertus.
Reference labels: PolitMonitor digitalisation tags (challenge files). Topic schemes: Curia Vista, Année
Politique Suisse. `data/` holds only frozen sample IDs, the topic definition and review sheets; raw files are
downloaded by `make data`.

## 🔧 Resources & Tools

Check our resources & tools page for detailed information:
[https://hackapertus.notion.site/liebefeld-resources-tools](https://hackapertus.notion.site/liebefeld-resources-tools)

| Models           | URL                                      |
|------------------|------------------------------------------|
| Apertus v1.5 8B  | [huggingface.co/swiss-ai/Apertus-v1.5-8B](https://huggingface.co/swiss-ai/Apertus-v1.5-8B)  |
| Apertus v1.5 70B | [huggingface.co/swiss-ai/Apertus-v1.5-70B](https://huggingface.co/swiss-ai/Apertus-v1.5-70B) |

## The structure

Keep the files and directories as shown below — don't rename or move them.

| Path | What it is |
| --- | --- |
| `README.md` | The challenge description and submission requirements |
| `technical_report.md` | The deeper write-up: architecture, evaluation, limitations |
| `LICENSE` | Apache-2.0 |
| `src/` | Your code |

## Environment

- Include instructions for running the project in your technical report.
- Use the following environment variables:
```
LLM_NAME — name and version of the model
LLM_BASE_URL — endpoint base URL
LLM_API_KEY — your API key
```

### Run Unisono

Requirements: Docker (or [uv](https://docs.astral.sh/uv/) for `make dev`) and an OpenAI-compatible endpoint
serving Apertus. Without an endpoint the app still starts, in cached mode.

```bash
cp .env.example .env   # set LLM_NAME, LLM_BASE_URL, LLM_API_KEY
make run               # Docker; app on http://localhost:8080, check /health
make dev               # same without Docker (needs uv)
make data              # download challenge files to data/raw and check checksums
make test              # unit tests
make status            # where we stand: slices, success criteria, submission checklist
make first-loop        # 20 positives + 20 negatives → table, accuracy, evidence-verified rate
uv run parltopics data load-bulk            # once: federal bulk texts → data/cache/bulk.db (needed for > ~500 affairs)
uv run parltopics runs                      # stored runs (SQLite: data/parltopics.db)
uv run parltopics partner files             # Excel files for the domain partner → data/gold/for_partner/
make eval RUN="<dev_run> <test_run>"        # digitalisation like-for-like eval → results/metrics.json + metrics.md
uv run parltopics demo export               # refresh results/demo/*.json (cached demo results for offline mode)
uv run parltopics demo export-collections   # refresh results/collections/*.json.gz (offline copies of whole parliaments)
uv run parltopics review add <prediction_id> confirm|reject|correct [--label …]   # human review, append-only
uv run parltopics ingest --body BE --since 2018-01-01    # whole parliament: fetch + assemble every affair once, data-quality report
uv run parltopics index --body BE --topic topics/digitalisation.yaml   # classify all of it (or --scheme aps); resumable
uv run parltopics update --body BE           # only affairs new since the last ingest → classify → "new" feed (cron)
uv run parltopics export --body BE --topic topics/digitalisation.yaml  # Excel/CSV with review status → data/exports/
uv run parltopics fetch 235308 --lang fr   # text the model sees (--lang only for federal affairs)
uv run parltopics classify --affair 235308 --lang de --topic topics/digitalisation.yaml   # one model call
```

## 📦 Submission Requirements & Deliverables

The submission must:
1. follow the template repo and include all prerequisite files and definitions
2. run end-to-end when judges try to run it

### Git repo (URL)
- Create your repo from this template (**Use this template**).
- Keep the layout as it is: don't rename or move its files.
- Set the repo to PUBLIC (Settings --> Collaborators --> Manage Visibility)
- Submit the URL of YOUR Git repo.

### Technical Report (pdf)
- Update [technical_report.md](technical_report.md) in this repository with all the details for your submission.
- Upload a pdf of your technical report to the root of the repo, named as `TeamName_Report.pdf`.
- Format: pdf, max. 6 pages w/o references
- Submit the pdf of the technical report.

### Demo video (URL)
- Max. 2 min demo video of your prototype
- Add the link to the **Demo** field at the top of [technical_report.md](technical_report.md)
- Submit the URL of the video.

## ⚖️ Judging Criteria

Each challenge has its own criteria, listed in its challenge description.

The main jury scores every submission on 6 dimensions (relevant for Top 6 teams):
1. **Purposeful use of AI**
2. **Technical rigour**
3. **Value, cost & scalability**
4. **Sovereign deployability**
5. **Implementation feasibility**
6. **Pitch & presentation**

Each dimension is scored from 0 to 5.

## Getting started

1. Click **Use this template** to create your own repository.

## License

All Hack Apertus projects are open-sourced. Please check our Terms & Conditions for specific licensing details (6. What you build is open source): https://hackapertus.ch/terms-and-conditions

## Support

### FAQ
💡 https://hackapertus.ch/faq

### Contact

💬 In case you have questions, join the conversation on Discord. Alternatively, send an email to “hello@hackapertus.ch”.
