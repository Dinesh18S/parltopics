import httpx
from fastapi import FastAPI

from parltopics.config import Settings, get_settings

app = FastAPI(title="ParlTopics")


def check_model(settings: Settings) -> dict:
    """Ask the endpoint's /models whether the configured model is served."""
    if not settings.llm_base_url:
        return {"reachable": False, "error": "LLM_BASE_URL not set"}
    try:
        r = httpx.get(
            f"{settings.llm_base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=5,
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        return {"reachable": False, "error": type(e).__name__}
    served = [m.get("id") for m in r.json().get("data", [])]
    return {"reachable": settings.llm_name in served, "served": served}


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    model = check_model(settings)
    return {
        "status": "ok",
        "mode": "live" if model["reachable"] else "cached",
        "model": settings.llm_name,
        "model_check": model,
    }
