from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

import numpy as np

from .segmenter import find_utterance_end
from .state import Segment

log = logging.getLogger(__name__)

# (audio16k_mono, sample_rate) -> list of (start_s, end_s, text)
TranscribeFn = Callable[[np.ndarray, int], list]
EmitFn = Callable[[Segment], None]


class ChannelTranscriber:
    """Accumulates one channel's 16 kHz audio, cuts utterances on silence, and
    transcribes each completed utterance into absolute-time Segments."""

    def __init__(
        self,
        channel: str,
        speaker: str,
        emit: EmitFn,
        transcribe_fn: TranscribeFn,
        *,
        sample_rate: int = 16000,
        poll_s: float = 1.0,
    ):
        self.channel = channel
        self.speaker = speaker
        self.emit = emit
        self.transcribe_fn = transcribe_fn
        self.sample_rate = sample_rate
        self.poll_s = poll_s
        self._buf = np.zeros(0, dtype=np.float32)
        self._consumed_s = 0.0          # absolute time at buf[0]
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def feed(self, samples: np.ndarray) -> None:
        with self._lock:
            self._buf = np.concatenate([self._buf, np.asarray(samples, dtype=np.float32)])

    def process(self) -> None:
        """Cut + transcribe at most one completed utterance from the buffer."""
        with self._lock:
            buf = self._buf
            base = self._consumed_s
        cut = find_utterance_end(buf, self.sample_rate)
        if cut is None:
            return
        utterance = buf[:cut]
        try:
            results = self.transcribe_fn(utterance, self.sample_rate)
        except Exception:
            log.exception("transcribe failed on %s channel", self.channel)
            results = []
        for (s, e, text) in results:
            self.emit(Segment(
                start=base + s, end=base + e, text=text,
                speaker=self.speaker, channel=self.channel,
            ))
        with self._lock:
            self._buf = self._buf[cut:]
            self._consumed_s += cut / self.sample_rate

    def flush(self) -> None:
        """Force-transcribe whatever speech remains (call on stop)."""
        with self._lock:
            buf = self._buf
            base = self._consumed_s
        if len(buf) == 0:
            return
        try:
            results = self.transcribe_fn(buf, self.sample_rate)
        except Exception:
            log.exception("flush transcribe failed on %s channel", self.channel)
            results = []
        for (s, e, text) in results:
            self.emit(Segment(
                start=base + s, end=base + e, text=text,
                speaker=self.speaker, channel=self.channel,
            ))
        with self._lock:
            self._consumed_s += len(self._buf) / self.sample_rate
            self._buf = np.zeros(0, dtype=np.float32)

    def run(self) -> None:
        while not self._stop.is_set():
            self.process()
            self._stop.wait(self.poll_s)

    def start(self) -> None:
        self._thread = threading.Thread(target=self.run, name=f"transcriber-{self.channel}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self.flush()
