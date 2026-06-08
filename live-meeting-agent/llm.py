import json
import os
from pathlib import Path
from anthropic import Anthropic
from model import MeetingState

PROMPT_DIR = Path(__file__).parent / "prompts"
DEFAULT_MODEL = "claude-sonnet-4-6"


def _load_prompt() -> str:
    return (PROMPT_DIR / "system.md").read_text(encoding="utf-8")


def _load_schema() -> dict:
    return json.loads((PROMPT_DIR / "schema.json").read_text(encoding="utf-8"))


def run_cycle(
    state: MeetingState,
    new_segments_text: str,
    model: str = DEFAULT_MODEL,
    client: Anthropic | None = None,
) -> MeetingState:
    """Run one LLM cycle. Returns an updated MeetingState (with tmp_ ids for new entities)."""
    client = client or Anthropic()
    system_prompt = _load_prompt()
    schema = _load_schema()
    user_message = (
        "Current state:\n"
        f"```json\n{state.model_dump_json(indent=2, by_alias=True)}\n```\n\n"
        "New transcript segments since last cycle:\n"
        f"```\n{new_segments_text}\n```\n\n"
        "Return the updated state model as JSON. Output ONLY the JSON, no prose, no markdown fences."
    )
    response = client.messages.create(
        model=model,
        max_tokens=8000,
        system=[
            {
                "type": "text",
                "text": system_prompt + "\n\n## JSON schema\n\n" + json.dumps(schema),
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_message}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return MeetingState.model_validate_json(raw)
