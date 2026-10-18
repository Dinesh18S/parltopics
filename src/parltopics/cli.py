import typer
import uvicorn

from parltopics.config import get_settings
from parltopics.sources import bulk
from parltopics.sources.api import OPDClient
from parltopics.sources.assemble import LangMissing, assemble

app = typer.Typer(no_args_is_help=True)
data_app = typer.Typer(no_args_is_help=True, help="Challenge data files.")
app.add_typer(data_app, name="data")


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
