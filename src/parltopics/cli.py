from pathlib import Path

import typer
import uvicorn

from parltopics.batch import run_sample
from parltopics.classify import classify_adhoc
from parltopics.config import get_settings
from parltopics.evaluate import report as reports
from parltopics.evaluate.samples import build_first_loop
from parltopics.llm import LLMClient
from parltopics.prompts import load_prompt
from parltopics.runlog import log_call, start_run
from parltopics.sources import bulk
from parltopics.sources.api import OPDClient
from parltopics.sources.assemble import LangMissing, assemble
from parltopics.store import Store
from parltopics.topics import keyword_absent, load_topic, tech_vocab_absent

RESULTS_DIR = Path("results")

app = typer.Typer(no_args_is_help=True)
data_app = typer.Typer(no_args_is_help=True, help="Challenge data files.")
app.add_typer(data_app, name="data")
sample_app = typer.Typer(no_args_is_help=True, help="Build frozen sample files.")
app.add_typer(sample_app, name="sample")
report_app = typer.Typer(no_args_is_help=True, help="Reports from stored runs.")
app.add_typer(report_app, name="report")
review_app = typer.Typer(no_args_is_help=True, help="Human review of stored predictions (append-only).")
app.add_typer(review_app, name="review")


@app.callback()
def main() -> None:
    """ParlTopics command line."""


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8080) -> None:
    """Start the API server."""
    uvicorn.run("parltopics.api:app", host=host, port=port)


@app.command()
def fetch(affair_id: int, lang: str | None = typer.Option(None, help="de|fr|it, federal affairs only")) -> None:
    """Fetch one affair and print the assembled text the model will see."""
    settings = get_settings()
    affair = OPDClient(settings).get_affair(affair_id)
    try:
        source = assemble(affair, settings.max_input_chars, lang)
    except LangMissing as e:
        typer.echo(f"status=lang_missing {e}")
        raise typer.Exit(2)
    except ValueError as e:
        typer.echo(f"error: {e}")
        raise typer.Exit(2)
    typer.echo(
        f"id={affair.id} body={affair.body.key} number={affair.number} type={affair.type} "
        f"date={affair.begin_date}\nlang={source.lang} ({source.lang_source}) "
        f"detected={source.detected_lang} mismatch={source.lang_mismatch}\n"
        f"sections={','.join(source.sections)} title_only={source.title_only}\n"
        f"chars={len(source.text)}/{source.n_chars_full} truncated={source.truncated} "
        f"cut_section={source.cut_section} chars_lost={source.chars_lost}\n"
        f"url={source.url}\nsha256={source.sha256}\n---"
    )
    typer.echo(source.text)


@app.command()
def classify(
    topic: Path = typer.Option(..., help="topic YAML, e.g. topics/<name>.yaml"),
    affair: int | None = typer.Option(None, help="one OpenParlData affair id"),
    sample: Path | None = typer.Option(None, help="sample CSV (affair_id, body_key, lang, gold, ...)"),
    lang: str | None = typer.Option(None, help="de|fr|it, federal affairs only (with --affair)"),
    prompt_version: str = "adhoc_v3",
    notes: str = "",
) -> None:
    """Classify one affair (--affair) or a sample file (--sample) against one ad-hoc topic."""
    settings = get_settings()
    if (affair is None) == (sample is None):
        raise typer.BadParameter("pass exactly one of --affair or --sample")
    store = Store(settings.db_path)
    if sample is not None:
        run = run_sample(settings, store, sample, topic, RESULTS_DIR, prompt_version, notes)
        typer.echo(f"run_id={run.run_id} prompt_version={run.fingerprint.prompt_version[:12]}")
        return
    affair_obj = OPDClient(settings).get_affair(affair)
    try:
        source = assemble(affair_obj, settings.max_input_chars, lang)
    except LangMissing as e:
        typer.echo(f"status=lang_missing {e}")
        raise typer.Exit(2)
    prompt = load_prompt(prompt_version)
    topic_obj = load_topic(topic)
    run = start_run(RESULTS_DIR, prompt, topic_obj, topic, settings, notes=notes or f"single affair {affair}")
    store.add_run(run, topic_obj)
    store.add_source(affair_obj, source)
    prediction = classify_adhoc(
        LLMClient(settings), prompt, source, topic_obj, settings.title_only_conf_cap, run.run_id
    )
    log_call(RESULTS_DIR, prediction)
    prediction_id = store.add_prediction(prediction.model_dump() | {
        "body_key": affair_obj.body.key, "title": source.title,
        "keyword_absent": keyword_absent(source.text, topic_obj),
        "tech_vocab_absent": tech_vocab_absent(source.text, topic_obj),
    })
    store.finish_run(run.run_id, 1)
    typer.echo(prediction.model_dump_json(indent=2, exclude={"raw_json"}))
    typer.echo(f"run_id={run.run_id} prompt_version={run.fingerprint.prompt_version[:12]} prediction_id={prediction_id}")


