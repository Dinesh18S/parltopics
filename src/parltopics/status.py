"""`parltopics status`: where the project stands against the build plan, the success criteria and the submission
checklist — computed from real artefacts (metrics.json, samples, caches, files), never from memory."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


DONE, PART, TODO = "✓", "◐", "✗"


@dataclass
class Item:
    state: str
    text: str
    next_step: str = ""


def _json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return ""


def _demo_keyword_free_hits(root: Path, threshold: float) -> int:
    data = _json(root / "results" / "demo" / "digitalisation.json")
    return sum(1 for p in data.get("predictions", [])
               if p.get("status") == "ok" and p.get("label") == "match" and (p.get("confidence") or 0) >= threshold
               and p.get("keyword_absent") and p.get("gold") == 1)


def collect(root: Path) -> dict[str, list[Item]]:
    metrics = _json(root / "results" / "metrics.json")
    digi = metrics.get("digitalisation_federal_2018", {})
    cv = metrics.get("curia_vista_standard", {})
    report = (root / "technical_report.md").read_text() if (root / "technical_report.md").exists() else ""
    readme = (root / "README.md").read_text() if (root / "README.md").exists() else ""
    adjudication = metrics.get("adjudication", {})
    answered, total = adjudication.get("answered", 0), adjudication.get("rows", 0)
    full = metrics.get("full_population", {}).get("CHE", {}).get("model")
    threshold = digi.get("threshold", {}).get("chosen_on_dev", 0.9)
    t = digi.get("test", {}).get("at_chosen_threshold", {})
    base = digi.get("baselines_full_slice", {}).get("curia_vista_area", {})
    crosslang = metrics.get("cross_language")
    cost = metrics.get("cost_time")

    slices = [
        Item(DONE if (root / "Dockerfile").exists() else TODO, "S0 scaffold, Docker, /health"),
        Item(DONE if (root / "data" / "raw_files.sha256").exists() else TODO, "S1 data + text assembly"),
        Item(DONE if (root / "src" / "parltopics" / "llm.py").exists() else TODO, "S2 Apertus client, JSON"),
        Item(DONE if (root / "src" / "parltopics" / "verify.py").exists() else TODO, "S3 evidence verification"),
        Item(DONE if (root / "results" / "first_loop.md").exists() else TODO, "S4 first loop"),
        Item(DONE if (root / "src" / "parltopics" / "store.py").exists() else TODO, "S5 store, runs, reviews"),
        Item(DONE if digi else TODO, "S6 digitalisation like-for-like eval"),
        Item(DONE if cv.get("test") else (PART if cv else TODO), "S7 standard mode (Curia Vista)",
             "" if cv.get("test") else "run Curia Vista test"),
        Item(DONE if (root / "src" / "web" / "index.html").exists() and (root / "results" / "demo").exists() else TODO,
             "S8 API + demo UI + cached mode"),
        Item(DONE if crosslang and cost else (PART if crosslang or cost else TODO), "S9 cross-language + cost/time",
             "" if crosslang and cost else "parltopics eval crosslang / cost"),
    ]

    p_ok = t.get("precision_corrected_ci95") and t["precision_corrected_ci95"][0] > (base.get("precision") or 1)
    r_ok = t.get("recall") is not None and base.get("recall") is not None and t["recall"] >= base["recall"] - 0.05
    hits = _demo_keyword_free_hits(root, threshold)
    criteria = [
        Item(DONE if p_ok and r_ok and answered else PART if p_ok else TODO,
             f"1 Digitalisation: precision {t.get('precision_corrected', 0):.0%} (CI low "
             f"{(t.get('precision_corrected_ci95') or [0])[0]:.0%}) vs baseline {base.get('precision', 0):.0%}; recall "
             f"{t.get('recall', 0):.0%} vs {base.get('recall', 0):.0%}; review {answered}/{total} answered"
             + (f"; all {full['n']:,} federal affairs: P {full['precision']:.0%} / R {full['recall']:.0%}" if full else ""),
             ("recall below baseline" if not r_ok else "") + ("; after-review numbers need the returned sheet"
                                                               if not answered else "")),
        Item(DONE if hits >= 3 else TODO, f"2 ≥ 3 keyword-free PolitMonitor affairs in the demo: {hits}"),
        Item(DONE if (root / "results" / "demo" / "covid19.json").exists() else TODO,
             "3 second topic runs without code change (Covid-19 preset + custom topics)"),
        Item(DONE if cv.get("test") and metrics.get("aps_gold") else PART if cv.get("test") else TODO,
             "4 Curia Vista multi-label: " + (f"at-least-one {cv['test']['at_least_one_correct']['rate']:.0%}, "
                                             f"micro-F1 {cv['test']['micro']['f1']:.2f}" if cv.get("test") else "missing")
             + "; APS sample check", "APS needs partner mapping/gold"),
        Item(DONE if crosslang else TODO, "5 cross-language agreement DE/FR/IT", "" if crosslang else "S9"),
        Item(DONE if cost else TODO, "6 cost/time per affair + 300k estimate", "" if cost else "S9"),
        Item(DONE if "`project name`" not in report and "`team name`" not in report else TODO,
             "7 technical report filled", "fill technical_report.md"),
    ]

    tracked = _git(root, "ls-files").splitlines()
    leaks = [f for f in tracked if f == ".env" or f.startswith(("data/raw/", "data/cache/", "designs/", "private/"))
             or f.endswith((".db", ".db-wal", ".db-shm"))]
    pdfs = list(root.glob("*_Report.pdf"))
    tests = subprocess.run(["uv", "run", "pytest", "-q"], cwd=root, capture_output=True, text=True)
    last = (tests.stdout.strip().splitlines() or [""])[-1]
    submission = [
        Item(DONE if tests.returncode == 0 else TODO, f"tests: {last}"),
        Item(DONE if not leaks else TODO, "no secrets / raw data / designs / private notes tracked in git",
             ", ".join(leaks[:5])),
        Item(DONE if "`challenge name`" not in readme and "`team name`" not in readme else TODO,
             "README title + challenge filled (docs/07)", "fill README.md template fields"),
        Item(DONE if "`link to video`" not in report else TODO, "demo video link in technical_report.md",
             "record ≤ 2 min video, add link"),
        Item(DONE if pdfs else TODO, "technical report PDF <TeamName>_Report.pdf in repo root", "export report to PDF"),
        Item(DONE if not _git(root, "status", "--porcelain").strip() else PART, "everything committed",
             "commit pending changes"),
    ]
    return {"Build slices": slices, "Success criteria (docs/01 §7)": criteria, "Submission (docs/07)": submission}


def render(sections: dict[str, list[Item]]) -> str:
    out = []
    for title, items in sections.items():
        done = sum(i.state == DONE for i in items)
        out.append(f"\n{title}  [{done}/{len(items)}]")
        for i in items:
            out.append(f"  {i.state} {i.text}" + (f"\n      → {i.next_step}" if i.next_step and i.state != DONE else ""))
    return "\n".join(out)
