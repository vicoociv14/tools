"""Live audio bus - the seam between the capture core and the live brain.

The recorder calls `AudioBus.push(frame)` with each (N, 2) float32 chunk at the
capture sample rate (column 0 = mic, column 1 = system). The bus splits the two
channels, downsamples each to 16 kHz mono (what whisper and pyannote want), and
keeps the most recent `capacity_seconds` per channel in a ring buffer. With no
brain attached the recorder's tap is None and `push` is never called, so this
costs nothing during a plain recording.
"""
from __future__ import annotations

import logging
import threading
from math import gcd

import numpy as np
from scipy.signal import resample_poly

log = logging.getLogger(__name__)

TARGET_SAMPLERATE = 16000


class RingBuffer:
    """Fixed-capacity mono float32 ring buffer, newest-wins."""

    def __init__(self, capacity_seconds: float, sample_rate: int = TARGET_SAMPLERATE):
        self.sample_rate = sample_rate
        self.capacity = int(capacity_seconds * sample_rate)
        self._buf = np.zeros(self.capacity, dtype=np.float32)
        self._write = 0
        self._filled = 0
        self._lock = threading.Lock()

    def write(self, samples: np.ndarray) -> None:
        samples = np.asarray(samples, dtype=np.float32).ravel()
        with self._lock:
            n = len(samples)
            if n >= self.capacity:
                self._buf[:] = samples[-self.capacity:]
                self._write = 0
                self._filled = self.capacity
                return
            end = self._write + n
            if end <= self.capacity:
                self._buf[self._write:end] = samples
            else:
                first = self.capacity - self._write
                self._buf[self._write:] = samples[:first]
                self._buf[: n - first] = samples[first:]
            self._write = (self._write + n) % self.capacity
            self._filled = min(self._filled + n, self.capacity)

    def read_last(self, seconds: float) -> np.ndarray:
        with self._lock:
            want = min(int(seconds * self.sample_rate), self._filled)
            if want == 0:
                return np.zeros(0, dtype=np.float32)
            start = (self._write - want) % self.capacity
            if start + want <= self.capacity:
                return self._buf[start:start + want].copy()
            tail = self.capacity - start
            return np.concatenate([self._buf[start:], self._buf[: want - tail]])


def _resample(x: np.ndarray, src: int, tgt: int) -> np.ndarray:
    if src == tgt:
        return np.asarray(x, dtype=np.float32)
    g = gcd(src, tgt)
    return resample_poly(x, tgt // g, src // g).astype(np.float32)


class AudioBus:
    """Splits stereo capture frames into 16 kHz mono mic/system ring buffers."""

    def __init__(
        self,
        source_samplerate: int,
        target_samplerate: int = TARGET_SAMPLERATE,
        capacity_seconds: float = 1800.0,
    ):
        self.source_samplerate = source_samplerate
        self.target_samplerate = target_samplerate
        self._channels = {
            "mic": RingBuffer(capacity_seconds, target_samplerate),
            "system": RingBuffer(capacity_seconds, target_samplerate),
        }
        self._subscribers = []

    def subscribe(self, fn) -> None:
        """Register fn(channel: str, samples: np.ndarray) called on every push.

        Lets streaming consumers (the live brain) receive audio as it arrives,
        in addition to the on-demand ring buffers. A subscriber that raises is
        logged and skipped - it must never break capture.
        """
        self._subscribers.append(fn)

    def push(self, frame: np.ndarray) -> None:
        """frame: (N, 2) float32 at source_samplerate; col 0 = mic, col 1 = system."""
        if frame.ndim != 2 or frame.shape[1] < 2 or len(frame) == 0:
            return
        mic = _resample(frame[:, 0], self.source_samplerate, self.target_samplerate)
        system = _resample(frame[:, 1], self.source_samplerate, self.target_samplerate)
        self._channels["mic"].write(mic)
        self._channels["system"].write(system)
        for fn in self._subscribers:
            try:
                fn("mic", mic)
                fn("system", system)
            except Exception:
                log.exception("audio bus subscriber raised; skipping")

    def read_last(self, channel: str, seconds: float) -> np.ndarray:
        if channel not in self._channels:
            raise ValueError(f"unknown channel '{channel}', expected 'mic' or 'system'")
        return self._channels[channel].read_last(seconds)
