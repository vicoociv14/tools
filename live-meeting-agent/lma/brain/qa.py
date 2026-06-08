from __future__ import annotations

import os
from typing import Iterator, Optional

from .state import Transcript

DEFAULT_MODEL = "claude-sonnet-4-6"


def build_client(config: Optional[dict] = None):
    """Return (client, model) for the configured Q&A backend.

    qa_backend == "foundry": a Claude model deployed on Azure AI Foundry. The
        Foundry endpoint speaks the standard Anthropic Messages API, so the stock
        SDK client works with x-api-key. Base URL comes from config
        ["foundry_base_url"] (or env LMA_FOUNDRY_BASE_URL); the key comes from env
        LMA_FOUNDRY_API_KEY only (never stored in config / git); model from
        config["foundry_model"].
    otherwise: the first-party Anthropic API (key from env ANTHROPIC_API_KEY).
    """
    import anthropic  # lazy: keep the SDK off unit-test import paths

    config = config or {}
    backend = str(config.get("qa_backend", "anthropic")).strip().lower()

    if backend == "foundry":
        base_url = config.get("foundry_base_url") or os.environ.get("LMA_FOUNDRY_BASE_URL")
        api_key = os.environ.get("LMA_FOUNDRY_API_KEY")
        model = config.get("foundry_model") or DEFAULT_MODEL
        if not base_url:
            raise RuntimeError(
                "qa_backend=foundry but no foundry_base_url in config and no "
                "LMA_FOUNDRY_BASE_URL env var"
            )
        if not api_key:
            raise RuntimeError(
                "qa_backend=foundry but the LMA_FOUNDRY_API_KEY env var is not set"
            )
        return anthropic.Anthropic(base_url=base_url, api_key=api_key), model

    return anthropic.Anthropic(), config.get("model") or DEFAULT_MODEL

SYSTEM_PROMPT = (
    "You are a meeting sparring partner. You are given the live transcript of a "
    "meeting, each line attributed to a speaker (You = the user; Remote / Speaker N "
    "= others). Answer the user's question about the meeting concisely and "
    "accurately, grounded ONLY in the transcript - do not invent content. The "
    "transcript may mix German and English; reply in the same language as the "
    "user's question. If asked to draw or diagram something, output a valid "
    "draw.io (mxGraph) XML document inside a ```xml fenced block."
)

PRESETS = {
    "summary": "Summarize the meeting so far as a few concise bullet points.",
    "decisions": "List the concrete decisions made so far; for each, note who made it.",
    "actions": "List the action items so far; for each, name the owner (the speaker).",
    "questions": "List the open questions or points of disagreement so far.",
    "draw": "Draw a draw.io diagram of what has been discussed (architecture or flow), as mxGraph XML.",
}


def resolve_question(question: str) -> str:
    """Map a preset key to its prompt; otherwise return the question unchanged."""
    return PRESETS.get(question.strip().lower(), question)


def build_messages(transcript: Transcript, question: str) -> tuple[list, str]:
    """Return (system_blocks, user_text). The transcript rides in a cacheable
    system block so repeated questions reuse the prompt cache."""
    convo = transcript.text() or "(no transcript yet)"
    system = [
        {"type": "text", "text": SYSTEM_PROMPT},
        {
            "type": "text",
            "text": "Transcript so far:\n\n" + convo,
            "cache_control": {"type": "ephemeral"},
        },
    ]
    return system, resolve_question(question)


def ask_stream(
    transcript: Transcript,
    question: str,
    *,
    model: str = DEFAULT_MODEL,
    client=None,
    max_tokens: int = 1500,
) -> Iterator[str]:
    """Stream Claude's answer to `question` about the transcript, yielding text chunks."""
    import anthropic  # lazy: keep the SDK off unit-test import paths

    client = client or anthropic.Anthropic()
    system, user_text = build_messages(transcript, question)
    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_text}],
    ) as stream:
        for text in stream.text_stream:
            yield text


def extract_drawio(answer: str) -> Optional[str]:
    """Pull the first ```xml ... ``` (or ```drawio```) fenced block from an answer."""
    for fence in ("```xml", "```drawio", "```"):
        i = answer.find(fence)
        if i == -1:
            continue
        start = answer.find("\n", i)
        if start == -1:
            continue
        end = answer.find("```", start + 1)
        if end == -1:
            continue
        block = answer[start + 1:end].strip()
        if "<mxGraphModel" in block or "<mxfile" in block:
            return block
    return None
