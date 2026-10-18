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
    sha: str


def load_prompt(version: str) -> Prompt:
    system = (PROMPT_DIR / f"{version}.system.txt").read_text()
    user = (PROMPT_DIR / f"{version}.user.txt").read_text()
    sha = hashlib.sha256(f"{system}\x00{user}".encode()).hexdigest()
    return Prompt(version=version, system=system, user=user, sha=sha)


def render_adhoc(prompt: Prompt, topic: Topic, text: str, lang: str) -> tuple[str, str]:
    rules = "".join(
        f"{label}: {value.strip()}\n"
        for label, value in (("COUNTS AS THIS TOPIC", topic.include), ("DOES NOT COUNT", topic.exclude))
        if value and value.strip()
    )
    user = prompt.user.format(
        name=topic.name, definition=topic.definition.strip(), rules=rules, lang=lang, text=text
    )
    return prompt.system.strip(), user.strip()
