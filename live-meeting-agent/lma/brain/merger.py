from __future__ import annotations

from typing import Callable, Optional

from .state import Segment, Transcript


class Merger:
    """Collects Segments from the transcribers into one Transcript and (optionally)
    broadcasts each to a sink (the WebSocket layer in Part B)."""

    def __init__(self, transcript: Transcript, broadcast: Optional[Callable[[Segment], None]] = None):
        self.transcript = transcript
        self.broadcast = broadcast

    def on_segment(self, seg: Segment) -> None:
        self.transcript.add(seg)
        if self.broadcast is not None:
            self.broadcast(seg)
