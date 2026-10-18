import typer
import uvicorn

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """ParlTopics command line."""


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8080) -> None:
    """Start the API server."""
    uvicorn.run("parltopics.api:app", host=host, port=port)
