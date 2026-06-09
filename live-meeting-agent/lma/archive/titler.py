"""Generate a meeting title/summary/topics from its transcript, via Foundry Claude.

Cached as a `<id>.meta.json` sidecar so titling runs once per meeting. Used lazily
by the archive server (on first view / background backfill) and by the backfill
command.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from ..brain import qa
from . import index as idx

log = logging.getLogger(__name__)

TITLE_SYSTEM = (
    "You title meeting transcripts. Given a transcript (lines like '[Speaker] text'), "
    "return ONLY a JSON object with three keys: 'title' (a short, specific headline of at "
    "most ~8 words), 'summary' (one sentence), and 'topics' (an array of 3-6 short tag "
    "words). Write the title and summary in the SAME language as the meeting. No prose, no "
    "code fence - just the JSON object."
)
MAX_TRANSCRIPT_CHARS = 20000


def _parse_json(text: str) -> Optional[dict]:
    t = (text or "").strip()
    if t.startswith("```"):
        nl = t.find("\n")
        t = t[nl + 1:] if nl != -1 else t
        if t.endswith("```"):
            t = t[:-3]
    a, b = t.find("{"), t.rfind("}")
    if a != -1 and b > a:
        t = t[a:b + 1]
    try:
        return json.loads(t)
    except Exception:
        return None


def generate_meta(transcript_text: str, *, client, model: str) -> dict:
    """Return {title, summary, topics} from a transcript via Claude (non-streaming)."""
    if not transcript_text.strip():
        return {"title": "", "summary": "", "topics": []}
    msg = client.messages.create(
        model=model,
        max_tokens=400,
        system=TITLE_SYSTEM,
        messages=[{"role": "user", "content": "Transcript:\n\n" + transcript_text[:MAX_TRANSCRIPT_CHARS]}],
    )
    text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
    data = _parse_json(text) or {}
    topics = data.get("topics") or []
    if not isinstance(topics, list):
        topics = [str(topics)]
    return {
        "title": str(data.get("title") or "").strip(),
        "summary": str(data.get("summary") or "").strip(),
        "topics": [str(t).strip() for t in topics if str(t).strip()][:6],
    }


def _transcript_text(jsonl_path: Path) -> str:
    return "\n".join(
        f"[{s.get('speaker', '')}] {s.get('text', '')}" for s in idx.read_segments(jsonl_path)
    )


def ensure_meta(jsonl_path, config: dict, *, client=None, model: Optional[str] = None) -> dict:
    """Return the meeting's meta dict, generating + caching the sidecar if missing."""
    jsonl_path = Path(jsonl_path)
    sidecar = idx.load_meta_sidecar(jsonl_path)
    if sidecar and (sidecar.get("title") or "").strip():
        return sidecar

    basic = idx.derive_basic(jsonl_path)
    mid = idx.meeting_id(jsonl_path)
    started = idx.parse_started_at(mid) or ""
    gen = {"title": "", "summary": "", "topics": []}
    used_model = model
    try:
        if client is None:
            client, used_model = qa.build_client(config)
        gen = generate_meta(_transcript_text(jsonl_path), client=client, model=used_model)
    except Exception:
        log.exception("title generation failed for %s", mid)

    meta = {
        "id": mid,
        "title": gen["title"] or (f"Meeting {started[:16].replace('T', ' ')}" if started else mid),
        "summary": gen["summary"],
        "topics": gen["topics"],
        "started_at": started,
        "duration_s": basic["duration_s"],
        "speakers": basic["speakers"],
        "segments": basic["segments"],
        "title_model": used_model,
    }
    try:
        idx.meta_path(jsonl_path).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        log.exception("could not write meta sidecar for %s", mid)
    return meta


def backfill(recordings_dir, config: dict) -> int:
    """Title every untitled meeting under recordings_dir. Returns count titled."""
    client = model = None
    titled = 0
    for p in idx.iter_transcripts(recordings_dir):
        sc = idx.load_meta_sidecar(p)
        if sc and (sc.get("title") or "").strip():
            continue
        if client is None:
            client, model = qa.build_client(config)
        ensure_meta(p, config, client=client, model=model)
        titled += 1
    return titled
