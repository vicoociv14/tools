from __future__ import annotations

import logging
from typing import Callable, Optional

import numpy as np

from ..capture.bus import AudioBus
from .merger import Merger
from .state import Segment, Transcript
from .transcriber import ChannelTranscriber, TranscribeFn

log = logging.getLogger(__name__)


class Brain:
    """Wires an AudioBus to two ChannelTranscribers (mic='You', system='Remote')
    feeding a Merger/Transcript. `attach()` subscribes to the bus; `start()` runs
    the transcriber threads; `process_once()` drives one pass synchronously (tests)."""

    def __init__(
        self,
        bus: AudioBus,
        transcript: Transcript,
        transcribe_fn: TranscribeFn,
        *,
        broadcast: Optional[Callable[[Segment], None]] = None,
    ):
        self.bus = bus
        self.merger = Merger(transcript, broadcast)
        self.mic = ChannelTranscriber("mic", "You", self.merger.on_segment, transcribe_fn)
        self.system = ChannelTranscriber("system", "Remote", self.merger.on_segment, transcribe_fn)
        self._by_channel = {"mic": self.mic, "system": self.system}

    def attach(self) -> None:
        self.bus.subscribe(self._dispatch)

    def _dispatch(self, channel: str, samples: np.ndarray) -> None:
        t = self._by_channel.get(channel)
        if t is not None:
            t.feed(samples)

    def process_once(self) -> None:
        self.mic.process()
        self.system.process()

    def start(self) -> None:
        self.mic.start()
        self.system.start()

    def stop(self) -> None:
        self.mic.stop()
        self.system.stop()
