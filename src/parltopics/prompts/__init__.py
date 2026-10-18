"""Versioned prompt templates. Change a template → new version file → re-run eval."""

import hashlib
from pathlib import Path

from pydantic import BaseModel

from parltopics.topics import Topic

PROMPT_DIR = Path(__file__).parent


class Prompt(BaseModel):
    version: str
    system: str
    user: str
    retry: str | None  # follow-up message when evidence fails verification (None = no retry)
    sha: str


def load_prompt(version: str) -> Prompt:
    system = (PROMPT_DIR / f"{version}.system.txt").read_text()
    user = (PROMPT_DIR / f"{version}.user.txt").read_text()
    retry_path = PROMPT_DIR / f"{version}.retry.txt"
    retry = retry_path.read_text() if retry_path.exists() else None
    sha = hashlib.sha256(f"{version}\x00{system}\x00{user}\x00{retry or ''}".encode()).hexdigest()
    return Prompt(version=version, system=system, user=user, retry=retry, sha=sha)


def render_adhoc(prompt: Prompt, topic: Topic, text: str, lang: str) -> tuple[str, str]:
    rules = "".join(
        f"{label}:\n" + "".join(f"- {item}\n" for item in items)
        for label, items in (("COUNTS AS THIS TOPIC", topic.include), ("DOES NOT COUNT", topic.exclude))
        if items
    )
    user = prompt.user.format(
        name=topic.name, definition=topic.definition.strip(), rules=rules, lang=lang, text=text
    )
    return prompt.system.strip(), user.strip()