@sample_app.command("first-loop")
def sample_first_loop(
    out: Path = Path("data/samples/first_loop.csv"),
    n_pos: int = 20,
    n_federal: int = 6,
    since: str = "2018-01-01",
    seed: int = 42,
    force: bool = False,
) -> None:
    """20 PolitMonitor positives + 20 in-scope negatives (same parliaments, since 2018), fixed seed."""
    if out.exists() and not force:
        typer.echo(f"{out} exists (frozen); use --force to rebuild")
        return
    df = build_first_loop(get_settings(), n_pos, n_federal, since, seed)
    df.to_csv(out, index=False)
    typer.echo(f"wrote {out}: {len(df)} rows, gold={df.gold.value_counts().to_dict()}")


@report_app.command("first-loop")
def report_first_loop(run_id: str, compare_to: str | None = None) -> None:
    """Table, summary, truncation report; optionally what changed vs another run on the same sample."""
    store = Store(get_settings().db_path)
    manifest, rows = reports.load_run(store, run_id)
    typer.echo(reports.table(rows))
    typer.echo("")
    typer.echo(reports.summary_text(manifest, rows))
    typer.echo("")
    typer.echo(reports.truncation_report(rows))
    if compare_to:
        old_manifest, old_rows = reports.load_run(store, compare_to)
        old_fp, new_fp = old_manifest["fingerprint"]["parts"], manifest["fingerprint"]["parts"]
        changed = [k for k in new_fp if old_fp.get(k) != new_fp[k]]
        typer.echo(f"\nvs run {compare_to} (prompt parts changed: {changed})")
        typer.echo(reports.compare(old_rows, rows))


@app.command()
def runs(limit: int = 20) -> None:
    """List stored runs, newest first."""
    for r in Store(get_settings().db_path).runs()[:limit]:
        typer.echo(f"{r['id']}  {r['model']:<18} {r['prompt_template']} {r['prompt_version'][:12]}  "
                   f"{r['topic_name']:<15} n={r['n_predictions']:<4} finished={bool(r['finished_at'])}  {r['notes']}")


@review_app.command("add")
def review_add(
    prediction_id: int,
    decision: str = typer.Argument(..., help="confirm | reject | correct"),
    label: str | None = typer.Option(None, help="corrected label (required for correct)"),
    reviewer: str = "",
    note: str = "",
) -> None:
    """Record a human review. The prediction itself is never changed."""
    review_id = Store(get_settings().db_path).add_review(prediction_id, decision, label, reviewer, note)
    typer.echo(f"review_id={review_id}")


@review_app.command("show")
def review_show(prediction_id: int) -> None:
    """Show a prediction's reviews (oldest first; the latest one counts)."""
    for r in Store(get_settings().db_path).reviews(prediction_id):
        typer.echo(f"{r['id']} {r['created_at']} {r['decision']} {r['corrected_label'] or ''} "
                   f"by={r['reviewer']} {r['note']}")


@data_app.command("download")
def data_download(force: bool = False) -> None:
    """Download challenge files into data/raw and compare with committed checksums."""
    settings = get_settings()
    raw_dir = settings.data_dir / "raw"
    checksum_file = settings.data_dir / "raw_files.sha256"
    for name in bulk.download_challenge_files(raw_dir, force):
        typer.echo(f"downloaded {name}")
    expected = bulk.read_checksums(checksum_file)
    status = bulk.check_files(raw_dir, expected)
    for name, state in status.items():
        typer.echo(f"{state:8} {name}")
    if not expected:
        checksum_file.write_text(
            "".join(f"{bulk.sha256_file(raw_dir / n)}  {n}\n" for n in bulk.CHALLENGE_FILES)
        )
        typer.echo(f"wrote {checksum_file}")
    if any(s in {"missing", "changed"} for s in status.values()):
        raise typer.Exit(1)
