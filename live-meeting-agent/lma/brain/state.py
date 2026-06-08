from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Segment:
    start: float          # absolute seconds since meeting start
    end: float
    text: str
    speaker: str          # "You" | "Remote" | (M3) "Speaker 1"...
    channel: str          # "mic" | "system"


class Transcript:
    """Thread-safe, start-ordered transcript with optional jsonl persistence."""

    def __init__(self, jsonl_path: Optional[Path] = None):
        self._segments: list[Segment] = []
        self._lock = threading.Lock()
        self._jsonl_path = Path(jsonl_path) if jsonl_path else None
        if self._jsonl_path is not None:
            self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, seg: Segment) -> None:
        with self._lock:
            self._segments.append(seg)
            self._segments.sort(key=lambda s: s.start)
            if self._jsonl_path is not None:
                with self._jsonl_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(asdict(seg), ensure_ascii=False) + "\n")

    def segments(self) -> list[Segment]:
        with self._lock:
            return list(self._segments)

    def text(self) -> str:
        with self._lock:
            return "\n".join(f"[{s.speaker}] {s.text}" for s in self._segments)
