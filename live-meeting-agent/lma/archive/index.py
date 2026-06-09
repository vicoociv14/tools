"""Build a browsable index over recorded meetings.

A meeting is a `<id>.transcript.jsonl` under the recordings dir (one Segment per
line). Optional sidecars: `<id>.meta.json` (title/summary/topics, written by the
titler). Pure file-based - no database.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

TRANSCRIPT_SUFFIX = ".transcript.jsonl"


@dataclass
class MeetingMeta:
    id: str
    started_at: str          # ISO 8601, or "" if unparseable
    duration_s: float
    speakers: list
    segments: int
    title: str
    summary: str
    topics: list
    titled: bool             # True once a real title has been generated
    transcript_path: str


def meeting_id(jsonl_path: Path) -> str:
    name = jsonl_path.name
    if name.endswith(TRANSCRIPT_SUFFIX):
        return name[: -len(TRANSCRIPT_SUFFIX)]
    return jsonl_path.stem


def meta_path(jsonl_path: Path) -> Path:
    return jsonl_path.with_name(meeting_id(jsonl_path) + ".meta.json")


def parse_started_at(mid: str) -> Optional[str]:
    """Recording ids look like 260608_073714 (%y%m%d_%H%M%S)."""
    try:
        return datetime.strptime(mid[:13], "%y%m%d_%H%M%S").isoformat()
    except Exception:
        return None


def read_segments(jsonl_path: Path) -> list:
    segs = []
    try:
        for line in Path(jsonl_path).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    segs.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        pass
    return segs


def derive_basic(jsonl_path: Path) -> dict:
    segs = read_segments(jsonl_path)
    duration = max((float(s.get("end", 0.0)) for s in segs), default=0.0)
    speakers: list = []
    for s in segs:
        sp = s.get("speaker")
        if sp and sp not in speakers:
            speakers.append(sp)
    return {"duration_s": round(duration, 1), "speakers": speakers, "segments": len(segs)}


def load_meta_sidecar(jsonl_path: Path) -> Optional[dict]:
    mp = meta_path(Path(jsonl_path))
    if mp.exists():
        try:
            return json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _placeholder_title(mid: str, started_at: str) -> str:
    return f"Meeting {started_at[:16].replace('T', ' ')}" if started_at else mid


def meeting_meta(jsonl_path: Path) -> MeetingMeta:
    jsonl_path = Path(jsonl_path)
    mid = meeting_id(jsonl_path)
    basic = derive_basic(jsonl_path)
    sidecar = load_meta_sidecar(jsonl_path) or {}
    started = sidecar.get("started_at") or parse_started_at(mid) or ""
    title = (sidecar.get("title") or "").strip()
    titled = bool(title)
    if not title:
        title = _placeholder_title(mid, started)
    return MeetingMeta(
        id=mid,
        started_at=started,
        duration_s=float(sidecar.get("duration_s", basic["duration_s"])),
        speakers=sidecar.get("speakers", basic["speakers"]),
        segments=int(sidecar.get("segments", basic["segments"])),
        title=title,
        summary=(sidecar.get("summary") or "").strip(),
        topics=sidecar.get("topics", []),
        titled=titled,
        transcript_path=str(jsonl_path),
    )


def iter_transcripts(recordings_dir) -> list:
    root = Path(recordings_dir)
    if not root.exists():
        return []
    return sorted(root.rglob("*" + TRANSCRIPT_SUFFIX))


def build_index(recordings_dir) -> list:
    metas = [meeting_meta(p) for p in iter_transcripts(recordings_dir)]
    metas.sort(key=lambda m: m.started_at, reverse=True)
    return metas
